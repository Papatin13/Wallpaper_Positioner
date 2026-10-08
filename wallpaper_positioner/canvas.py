"""Interactive GTK4 DrawingArea canvas powered by Cairo."""

from __future__ import annotations

import math
from typing import List, Optional, Tuple, Callable
import cairo

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, Gio, GLib

from .models import Layer, Handle, HandleType
from .monitor_manager import MonitorInfo
from .color_engine import rgb_to_hex
from .i18n import tr


class WallpaperCanvas(Gtk.DrawingArea):
    """Interactive canvas widget for positioning and manipulating image layers."""

    def __init__(self, monitor: MonitorInfo):
        super().__init__()
        self.monitor = monitor
        self.layers: List[Layer] = []
        self.all_layers: List[Layer] = []
        self._selected_layers: List[Layer] = []
        self.active_sub_monitor: Optional[MonitorInfo] = None
        self.bg_color: Tuple[int, int, int] = (26, 27, 38)  # Default dark theme background

        # Default styling for newly added layers (persistent styling across layers)
        self.default_border_width: float = 0.0
        self.default_border_color: Tuple[int, int, int] = (255, 255, 255)
        self.default_border_radius: float = 0.0

        self.default_shadow_enabled: bool = False
        self.default_shadow_blur: float = 20.0
        self.default_shadow_offset_x: float = 0.0
        self.default_shadow_offset_y: float = 15.0
        self.default_shadow_opacity: float = 0.5
        self.default_shadow_color: Tuple[int, int, int] = (0, 0, 0)

        # Viewport transform (Canvas to Widget coordinates)
        self.zoom: float = 1.0
        self.pan_x: float = 0.0
        self.pan_y: float = 0.0
        self.user_panned_or_zoomed: bool = False

        # Interaction state
        self.active_handle: Optional[Handle] = None
        self.is_dragging_layer: bool = False
        self.is_panning: bool = False
        self.is_rubberband: bool = False
        self.rubberband_start: Tuple[float, float] = (0.0, 0.0)
        self.rubberband_current: Tuple[float, float] = (0.0, 0.0)
        self.rubberband_base_selection: List[Layer] = []
        self.drag_start_mouse: Tuple[float, float] = (0.0, 0.0)
        self.drag_start_layer_pos: Tuple[float, float] = (0.0, 0.0)
        self.drag_start_layer_size: Tuple[float, float] = (0.0, 0.0)
        self.drag_start_multi_positions: Dict[Layer, Tuple[float, float]] = {}
        self.drag_start_multi_canvas_positions: Dict[Layer, Tuple[float, float]] = {}
        self.drag_start_pan: Tuple[float, float] = (0.0, 0.0)

        # Callbacks
        self.on_selection_changed: Optional[Callable[[Optional[Layer]], None]] = None
        self.on_layers_changed: Optional[Callable[[], None]] = None
        self.on_bg_color_changed: Optional[Callable[[Tuple[int, int, int]], None]] = None
        self.on_paste_requested: Optional[Callable[[], None]] = None

        # Widget setup
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_focusable(True)
        self.set_draw_func(self._on_draw)

        # Connect event controllers
        self._setup_event_controllers()
        self._setup_drop_target()

    # -------------------------------------------------------------------------
    # Selection Properties
    # -------------------------------------------------------------------------
    @property
    def selected_layers(self) -> List[Layer]:
        return self._selected_layers

    @selected_layers.setter
    def selected_layers(self, layers: List[Layer]):
        self._selected_layers = [l for l in layers if l in self.layers]

    @property
    def selected_layer(self) -> Optional[Layer]:
        return self._selected_layers[-1] if self._selected_layers else None

    @selected_layer.setter
    def selected_layer(self, layer: Optional[Layer]):
        if layer is None:
            self._selected_layers.clear()
        elif layer in self.layers:
            self._selected_layers = [layer]
        else:
            self._selected_layers = [layer]

    # -------------------------------------------------------------------------
    # Event Controllers Setup
    # -------------------------------------------------------------------------
    def _setup_event_controllers(self):
        # Click gesture (Primary button)
        self.click_gesture = Gtk.GestureClick.new()
        self.click_gesture.set_button(0)  # Listen to all mouse buttons
        self.click_gesture.connect("pressed", self._on_button_pressed)
        self.click_gesture.connect("released", self._on_button_released)
        self.add_controller(self.click_gesture)

        # Drag gesture
        self.drag_gesture = Gtk.GestureDrag.new()
        self.drag_gesture.set_button(0)
        self.drag_gesture.connect("drag-begin", self._on_drag_begin)
        self.drag_gesture.connect("drag-update", self._on_drag_update)
        self.drag_gesture.connect("drag-end", self._on_drag_end)
        self.add_controller(self.drag_gesture)

        # Motion controller for cursor styling
        self.motion_controller = Gtk.EventControllerMotion.new()
        self.motion_controller.connect("motion", self._on_mouse_motion)
        self.add_controller(self.motion_controller)

        # Scroll controller for zooming
        self.scroll_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
        )
        self.scroll_controller.connect("scroll", self._on_scroll)
        self.add_controller(self.scroll_controller)

        # Keyboard controller for layer nudging & shortcuts
        self.key_controller = Gtk.EventControllerKey.new()
        self.key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(self.key_controller)

    def _setup_drop_target(self):
        # Accept Gdk.FileList for drag and drop from file managers
        drop_file_list = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_file_list.connect("drop", self._on_file_list_drop)
        self.add_controller(drop_file_list)

        # Also accept Gio.File
        drop_file = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop_file.connect("drop", self._on_single_file_drop)
        self.add_controller(drop_file)

    # -------------------------------------------------------------------------
    # Coordinate Transforms
    # -------------------------------------------------------------------------
    def widget_to_canvas(self, wx: float, wy: float) -> Tuple[float, float]:
        """Convert widget window coordinates to canvas pixel coordinates."""
        cx = (wx - self.pan_x) / self.zoom
        cy = (wy - self.pan_y) / self.zoom
        return cx, cy

    def canvas_to_widget(self, cx: float, cy: float) -> Tuple[float, float]:
        """Convert canvas pixel coordinates to widget window coordinates."""
        wx = (cx * self.zoom) + self.pan_x
        wy = (cy * self.zoom) + self.pan_y
        return wx, wy

    # -------------------------------------------------------------------------
    # Multi-Monitor Coordinate & Sub-Monitor Helpers
    # -------------------------------------------------------------------------
    def get_sub_monitor_for_layer(self, layer: Layer) -> Optional[MonitorInfo]:
        """Find the sub-monitor that this layer belongs to."""
        if not self.monitor.is_spanned or not self.monitor.sub_monitors:
            return None
        for sub in self.monitor.sub_monitors:
            if sub.name == layer.monitor_name:
                return sub
        return self.monitor.sub_monitors[0]

    def get_sub_monitor_at_point(self, cx: float, cy: float) -> Optional[MonitorInfo]:
        """Return the sub-monitor containing the canvas coordinate (cx, cy)."""
        if not self.monitor.is_spanned or not self.monitor.sub_monitors:
            return None
        for sub in self.monitor.sub_monitors:
            if sub.rel_x <= cx <= sub.rel_x + sub.width and sub.rel_y <= cy <= sub.rel_y + sub.height:
                return sub
        return None

    def get_closest_sub_monitor_at_point(self, cx: float, cy: float) -> MonitorInfo:
        """Return the sub-monitor closest to the canvas coordinate (cx, cy)."""
        if not self.monitor.is_spanned or not self.monitor.sub_monitors:
            return self.monitor
        hit = self.get_sub_monitor_at_point(cx, cy)
        if hit is not None:
            return hit
        best_sub = self.monitor.sub_monitors[0]
        best_dist = float("inf")
        for sub in self.monitor.sub_monitors:
            center_x = sub.rel_x + (sub.width / 2.0)
            dist = abs(cx - center_x)
            if dist < best_dist:
                best_dist = dist
                best_sub = sub
        return best_sub

    def get_layer_canvas_pos(self, layer: Layer) -> Tuple[float, float]:
        """Return layer center position in canvas coordinate space."""
        if self.monitor.is_spanned and self.monitor.sub_monitors:
            sub = self.get_sub_monitor_for_layer(layer)
            if sub is not None:
                return sub.rel_x + layer.x, sub.rel_y + layer.y
        return layer.x, layer.y

    def get_layer_local_coords(self, layer: Layer, cx: float, cy: float) -> Tuple[float, float]:
        """Convert canvas coordinate (cx, cy) to local coordinates for this layer's monitor."""
        if self.monitor.is_spanned and self.monitor.sub_monitors:
            sub = self.get_sub_monitor_for_layer(layer)
            if sub is not None:
                return cx - sub.rel_x, cy - sub.rel_y
        return cx, cy

    def set_layer_canvas_pos(self, layer: Layer, cx: float, cy: float):
        """Set layer position from canvas coordinates, updating monitor assignment if moved across screens."""
        if self.monitor.is_spanned and self.monitor.sub_monitors:
            sub = self.get_closest_sub_monitor_at_point(cx, cy)
            layer.monitor_name = sub.name
            layer.x = cx - sub.rel_x
            layer.y = cy - sub.rel_y
        else:
            layer.monitor_name = self.monitor.name
            layer.x = cx
            layer.y = cy

    def set_monitor(self, monitor: MonitorInfo):
        """Update active monitor, filter/restore visible layers, and re-fit canvas."""
        self.monitor = monitor

        # Ensure all existing layers in self.layers are registered in self.all_layers
        for l in self.layers:
            if l not in self.all_layers:
                self.all_layers.append(l)

        # Filter active layers for this monitor view
        if monitor.is_spanned:
            self.layers = list(self.all_layers)
        elif monitor.is_custom:
            if not self.layers and self.all_layers:
                self.layers = list(self.all_layers)
            for l in self.layers:
                l.monitor_name = monitor.name
        else:
            self.layers = [l for l in self.all_layers if (l.monitor_name == monitor.name or not l.monitor_name)]
            for l in self.layers:
                if not l.monitor_name:
                    l.monitor_name = monitor.name

        self._selected_layers = [l for l in self._selected_layers if l in self.layers]
        self.fit_to_view()
        if self.on_layers_changed:
            self.on_layers_changed()
        if self.on_selection_changed:
            self.on_selection_changed(self.selected_layer)
        self.queue_draw()

    def update_custom_size(self, width: int, height: int):
        """Update canvas resolution dimensions and re-fit view."""
        self.monitor.width = max(100, int(round(width)))
        self.monitor.height = max(100, int(round(height)))
        self.fit_to_view()
        self.queue_draw()

    def fit_to_view(self):
        """Scale and center the canvas within the current drawing area."""
        w = self.get_width()
        h = self.get_height()
        if w <= 10 or h <= 10 or self.monitor.width <= 0 or self.monitor.height <= 0:
            return

        padding = 40.0
        avail_w = max(100.0, w - (padding * 2))
        avail_h = max(100.0, h - (padding * 2))

        scale_x = avail_w / self.monitor.width
        scale_y = avail_h / self.monitor.height
        self.zoom = min(scale_x, scale_y)

        # Center canvas in widget
        canvas_display_w = self.monitor.width * self.zoom
        canvas_display_h = self.monitor.height * self.zoom
        self.pan_x = (w - canvas_display_w) / 2.0
        self.pan_y = (h - canvas_display_h) / 2.0
        self.user_panned_or_zoomed = False
        self.queue_draw()

    def set_zoom_centered(self, new_zoom: float, center_wx: float, center_wy: float):
        """Zoom in or out while keeping the canvas point under (center_wx, center_wy) fixed."""
        new_zoom = max(0.05, min(5.0, new_zoom))
        if abs(new_zoom - self.zoom) < 1e-4:
            return

        cx, cy = self.widget_to_canvas(center_wx, center_wy)
        self.zoom = new_zoom
        self.pan_x = center_wx - (cx * self.zoom)
        self.pan_y = center_wy - (cy * self.zoom)
        self.user_panned_or_zoomed = True
        self.queue_draw()

    def set_default_style_from_layer(self, layer: Layer):
        """Update active default styling (border & shadow) from a layer."""
        self.default_border_width = layer.border_width
        self.default_border_color = layer.border_color
        self.default_border_radius = layer.border_radius
        self.default_shadow_enabled = layer.shadow_enabled
        self.default_shadow_blur = layer.shadow_blur
        self.default_shadow_offset_x = layer.shadow_offset_x
        self.default_shadow_offset_y = layer.shadow_offset_y
        self.default_shadow_opacity = layer.shadow_opacity
        self.default_shadow_color = layer.shadow_color

    def apply_default_style_to_layer(self, layer: Layer):
        """Apply active default styling (border & shadow) to a layer."""
        layer.border_width = self.default_border_width
        layer.border_color = self.default_border_color
        layer.border_radius = self.default_border_radius
        layer.shadow_enabled = self.default_shadow_enabled
        layer.shadow_blur = self.default_shadow_blur
        layer.shadow_offset_x = self.default_shadow_offset_x
        layer.shadow_offset_y = self.default_shadow_offset_y
        layer.shadow_opacity = self.default_shadow_opacity
        layer.shadow_color = self.default_shadow_color

    def apply_style_to_all_layers(self, source_layer: Optional[Layer] = None):
        """Apply border and shadow styling (from source_layer or current defaults) to all layers."""
        if source_layer is not None:
            self.set_default_style_from_layer(source_layer)
        for layer in self.layers:
            self.apply_default_style_to_layer(layer)
        self.queue_draw()

    # -------------------------------------------------------------------------
    # Auto Layout & Spacing (Dynamic & Proportional)
    # -------------------------------------------------------------------------
    @staticmethod
    def _calculate_grid_dimensions(n: int, avail_w: float, avail_h: float) -> Tuple[int, int]:
        """Determine optimal column and row counts for n items in given aspect ratio."""
        if n <= 1:
            return 1, 1
        ratio = avail_w / max(1.0, avail_h)
        if n == 2:
            return (2, 1) if ratio >= 1.0 else (1, 2)
        elif n == 3:
            return (3, 1) if ratio >= 1.7 else (2, 2)
        elif n == 4:
            return 2, 2
        elif n in [5, 6]:
            return (3, 2) if ratio >= 1.0 else (2, 3)
        elif n in [7, 8]:
            return (4, 2) if ratio >= 1.0 else (2, 4)
        elif n == 9:
            return 3, 3
        else:
            cols = max(1, int(round(math.sqrt(n * ratio))))
            rows = max(1, int(math.ceil(n / cols)))
            return cols, rows

    @staticmethod
    def _compute_layer_weights(layers: List[Layer]) -> List[float]:
        """Compute relative importance weights based on image native resolution or canvas size."""
        mags = []
        for l in layers:
            nat_area = float(max(10, l.orig_width * l.orig_height))
            cur_area = float(max(10, l.width * l.height))
            mag = math.sqrt(max(nat_area, cur_area))
            mags.append(mag)

        min_m = min(mags)
        max_m = max(mags)
        if max_m > min_m * 1.15:
            # Scale weights smoothly between 1.0 (smallest) and 3.5 (largest)
            return [1.0 + 2.5 * ((m - min_m) / (max_m - min_m)) for m in mags]
        return [1.0 for _ in mags]

    @staticmethod
    def _layout_as_grid(
        rect: Tuple[float, float, float, float],
        layers: List[Layer],
        gap: float,
    ) -> List[Tuple[Layer, Tuple[float, float, float, float]]]:
        """Uniform grid placement for a group of layers inside (rx, ry, rw, rh)."""
        rx, ry, rw, rh = rect
        n = len(layers)
        if n == 0:
            return []
        cols, rows = WallpaperCanvas._calculate_grid_dimensions(n, rw, rh)
        g = gap
        if cols > 1 and (cols - 1) * g >= rw:
            g = max(0.0, (rw - 10.0) / (cols - 1))
        if rows > 1 and (rows - 1) * g >= rh:
            g = max(0.0, (rh - 10.0) / (rows - 1))

        cell_w = max(10.0, (rw - ((cols - 1) * g)) / cols)
        cell_h = max(10.0, (rh - ((rows - 1) * g)) / rows)

        placements = []
        idx = 0
        for r in range(rows):
            n_in_row = min(cols, n - idx)
            if n_in_row <= 0:
                break
            row_w = (n_in_row * cell_w) + max(0.0, (n_in_row - 1) * g)
            row_start_x = rx + ((rw - row_w) / 2.0)
            row_y = ry + (r * (cell_h + g))

            for c in range(n_in_row):
                cell_rect = (row_start_x + (c * (cell_w + g)), row_y, cell_w, cell_h)
                placements.append((layers[idx], cell_rect))
                idx += 1
        return placements

    @staticmethod
    def _score_candidate(
        placements: List[Tuple[Layer, Tuple[float, float, float, float]]]
    ) -> float:
        total = 0.0
        for layer, (_, _, cw, ch) in placements:
            cell_ar = cw / max(1.0, ch)
            layer_ar = layer.aspect_ratio
            distortion = max(cell_ar / layer_ar, layer_ar / cell_ar)
            pen = 0.0
            if cell_ar > 3.0:
                pen += 25.0 * (cell_ar - 3.0)
            if cell_ar < 0.33:
                pen += 25.0 * (0.33 - cell_ar)
            total += distortion + pen
        return total

    @staticmethod
    def _weighted_bsp_partition(
        rect: Tuple[float, float, float, float],
        layers: List[Layer],
        weights: List[float],
        gap: float,
    ) -> List[Tuple[Layer, Tuple[float, float, float, float]]]:
        """Recursive Binary Space Partitioning allocating area proportional to item weights."""
        rx, ry, rw, rh = rect
        n = len(layers)
        if n == 0:
            return []
        if n == 1:
            return [(layers[0], rect)]
        if max(weights) <= min(weights) * 1.3:
            return WallpaperCanvas._layout_as_grid(rect, layers, gap)

        total_w = sum(weights)
        best_score = float("inf")
        best_split = None

        for k in range(1, n):
            w_a = sum(weights[:k])
            frac = w_a / total_w
            for ori in ["V", "H"]:
                if ori == "V":
                    w_left = max(10.0, (rw - gap) * frac)
                    w_right = max(10.0, rw - gap - w_left)
                    r_a = (rx, ry, w_left, rh)
                    r_b = (rx + w_left + gap, ry, w_right, rh)
                else:
                    h_top = max(10.0, (rh - gap) * frac)
                    h_bot = max(10.0, rh - gap - h_top)
                    r_a = (rx, ry, rw, h_top)
                    r_b = (rx, ry + h_top + gap, rw, h_bot)

                ar_a = r_a[2] / max(1.0, r_a[3])
                ar_b = r_b[2] / max(1.0, r_b[3])
                pen = 0.0
                if ar_a > 2.8: pen += 40.0 * (ar_a - 2.8)
                if ar_a < 0.35: pen += 40.0 * (0.35 - ar_a)
                if ar_b > 2.8: pen += 40.0 * (ar_b - 2.8)
                if ar_b < 0.35: pen += 40.0 * (0.35 - ar_b)

                score = pen + abs(ar_a - 1.33) + abs(ar_b - 1.33)
                if score < best_score:
                    best_score = score
                    best_split = (k, r_a, r_b)

        if best_split is None:
            return WallpaperCanvas._layout_as_grid(rect, layers, gap)

        k, r_a, r_b = best_split
        return WallpaperCanvas._weighted_bsp_partition(r_a, layers[:k], weights[:k], gap) + \
               WallpaperCanvas._weighted_bsp_partition(r_b, layers[k:], weights[k:], gap)

    @classmethod
    def _solve_dynamic_layout(
        cls,
        rect: Tuple[float, float, float, float],
        layers: List[Layer],
        gap: float,
    ) -> List[Tuple[Layer, Tuple[float, float, float, float]]]:
        """Find the optimal dynamic layout allocating more space to larger images."""
        rx, ry, rw, rh = rect
        n = len(layers)
        if n == 0:
            return []
        if n == 1:
            return [(layers[0], rect)]

        weights = cls._compute_layer_weights(layers)
        paired = sorted(zip(layers, weights), key=lambda x: x[1], reverse=True)
        sorted_layers = [p[0] for p in paired]
        sorted_weights = [p[1] for p in paired]

        candidates = []

        # Candidate 1: Recursive BSP
        c_bsp = cls._weighted_bsp_partition(rect, sorted_layers, sorted_weights, gap)
        candidates.append(c_bsp)

        # Candidate 2: Hero Layouts (if 1 dominant item exists and n >= 3)
        if n >= 3 and sorted_weights[0] > sorted_weights[1] * 1.15:
            hero = sorted_layers[0]
            others = sorted_layers[1:]
            hero_w = sorted_weights[0]
            others_w = sum(sorted_weights[1:])
            frac = max(0.42, min(0.68, hero_w / (hero_w + others_w)))

            w_h = max(10.0, (rw - gap) * frac)
            w_sub = max(10.0, rw - gap - w_h)
            h_h = max(10.0, (rh - gap) * frac)
            h_sub = max(10.0, rh - gap - h_h)

            # Hero Left
            candidates.append([(hero, (rx, ry, w_h, rh))] + cls._layout_as_grid((rx + w_h + gap, ry, w_sub, rh), others, gap))

            # Hero Right
            candidates.append([(hero, (rx + w_sub + gap, ry, w_h, rh))] + cls._layout_as_grid((rx, ry, w_sub, rh), others, gap))

            # Hero Top
            candidates.append([(hero, (rx, ry, rw, h_h))] + cls._layout_as_grid((rx, ry + h_h + gap, rw, h_sub), others, gap))

            # Triptych (Hero Center, 2 others flanking on sides) if n == 3
            if n == 3:
                w_hc = max(10.0, (rw - 2.0 * gap) * frac)
                w_side = max(10.0, (rw - 2.0 * gap - w_hc) / 2.0)
                candidates.append([
                    (others[0], (rx, ry, w_side, rh)),
                    (hero, (rx + w_side + gap, ry, w_hc, rh)),
                    (others[1], (rx + w_side + gap + w_hc + gap, ry, w_side, rh)),
                ])

        # Pick best candidate based on aspect ratio match & sliver minimization
        return min(candidates, key=cls._score_candidate)

    def _layout_subset_in_rect(
        self,
        layers: List[Layer],
        rx: float,
        ry: float,
        rw: float,
        rh: float,
        mode: str,
        margin: float,
        gap: float,
        cover: bool = False,
    ) -> None:
        """Arrange a subset of layers inside a bounding rectangle."""
        n = len(layers)
        if n == 0:
            return

        m = max(0.0, min(margin, min(rw, rh) / 2.0 - 5.0))
        avail_w = max(20.0, rw - (2.0 * m))
        avail_h = max(20.0, rh - (2.0 * m))
        g = max(0.0, min(gap, 300.0))

        if mode == "dynamic":
            placements = self._solve_dynamic_layout((rx + m, ry + m, avail_w, avail_h), layers, g)
            for layer, (cell_x, cell_y, cell_w, cell_h) in placements:
                layer.reset_rotation()
                eff_cell_w = max(10.0, cell_w - (2.0 * layer.border_width))
                eff_cell_h = max(10.0, cell_h - (2.0 * layer.border_width))
                layer.fit_into(eff_cell_w, eff_cell_h, cover=cover)
                layer.x = cell_x + (cell_w / 2.0)
                layer.y = cell_y + (cell_h / 2.0)
            return

        elif mode == "row":
            weights = self._compute_layer_weights(layers)
            total_w = sum(weights)
            avail_item_w = max(10.0, avail_w - max(0.0, (n - 1) * g))
            x_cursor = rx + m
            for layer, w in zip(layers, weights):
                item_w = max(10.0, avail_item_w * (w / total_w))
                cx = x_cursor + (item_w / 2.0)
                cy = ry + m + (avail_h / 2.0)
                layer.reset_rotation()
                eff_w = max(10.0, item_w - (2.0 * layer.border_width))
                eff_h = max(10.0, avail_h - (2.0 * layer.border_width))
                layer.fit_into(eff_w, eff_h, cover=cover)
                layer.x = cx
                layer.y = cy
                x_cursor += item_w + g
            return

        elif mode == "col":
            weights = self._compute_layer_weights(layers)
            total_w = sum(weights)
            avail_item_h = max(10.0, avail_h - max(0.0, (n - 1) * g))
            y_cursor = ry + m
            for layer, w in zip(layers, weights):
                item_h = max(10.0, avail_item_h * (w / total_w))
                cx = rx + m + (avail_w / 2.0)
                cy = y_cursor + (item_h / 2.0)
                layer.reset_rotation()
                eff_w = max(10.0, avail_w - (2.0 * layer.border_width))
                eff_h = max(10.0, item_h - (2.0 * layer.border_width))
                layer.fit_into(eff_w, eff_h, cover=cover)
                layer.x = cx
                layer.y = cy
                y_cursor += item_h + g
            return

        else:  # "grid" (Classic uniform grid)
            cols, rows = self._calculate_grid_dimensions(n, avail_w, avail_h)
            if cols > 1 and (cols - 1) * g >= avail_w:
                g = max(0.0, (avail_w - 20.0) / (cols - 1))
            if rows > 1 and (rows - 1) * g >= avail_h:
                g = max(0.0, (avail_h - 20.0) / (rows - 1))

            cell_w = max(10.0, (avail_w - ((cols - 1) * g)) / cols)
            cell_h = max(10.0, (avail_h - ((rows - 1) * g)) / rows)

            idx = 0
            for r in range(rows):
                n_in_row = min(cols, n - idx)
                if n_in_row <= 0:
                    break
                row_w = (n_in_row * cell_w) + max(0.0, (n_in_row - 1) * g)
                row_start_x = rx + m + ((avail_w - row_w) / 2.0)
                row_y = ry + m + (r * (cell_h + g))

                for c in range(n_in_row):
                    layer = layers[idx]
                    cx = row_start_x + (c * (cell_w + g)) + (cell_w / 2.0)
                    cy = row_y + (cell_h / 2.0)

                    layer.reset_rotation()
                    eff_cell_w = max(10.0, cell_w - (2.0 * layer.border_width))
                    eff_cell_h = max(10.0, cell_h - (2.0 * layer.border_width))
                    layer.fit_into(eff_cell_w, eff_cell_h, cover=cover)
                    layer.x = cx
                    layer.y = cy

                    idx += 1

    def auto_layout_layers(
        self,
        mode: str = "dynamic",
        margin: float = 40.0,
        gap: float = 20.0,
        cover: bool = False,
    ) -> None:
        """Automatically arrange and resize all visible layers to fit the canvas."""
        active_layers = [l for l in self.layers if l.visible]
        if not active_layers:
            return

        if self.monitor.is_spanned and self.monitor.sub_monitors:
            if mode == "per_monitor":
                subs = sorted(self.monitor.sub_monitors, key=lambda s: (s.rel_x, s.rel_y))
                num_subs = len(subs)
                num_layers = len(active_layers)
                chunks: List[List[Layer]] = [[] for _ in range(num_subs)]
                if num_layers <= num_subs:
                    for i in range(num_layers):
                        chunks[i].append(active_layers[i])
                else:
                    base_count = num_layers // num_subs
                    rem = num_layers % num_subs
                    start_i = 0
                    for i in range(num_subs):
                        count = base_count + (1 if i < rem else 0)
                        chunks[i] = active_layers[start_i : start_i + count]
                        start_i += count

                for sub, sub_layers in zip(subs, chunks):
                    for l in sub_layers:
                        l.monitor_name = sub.name
                    if sub_layers:
                        self._layout_subset_in_rect(
                            sub_layers,
                            0.0,
                            0.0,
                            sub.width,
                            sub.height,
                            "dynamic",
                            margin,
                            gap,
                            cover=cover,
                        )
            else:
                for sub in self.monitor.sub_monitors:
                    sub_layers = [l for l in active_layers if l.monitor_name == sub.name]
                    if sub == self.monitor.sub_monitors[0]:
                        unassigned = [
                            l for l in active_layers
                            if not l.monitor_name or l.monitor_name not in [s.name for s in self.monitor.sub_monitors]
                        ]
                        for ul in unassigned:
                            ul.monitor_name = sub.name
                        sub_layers.extend(unassigned)
                    if sub_layers:
                        self._layout_subset_in_rect(
                            sub_layers,
                            0.0,
                            0.0,
                            sub.width,
                            sub.height,
                            mode,
                            margin,
                            gap,
                            cover=cover,
                        )
        else:
            self._layout_subset_in_rect(
                active_layers,
                0.0,
                0.0,
                self.monitor.width,
                self.monitor.height,
                mode,
                margin,
                gap,
                cover=cover,
            )

        if self.on_selection_changed and self.selected_layer:
            self.on_selection_changed(self.selected_layer)
        if self.on_layers_changed:
            self.on_layers_changed()

        self.queue_draw()

    # -------------------------------------------------------------------------
    # Layer Management
    # -------------------------------------------------------------------------
    def add_layer_from_path(self, path: str, at_cx: Optional[float] = None, at_cy: Optional[float] = None) -> Optional[Layer]:
        """Load an image and add it as a new layer to the canvas."""
        try:
            layer = Layer(file_path=path)
            # Inherit active persistent styling for border & shadow
            self.apply_default_style_to_layer(layer)

            if self.monitor.is_spanned and self.monitor.sub_monitors:
                if at_cx is not None:
                    sub = self.get_closest_sub_monitor_at_point(at_cx, at_cy if at_cy is not None else 0.0)
                    local_x = at_cx - sub.rel_x
                    local_y = (at_cy - sub.rel_y) if at_cy is not None else (sub.height / 2.0)
                else:
                    sub = self.active_sub_monitor or self.monitor.sub_monitors[0]
                    local_x = sub.width / 2.0
                    local_y = sub.height / 2.0
                layer.monitor_name = sub.name
                layer.x = local_x
                layer.y = local_y
                layer.fit_into(sub.width * 0.7, sub.height * 0.7)
            else:
                layer.monitor_name = self.monitor.name
                if at_cx is None:
                    at_cx = self.monitor.width / 2.0
                if at_cy is None:
                    at_cy = self.monitor.height / 2.0
                layer.x = at_cx
                layer.y = at_cy
                layer.fit_into(self.monitor.width * 0.7, self.monitor.height * 0.7)

            if layer not in self.all_layers:
                self.all_layers.append(layer)
            if layer not in self.layers:
                self.layers.append(layer)
            self.select_layer(layer)

            if self.on_layers_changed:
                self.on_layers_changed()

            self.queue_draw()
            return layer
        except Exception as e:
            print(f"Error adding layer from {path}: {e}")
            return None

    def select_layer(self, layer: Optional[Layer], add: bool = False):
        """Select a single layer, or add it to selection if add=True."""
        if layer is None:
            self.clear_selection()
            return
        if add:
            if layer not in self._selected_layers:
                self._selected_layers.append(layer)
        else:
            self._selected_layers = [layer]
        if self.on_selection_changed:
            self.on_selection_changed(self.selected_layer)
        self.queue_draw()

    def select_layers(self, layers: List[Layer]):
        """Select multiple layers at once."""
        self._selected_layers = [l for l in layers if l in self.layers]
        if self.on_selection_changed:
            self.on_selection_changed(self.selected_layer)
        self.queue_draw()

    def toggle_layer_selection(self, layer: Layer):
        """Toggle a layer in or out of the current multi-selection."""
        if layer in self._selected_layers:
            self._selected_layers.remove(layer)
        else:
            self._selected_layers.append(layer)
        if self.on_selection_changed:
            self.on_selection_changed(self.selected_layer)
        self.queue_draw()

    def select_all_layers(self):
        """Select all visible layers on the canvas."""
        self._selected_layers = [l for l in self.layers if l.visible]
        if self.on_selection_changed:
            self.on_selection_changed(self.selected_layer)
        self.queue_draw()

    def clear_selection(self):
        """Deselect all layers."""
        if self._selected_layers:
            self._selected_layers.clear()
            if self.on_selection_changed:
                self.on_selection_changed(None)
            self.queue_draw()

    def remove_layer(self, layer: Layer):
        if layer in self.all_layers:
            self.all_layers.remove(layer)
        if layer in self.layers:
            self.layers.remove(layer)
            if layer in self._selected_layers:
                self._selected_layers.remove(layer)
                if self.on_selection_changed:
                    self.on_selection_changed(self.selected_layer)
            if self.on_layers_changed:
                self.on_layers_changed()
            self.queue_draw()

    def remove_selected_layers(self):
        """Remove all currently selected layers."""
        if not self._selected_layers:
            return
        to_remove = list(self._selected_layers)
        for layer in to_remove:
            if layer in self.all_layers:
                self.all_layers.remove(layer)
            if layer in self.layers:
                self.layers.remove(layer)
        self._selected_layers.clear()
        if self.layers:
            self.select_layer(self.layers[-1])
        else:
            if self.on_selection_changed:
                self.on_selection_changed(None)
        if self.on_layers_changed:
            self.on_layers_changed()
        self.queue_draw()

    def move_layer_up(self, layer: Layer):
        idx = self.layers.index(layer)
        if idx < len(self.layers) - 1:
            self.layers[idx], self.layers[idx + 1] = self.layers[idx + 1], self.layers[idx]
            if self.on_layers_changed:
                self.on_layers_changed()
            self.queue_draw()

    def move_layer_down(self, layer: Layer):
        idx = self.layers.index(layer)
        if idx > 0:
            self.layers[idx], self.layers[idx - 1] = self.layers[idx - 1], self.layers[idx]
            if self.on_layers_changed:
                self.on_layers_changed()
            self.queue_draw()

    def move_layer_to_front(self, layer: Layer):
        if layer in self.layers:
            self.layers.remove(layer)
            self.layers.append(layer)
            if self.on_layers_changed:
                self.on_layers_changed()
            self.queue_draw()

    def move_layer_to_back(self, layer: Layer):
        if layer in self.layers:
            self.layers.remove(layer)
            self.layers.insert(0, layer)
            if self.on_layers_changed:
                self.on_layers_changed()
            self.queue_draw()

    def move_selected_layers_to_front(self):
        """Move all selected layers to the very front."""
        if not self._selected_layers:
            return
        for layer in self._selected_layers:
            if layer in self.layers:
                self.layers.remove(layer)
                self.layers.append(layer)
        if self.on_layers_changed:
            self.on_layers_changed()
        self.queue_draw()

    def move_selected_layers_to_back(self):
        """Move all selected layers to the very back."""
        if not self._selected_layers:
            return
        for layer in reversed(self._selected_layers):
            if layer in self.layers:
                self.layers.remove(layer)
                self.layers.insert(0, layer)
        if self.on_layers_changed:
            self.on_layers_changed()
        self.queue_draw()

    def move_selected_layers_up(self):
        """Move selected layers one step up."""
        if not self._selected_layers:
            return
        for layer in reversed(self.layers):
            if layer in self._selected_layers:
                idx = self.layers.index(layer)
                if idx < len(self.layers) - 1 and self.layers[idx + 1] not in self._selected_layers:
                    self.layers[idx], self.layers[idx + 1] = self.layers[idx + 1], self.layers[idx]
        if self.on_layers_changed:
            self.on_layers_changed()
        self.queue_draw()

    def move_selected_layers_down(self):
        """Move selected layers one step down."""
        if not self._selected_layers:
            return
        for layer in self.layers:
            if layer in self._selected_layers:
                idx = self.layers.index(layer)
                if idx > 0 and self.layers[idx - 1] not in self._selected_layers:
                    self.layers[idx], self.layers[idx - 1] = self.layers[idx - 1], self.layers[idx]
        if self.on_layers_changed:
            self.on_layers_changed()
        self.queue_draw()

    def set_background_color(self, rgb: Tuple[int, int, int]):
        self.bg_color = rgb
        if self.on_bg_color_changed:
            self.on_bg_color_changed(rgb)
        self.queue_draw()

    # -------------------------------------------------------------------------
    # Mouse & Gesture Event Handlers
    # -------------------------------------------------------------------------
    def _on_button_pressed(self, gesture: Gtk.GestureClick, n_press: int, wx: float, wy: float):
        self.grab_focus()
        btn = gesture.get_current_button()
        cx, cy = self.widget_to_canvas(wx, wy)

        # Middle mouse button or right click initiates panning
        if btn == Gdk.BUTTON_MIDDLE or btn == Gdk.BUTTON_SECONDARY:
            self.is_panning = True
            self.drag_start_mouse = (wx, wy)
            self.drag_start_pan = (self.pan_x, self.pan_y)
            self.set_cursor_from_name("grabbing")
            return

        if btn == Gdk.BUTTON_PRIMARY:
            state = gesture.get_current_event_state()
            is_multi = bool(state & (Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK))

            # 1. If only 1 layer selected and not holding shift/ctrl, check handle click
            if len(self._selected_layers) == 1 and not is_multi and self.selected_layer is not None:
                layer = self.selected_layer
                tol = max(6.0, 10.0 / self.zoom)
                lx, ly = self.get_layer_local_coords(layer, cx, cy)
                handle = layer.get_handle_at(lx, ly, tolerance=tol)
                if handle is not None:
                    self.active_handle = handle
                    self.drag_start_mouse = (cx, cy)
                    self.drag_start_layer_pos = self.get_layer_canvas_pos(layer)
                    self.drag_start_layer_size = (layer.width, layer.height)
                    return

            # 2. Check if clicked on any layer (topmost first)
            hit_layer = None
            for layer in reversed(self.layers):
                lx, ly = self.get_layer_local_coords(layer, cx, cy)
                if layer.contains_point(lx, ly):
                    hit_layer = layer
                    break

            if hit_layer is not None:
                if is_multi:
                    self.toggle_layer_selection(hit_layer)
                else:
                    if hit_layer not in self._selected_layers:
                        self.select_layer(hit_layer)
                    # If hit_layer is already in self._selected_layers, keep the multi-selection for dragging

                if hit_layer in self._selected_layers:
                    self.is_dragging_layer = True
                    self.drag_start_mouse = (cx, cy)
                    self.drag_start_multi_positions = {l: (l.x, l.y) for l in self._selected_layers}
                    self.drag_start_multi_canvas_positions = {l: self.get_layer_canvas_pos(l) for l in self._selected_layers}
            else:
                # Clicked empty space: start rubberband selection
                if not is_multi:
                    self.clear_selection()
                    self.rubberband_base_selection = []
                else:
                    self.rubberband_base_selection = list(self._selected_layers)

                self.is_rubberband = True
                self.rubberband_start = (cx, cy)
                self.rubberband_current = (cx, cy)

    def _on_button_released(self, gesture: Gtk.GestureClick, n_press: int, wx: float, wy: float):
        self.active_handle = None
        self.is_dragging_layer = False
        self.is_rubberband = False
        self.is_panning = False
        self.set_cursor_from_name("default")
        self.queue_draw()

    def _on_drag_begin(self, gesture: Gtk.GestureDrag, start_x: float, start_y: float):
        pass

    def _on_drag_update(self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float):
        wx = gesture.get_start_point()[1] + offset_x
        wy = gesture.get_start_point()[2] + offset_y
        cx, cy = self.widget_to_canvas(wx, wy)

        # 1. Canvas Panning
        if self.is_panning:
            start_wx, start_wy = self.drag_start_mouse
            dx = wx - start_wx
            dy = wy - start_wy
            self.pan_x = self.drag_start_pan[0] + dx
            self.pan_y = self.drag_start_pan[1] + dy
            self.user_panned_or_zoomed = True
            self.queue_draw()
            return

        # 2. Rubberband Selection
        if self.is_rubberband:
            self.rubberband_current = (cx, cy)
            rx = min(self.rubberband_start[0], cx)
            ry = min(self.rubberband_start[1], cy)
            rw = abs(cx - self.rubberband_start[0])
            rh = abs(cy - self.rubberband_start[1])

            # Hit-test all visible layers
            hit_layers = []
            for l in self.layers:
                sub_ox, sub_oy = (0.0, 0.0)
                if self.monitor.is_spanned and self.monitor.sub_monitors:
                    sub = self.get_sub_monitor_for_layer(l)
                    if sub is not None:
                        sub_ox, sub_oy = sub.rel_x, sub.rel_y
                if l.intersects_rect(rx - sub_ox, ry - sub_oy, rw, rh):
                    hit_layers.append(l)

            new_selection = list(self.rubberband_base_selection)
            for hl in hit_layers:
                if hl not in new_selection:
                    new_selection.append(hl)

            self._selected_layers = new_selection
            if self.on_selection_changed:
                self.on_selection_changed(self.selected_layer)
            self.queue_draw()
            return

        # 3. Moving selected layer(s)
        if self.is_dragging_layer and self._selected_layers:
            start_cx, start_cy = self.drag_start_mouse
            dx = cx - start_cx
            dy = cy - start_cy
            for layer in self._selected_layers:
                if layer in self.drag_start_multi_canvas_positions:
                    orig_cx, orig_cy = self.drag_start_multi_canvas_positions[layer]
                    self.set_layer_canvas_pos(layer, orig_cx + dx, orig_cy + dy)
                elif layer in self.drag_start_multi_positions:
                    orig_x, orig_y = self.drag_start_multi_positions[layer]
                    layer.x = orig_x + dx
                    layer.y = orig_y + dy
            if self.on_selection_changed and self.selected_layer:
                self.on_selection_changed(self.selected_layer)
            self.queue_draw()
            return

        # 4. Handle Transform (Resize / Rotate)
        if self.active_handle is not None and self.selected_layer is not None:
            layer = self.selected_layer
            lx, ly = self.get_layer_local_coords(layer, cx, cy)

            # Rotation
            if self.active_handle.handle_type == HandleType.ROTATE:
                v_x = lx - layer.x
                v_y = ly - layer.y
                angle_rad = math.atan2(v_y, v_x)
                deg = (math.degrees(angle_rad) + 90.0) % 360.0
                for snap_deg in [0.0, 90.0, 180.0, 270.0, 360.0]:
                    if abs(deg - snap_deg) < 4.0:
                        deg = snap_deg % 360.0
                        break
                layer.rotation = deg
                if self.on_selection_changed:
                    self.on_selection_changed(layer)
                self.queue_draw()
                return

            # Resizing
            rel_lx, rel_ly = layer.to_layer_coords(lx, ly)
            orig_aspect = layer.aspect_ratio if layer.aspect_ratio > 0 else 1.0

            ht = self.active_handle.handle_type
            if ht in [HandleType.TOP_LEFT, HandleType.TOP_RIGHT, HandleType.BOTTOM_LEFT, HandleType.BOTTOM_RIGHT]:
                dist = math.sqrt(rel_lx ** 2 + rel_ly ** 2)
                orig_diag = math.sqrt((orig_aspect ** 2) + 1.0)
                new_h = max(20.0, (dist * 2.0) / orig_diag)
                new_w = new_h * orig_aspect
                layer.width = new_w
                layer.height = new_h
            elif ht in [HandleType.LEFT, HandleType.RIGHT]:
                new_w = max(20.0, abs(rel_lx) * 2.0)
                layer.width = new_w
                layer.height = new_w / orig_aspect
            elif ht in [HandleType.TOP, HandleType.BOTTOM]:
                new_h = max(20.0, abs(rel_ly) * 2.0)
                layer.height = new_h
                layer.width = new_h * orig_aspect

            if self.on_selection_changed:
                self.on_selection_changed(layer)
            self.queue_draw()

    def _on_drag_end(self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float):
        self.active_handle = None
        self.is_dragging_layer = False
        self.is_rubberband = False
        self.is_panning = False
        self.set_cursor_from_name("default")
        self.queue_draw()

    def _on_mouse_motion(self, controller: Gtk.EventControllerMotion, wx: float, wy: float):
        cx, cy = self.widget_to_canvas(wx, wy)

        if self.is_panning:
            self.set_cursor_from_name("grabbing")
            return

        if len(self._selected_layers) == 1 and self.selected_layer is not None:
            layer = self.selected_layer
            tol = max(6.0, 10.0 / self.zoom)
            lx, ly = self.get_layer_local_coords(layer, cx, cy)
            handle = layer.get_handle_at(lx, ly, tolerance=tol)
            if handle is not None:
                ht = handle.handle_type
                if ht in [HandleType.TOP_LEFT, HandleType.BOTTOM_RIGHT]:
                    self.set_cursor_from_name("nwse-resize")
                elif ht in [HandleType.TOP_RIGHT, HandleType.BOTTOM_LEFT]:
                    self.set_cursor_from_name("nesw-resize")
                elif ht in [HandleType.TOP, HandleType.BOTTOM]:
                    self.set_cursor_from_name("ns-resize")
                elif ht in [HandleType.LEFT, HandleType.RIGHT]:
                    self.set_cursor_from_name("ew-resize")
                elif ht == HandleType.ROTATE:
                    self.set_cursor_from_name("grab")
                return

        # Check if hovering over any layer
        for layer in reversed(self.layers):
            lx, ly = self.get_layer_local_coords(layer, cx, cy)
            if layer.contains_point(lx, ly):
                self.set_cursor_from_name("move")
                return

        self.set_cursor_from_name("default")

    def _on_scroll(self, controller: Gtk.EventControllerScroll, dx: float, dy: float) -> bool:
        zoom_factor = 1.15 if dy < 0 else (1.0 / 1.15)
        alloc = self.get_allocation()
        center_x = alloc.width / 2.0
        center_y = alloc.height / 2.0
        self.set_zoom_centered(self.zoom * zoom_factor, center_x, center_y)
        return True

    def _on_key_pressed(self, controller: Gtk.EventControllerKey, keyval: int, keycode: int, state: Gdk.ModifierType) -> bool:
        # Handle Ctrl+A (Select All)
        if (state & Gdk.ModifierType.CONTROL_MASK) and keyval in [Gdk.KEY_a, Gdk.KEY_A]:
            self.select_all_layers()
            return True

        # Handle Ctrl+V (Paste)
        if (state & Gdk.ModifierType.CONTROL_MASK) and keyval in [Gdk.KEY_v, Gdk.KEY_V]:
            if self.on_paste_requested:
                self.on_paste_requested()
                return True

        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)
        step = 10.0 if shift_pressed else 1.0

        if self._selected_layers:
            if keyval == Gdk.KEY_Left:
                for l in self._selected_layers:
                    l.x -= step
                self.queue_draw()
                return True
            elif keyval == Gdk.KEY_Right:
                for l in self._selected_layers:
                    l.x += step
                self.queue_draw()
                return True
            elif keyval == Gdk.KEY_Up:
                for l in self._selected_layers:
                    l.y -= step
                self.queue_draw()
                return True
            elif keyval == Gdk.KEY_Down:
                for l in self._selected_layers:
                    l.y += step
                self.queue_draw()
                return True
            elif keyval in [Gdk.KEY_Delete, Gdk.KEY_BackSpace]:
                self.remove_selected_layers()
                return True

        if keyval == Gdk.KEY_Escape:
            self.clear_selection()
            return True

        return False

    def _on_file_list_drop(self, target: Gtk.DropTarget, file_list: Gdk.FileList, x: float, y: float) -> bool:
        files = file_list.get_files()
        cx, cy = self.widget_to_canvas(x, y)
        loaded = False
        for f in files:
            path = f.get_path()
            if path and self._is_image_path(path):
                self.add_layer_from_path(path, at_cx=cx, at_cy=cy)
                loaded = True
        return loaded

    def _on_single_file_drop(self, target: Gtk.DropTarget, file: Gio.File, x: float, y: float) -> bool:
        path = file.get_path()
        if path and self._is_image_path(path):
            cx, cy = self.widget_to_canvas(x, y)
            self.add_layer_from_path(path, at_cx=cx, at_cy=cy)
            return True
        return False

    @staticmethod
    def _is_image_path(path: str) -> bool:
        valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".bmp", ".gif", ".tiff"}
        ext = path.lower()[path.rfind("."):] if "." in path else ""
        return ext in valid_exts

    # -------------------------------------------------------------------------
    # Cairo Drawing Routine
    # -------------------------------------------------------------------------
    def _draw_single_layer(self, cr: cairo.Context, layer: Layer, canvas_x: float, canvas_y: float):
        """Render a single layer including its shadow and border at the given canvas coordinates."""
        # Draw Drop Shadow (underneath image)
        if layer.shadow_enabled and layer.shadow_blur > 0 and layer.shadow_opacity > 0:
            shadow_surf = layer.get_shadow_surface()
            if shadow_surf is not None:
                sw = shadow_surf.get_width()
                sh = shadow_surf.get_height()
                cr.save()
                cr.translate(canvas_x + layer.shadow_offset_x, canvas_y + layer.shadow_offset_y)
                cr.rotate(math.radians(layer.rotation))
                cr.set_source_surface(shadow_surf, -sw / 2.0, -sh / 2.0)
                cr.paint_with_alpha(layer.opacity)
                cr.restore()

        surf = layer.cairo_surface
        if surf is None:
            return

        orig_w = surf.get_width()
        orig_h = surf.get_height()
        if orig_w <= 0 or orig_h <= 0:
            return

        cr.save()
        cr.translate(canvas_x, canvas_y)
        cr.rotate(math.radians(layer.rotation))

        hw = layer.width / 2.0
        hh = layer.height / 2.0
        bw = layer.border_width
        bradius = layer.border_radius

        # Draw image (clipped if rounded corners)
        if bradius > 0:
            cr.save()
            self._draw_rounded_rect_path(cr, -hw, -hh, layer.width, layer.height, bradius)
            cr.clip()
            cr.scale(layer.width / orig_w, layer.height / orig_h)
            cr.set_source_surface(surf, -orig_w / 2.0, -orig_h / 2.0)
            cr.paint_with_alpha(layer.opacity)
            cr.restore()
        else:
            cr.save()
            cr.scale(layer.width / orig_w, layer.height / orig_h)
            cr.set_source_surface(surf, -orig_w / 2.0, -orig_h / 2.0)
            cr.paint_with_alpha(layer.opacity)
            cr.restore()

        # Render border frame if border_width > 0
        if bw > 0:
            br, bg, bb = layer.border_color
            cr.set_source_rgba(br / 255.0, bg / 255.0, bb / 255.0, layer.opacity)
            cr.set_line_width(bw)
            if bradius > 0:
                self._draw_rounded_rect_path(
                    cr,
                    -hw - (bw / 2.0),
                    -hh - (bw / 2.0),
                    layer.width + bw,
                    layer.height + bw,
                    bradius + (bw / 2.0),
                )
            else:
                cr.rectangle(
                    -hw - (bw / 2.0),
                    -hh - (bw / 2.0),
                    layer.width + bw,
                    layer.height + bw,
                )
            cr.stroke()

        cr.restore()

    def _on_draw(self, area: Gtk.DrawingArea, cr: cairo.Context, width: int, height: int):
        # Auto-fit on first draw if user hasn't explicitly navigated
        if not self.user_panned_or_zoomed and (abs(self.pan_x) < 0.01 and abs(self.pan_y) < 0.01):
            self.fit_to_view()

        # 1. Fill entire widget background with dark desk/workspace (#11111b)
        cr.set_source_rgb(0.07, 0.07, 0.11)
        cr.paint()

        # 2. Setup Canvas viewport transformation
        cr.save()
        cr.translate(self.pan_x, self.pan_y)
        cr.scale(self.zoom, self.zoom)

        # 3. Determine monitor list (Sub-monitors if spanned, otherwise single monitor)
        if self.monitor.is_spanned and self.monitor.sub_monitors:
            mon_list = self.monitor.sub_monitors
        else:
            mon_list = [self.monitor]

        # Draw soft shadow behind each monitor housing
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.55)
        for sub in mon_list:
            rx = sub.rel_x if self.monitor.is_spanned else 0.0
            ry = sub.rel_y if self.monitor.is_spanned else 0.0
            bezel = 18.0 / max(0.2, self.zoom)
            shadow_off = 10.0 / max(0.2, self.zoom)
            self._draw_rounded_rect_path(
                cr,
                rx - bezel,
                ry - bezel + shadow_off,
                sub.width + (bezel * 2.0),
                sub.height + (bezel * 2.0),
                16.0 / max(0.2, self.zoom),
            )
            cr.fill()

        # Draw monitor chassis and screen area for each monitor
        bg_r, bg_g, bg_b = self.bg_color
        for sub in mon_list:
            rx = sub.rel_x if self.monitor.is_spanned else 0.0
            ry = sub.rel_y if self.monitor.is_spanned else 0.0
            bezel = 18.0 / max(0.2, self.zoom)
            r_outer = 16.0 / max(0.2, self.zoom)

            # Bezel body (Dark sleek chassis #1e1e2e)
            cr.set_source_rgb(0.12, 0.12, 0.18)
            self._draw_rounded_rect_path(
                cr,
                rx - bezel,
                ry - bezel,
                sub.width + (bezel * 2.0),
                sub.height + (bezel * 2.0),
                r_outer,
            )
            cr.fill_preserve()

            # Bezel highlight border (#313244)
            cr.set_source_rgba(0.35, 0.42, 0.65, 0.8)
            cr.set_line_width(2.0 / self.zoom)
            cr.stroke()

            # Screen area fill (User selected bg_color)
            cr.set_source_rgb(bg_r / 255.0, bg_g / 255.0, bg_b / 255.0)
            cr.rectangle(rx, ry, sub.width, sub.height)
            cr.fill_preserve()

            # Subtle inner screen border
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.35)
            cr.set_line_width(1.0 / self.zoom)
            cr.stroke()

            # Monitor title badge
            if getattr(sub, "is_custom", False):
                badge_text = tr("canvas_badge_custom", name=sub.name, w=sub.width, h=sub.height)
            else:
                badge_text = tr("canvas_badge_monitor", name=sub.name, w=sub.width, h=sub.height)
            self._draw_monitor_badge(cr, badge_text, rx + (18.0 / self.zoom), ry + (18.0 / self.zoom))

        # 4. Render Layers (clipped to respective monitor screens)
        for sub in mon_list:
            rx = sub.rel_x if self.monitor.is_spanned else 0.0
            ry = sub.rel_y if self.monitor.is_spanned else 0.0

            cr.save()
            cr.rectangle(rx, ry, sub.width, sub.height)
            cr.clip()

            for layer in self.layers:
                if not layer.visible or layer.width <= 0 or layer.height <= 0:
                    continue
                if self.monitor.is_spanned:
                    sub_for_layer = self.get_sub_monitor_for_layer(layer)
                    if sub_for_layer != sub:
                        continue
                    cx = sub.rel_x + layer.x
                    cy = sub.rel_y + layer.y
                else:
                    cx = layer.x
                    cy = layer.y

                self._draw_single_layer(cr, layer, cx, cy)

            cr.restore()  # Undo clipping

        # 5. Draw Selection Overlays (Bounding box, handles)
        if len(self._selected_layers) == 1 and self.selected_layer is not None and self.selected_layer.visible:
            self._draw_selection_overlay(cr, self.selected_layer)
        elif len(self._selected_layers) > 1:
            for layer in self._selected_layers:
                if layer.visible:
                    self._draw_multi_selection_overlay(cr, layer)

        # 6. Draw Rubberband Selection Box if active
        if self.is_rubberband:
            rx = min(self.rubberband_start[0], self.rubberband_current[0])
            ry = min(self.rubberband_start[1], self.rubberband_current[1])
            rw = abs(self.rubberband_current[0] - self.rubberband_start[0])
            rh = abs(self.rubberband_current[1] - self.rubberband_start[1])

            cr.save()
            cr.set_source_rgba(0.0, 0.82, 1.0, 0.15)
            cr.rectangle(rx, ry, rw, rh)
            cr.fill_preserve()

            cr.set_source_rgba(0.0, 0.82, 1.0, 0.9)
            cr.set_line_width(1.5 / self.zoom)
            cr.set_dash([6.0 / self.zoom, 4.0 / self.zoom])
            cr.stroke()
            cr.restore()

        cr.restore()  # Undo viewport transform

    @staticmethod
    def _draw_rounded_rect_path(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float):
        """Draw rounded rectangle sub-path on cairo context."""
        r = max(0.0, min(r, w / 2.0, h / 2.0))
        if r <= 0:
            cr.rectangle(x, y, w, h)
            return
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2.0, 0.0)
        cr.arc(x + w - r, y + h - r, r, 0.0, math.pi / 2.0)
        cr.arc(x + r, y + h - r, r, math.pi / 2.0, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3.0 * math.pi / 2.0)
        cr.close_path()

    def _draw_selection_overlay(self, cr: cairo.Context, layer: Layer):
        """Draw bounding box, resize handles, and rotation handle in canvas coordinate space."""
        canvas_x, canvas_y = self.get_layer_canvas_pos(layer)
        hw = (layer.width / 2.0) + layer.border_width
        hh = (layer.height / 2.0) + layer.border_width
        total_w = layer.width + (2.0 * layer.border_width)
        total_h = layer.height + (2.0 * layer.border_width)
        lw = 2.0 / self.zoom
        handle_sz = 10.0 / self.zoom

        cr.save()
        cr.translate(canvas_x, canvas_y)
        cr.rotate(math.radians(layer.rotation))

        # Bounding box rectangle (Accent Cyan #00d2ff)
        cr.set_source_rgba(0.0, 0.82, 1.0, 0.9)
        cr.set_line_width(lw)
        if layer.border_radius > 0:
            self._draw_rounded_rect_path(
                cr, -hw, -hh, total_w, total_h, layer.border_radius + layer.border_width
            )
        else:
            cr.rectangle(-hw, -hh, total_w, total_h)
        cr.stroke()

        # Line connecting top edge to rotation handle
        rot_offset = 30.0 / self.zoom
        cr.set_source_rgba(0.0, 0.82, 1.0, 0.7)
        cr.set_line_width(lw)
        cr.move_to(0, -hh)
        cr.line_to(0, -hh - rot_offset)
        cr.stroke()

        # Rotation handle circle
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.arc(0, -hh - rot_offset, handle_sz / 2.0, 0, 2 * math.pi)
        cr.fill_preserve()
        cr.set_source_rgb(0.0, 0.6, 0.9)
        cr.set_line_width(lw)
        cr.stroke()

        # 8 Square resize handles
        handle_positions = [
            (-hw, -hh), (hw, -hh), (-hw, hh), (hw, hh),  # Corners
            (0, -hh), (0, hh), (-hw, 0), (hw, 0),        # Edges
        ]

        for hx, hy in handle_positions:
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.rectangle(hx - (handle_sz / 2.0), hy - (handle_sz / 2.0), handle_sz, handle_sz)
            cr.fill_preserve()
            cr.set_source_rgb(0.0, 0.6, 0.9)
            cr.set_line_width(lw)
            cr.stroke()

        cr.restore()

    def _draw_multi_selection_overlay(self, cr: cairo.Context, layer: Layer):
        """Draw a distinct bounding box and corner tags for a multi-selected layer."""
        canvas_x, canvas_y = self.get_layer_canvas_pos(layer)
        hw = (layer.width / 2.0) + layer.border_width
        hh = (layer.height / 2.0) + layer.border_width
        total_w = layer.width + (2.0 * layer.border_width)
        total_h = layer.height + (2.0 * layer.border_width)
        lw = 2.0 / self.zoom
        corner_sz = 8.0 / self.zoom

        cr.save()
        cr.translate(canvas_x, canvas_y)
        cr.rotate(math.radians(layer.rotation))

        # Cyan bounding box
        cr.set_source_rgba(0.0, 0.82, 1.0, 0.9)
        cr.set_line_width(lw)
        if layer.border_radius > 0:
            self._draw_rounded_rect_path(
                cr, -hw, -hh, total_w, total_h, layer.border_radius + layer.border_width
            )
        else:
            cr.rectangle(-hw, -hh, total_w, total_h)
        cr.stroke()

        # Corner markers
        corners = [(-hw, -hh), (hw, -hh), (-hw, hh), (hw, hh)]
        for cx, cy in corners:
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.rectangle(cx - (corner_sz / 2.0), cy - (corner_sz / 2.0), corner_sz, corner_sz)
            cr.fill_preserve()
            cr.set_source_rgb(0.0, 0.6, 0.9)
            cr.set_line_width(lw)
            cr.stroke()

        cr.restore()


    def _draw_monitor_badge(self, cr: cairo.Context, text: str, x: float, y: float):
        """Draw a sleek monitor identification badge in canvas coordinates."""
        cr.save()
        font_sz = max(8.0, 14.0 / self.zoom)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(font_sz)
        ext = cr.text_extents(text)

        pad_x = 10.0 / self.zoom
        pad_y = 6.0 / self.zoom
        bw = ext.width + (pad_x * 2)
        bh = ext.height + (pad_y * 2)

        # Background pill
        cr.set_source_rgba(0.08, 0.09, 0.14, 0.85)
        self._draw_rounded_rect_path(cr, x, y, bw, bh, 6.0 / self.zoom)
        cr.fill_preserve()

        # Border
        cr.set_source_rgba(0.35, 0.52, 0.9, 0.8)
        cr.set_line_width(1.5 / self.zoom)
        cr.stroke()

        # Text
        cr.set_source_rgb(0.92, 0.94, 1.0)
        cr.move_to(x + pad_x - ext.x_bearing, y + pad_y - ext.y_bearing)
        cr.show_text(text)
        cr.restore()

    def _draw_divider_badge(self, cr: cairo.Context, text: str, cx: float, cy: float):
        """Draw an informative boundary badge centered on the dividing line between monitors."""
        cr.save()
        font_sz = max(9.0, 13.0 / self.zoom)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(font_sz)
        ext = cr.text_extents(text)

        pad_x = 12.0 / self.zoom
        pad_y = 6.0 / self.zoom
        bw = ext.width + (pad_x * 2)
        bh = ext.height + (pad_y * 2)
        bx = cx - (bw / 2.0)
        by = cy - (bh / 2.0)

        # Background pill
        cr.set_source_rgba(0.05, 0.08, 0.15, 0.92)
        self._draw_rounded_rect_path(cr, bx, by, bw, bh, 8.0 / self.zoom)
        cr.fill_preserve()

        # Border (Cyan #00d2ff)
        cr.set_source_rgba(0.0, 0.85, 1.0, 0.95)
        cr.set_line_width(2.0 / self.zoom)
        cr.stroke()

        # Text
        cr.set_source_rgb(0.0, 0.85, 1.0)
        cr.move_to(bx + pad_x - ext.x_bearing, by + pad_y - ext.y_bearing)
        cr.show_text(text)
        cr.restore()
