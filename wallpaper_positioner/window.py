"""Main application window using GTK4 and Libadwaita."""

from __future__ import annotations

import os
from typing import Optional, List, Tuple
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gdk, Adw, Gio, GLib

from .models import Layer
from .monitor_manager import MonitorManager, MonitorInfo
from .color_engine import (
    ColorEngine,
    rgb_to_hex,
    hex_to_rgb,
    rgb_to_gdk_rgba,
    gdk_rgba_to_rgb,
)
from .wallpaper_setter import WallpaperSetter
from .canvas import WallpaperCanvas
from .clipboard_manager import ClipboardManager
from .project_manager import ProjectManager
from .i18n import tr, set_language, get_language


class WallpaperWindow(Adw.ApplicationWindow):
    """Main window for Wallpaper Positioner."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._setup_icon_theme()
        self.set_title(tr("app_title"))
        self.set_default_size(1280, 820)

        self.monitor_manager = MonitorManager()
        self.current_monitor = self.monitor_manager.monitors[0]

        # Active project tracking
        self.current_project_path: Optional[str] = None

        # Auto adapt background color state (False by default so background color only changes on button click)
        self.auto_adapt_bg = False
        self.current_dominant_palette: List[Tuple[int, int, int]] = []

        # Auto-layout and spacing state
        self.current_layout_mode: str = "dynamic"
        self.layout_margin: float = 40.0
        self.layout_gap: float = 20.0
        self.layout_cover: bool = False

        # Internal flag to prevent infinite callback loops during UI updates
        self._updating_ui = False

        self.connect("close-request", self._on_window_close_request)
        self._setup_css()
        self._build_ui()
        self._refresh_palette()

        # Restore last editing session if available
        app = self.get_application()
        has_initial_cli_files = bool(getattr(app, "initial_files", None))
        if not has_initial_cli_files:
            last_session = ProjectManager.load_session()
            if last_session and last_session.get("layers"):
                self._apply_project_data(last_session, is_session_restore=True)

    def _setup_icon_theme(self):
        d = Gdk.Display.get_default()
        if d:
            it = Gtk.IconTheme.get_for_display(d)
            settings = Gtk.Settings.get_default()
            # If current icon theme lacks standard action icons, fall back to Adwaita
            if not it.has_icon("document-new-symbolic"):
                settings.set_property("gtk-icon-theme-name", "Adwaita")

    @classmethod
    def _get_icon(cls, *names: str) -> str:
        d = Gdk.Display.get_default()
        if d:
            it = Gtk.IconTheme.get_for_display(d)
            for n in names:
                if it.has_icon(n):
                    return n
        return names[0] if names else ""

    def _setup_css(self):
        css = """
        .canvas-container {
            background-color: #11111b;
        }
        .canvas-status-badge {
            background-color: rgba(30, 30, 46, 0.85);
            color: #cdd6f4;
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 12px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .palette-chip {
            min-width: 32px;
            min-height: 32px;
            border-radius: 6px;
            border: 2px solid rgba(255, 255, 255, 0.25);
            padding: 0;
            margin: 2px;
            transition: all 150ms ease;
        }
        .palette-chip:hover {
            border-color: #00d2ff;
            transform: scale(1.08);
        }
        .sidebar-section {
            background-color: alpha(@window_bg_color, 0.4);
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 12px;
        }
        .sidebar-title {
            font-weight: bold;
            font-size: 13px;
            color: @accent_color;
            margin-bottom: 6px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_ui(self):
        # Toast overlay for notifications
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        # Root box
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(root_box)

        # Header bar
        header_bar = self._create_header_bar()
        root_box.append(header_bar)

        # Split view: Canvas (left) and Sidebar (right)
        self.split_view = Adw.OverlaySplitView()
        self.split_view.set_sidebar_position(Gtk.PackType.END)
        self.split_view.set_min_sidebar_width(340)
        self.split_view.set_max_sidebar_width(420)
        self.split_view.set_sidebar_width_fraction(0.28)
        self.split_view.set_show_sidebar(True)
        root_box.append(self.split_view)

        # 1. Canvas View
        canvas_overlay = Gtk.Overlay()
        canvas_overlay.add_css_class("canvas-container")

        self.canvas = WallpaperCanvas(self.current_monitor)
        self.canvas.on_selection_changed = self._on_canvas_selection_changed
        self.canvas.on_layers_changed = self._on_canvas_layers_changed
        self.canvas.on_bg_color_changed = self._on_canvas_bg_color_changed
        self.canvas.on_paste_requested = self.paste_clipboard
        canvas_overlay.set_child(self.canvas)

        # Window-level shortcut controller (Ctrl+V paste works everywhere)
        win_key_ctrl = Gtk.EventControllerKey.new()
        win_key_ctrl.connect("key-pressed", self._on_window_key_pressed)
        self.add_controller(win_key_ctrl)

        # Overlay status bar at bottom of canvas
        self.status_bar = self._create_canvas_status_overlay()
        canvas_overlay.add_overlay(self.status_bar)

        self.split_view.set_content(canvas_overlay)

        # 2. Sidebar View
        self.sidebar_scroll = Gtk.ScrolledWindow()
        self.sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.sidebar_box = self._create_sidebar()
        self.sidebar_scroll.set_child(self.sidebar_box)

        self.split_view.set_sidebar(self.sidebar_scroll)

    def _create_header_bar(self) -> Adw.HeaderBar:
        header = Adw.HeaderBar()

        # Monitor selector dropdown
        self.monitor_dropdown = Gtk.DropDown()
        self._update_monitor_dropdown_items()
        self.monitor_dropdown.connect("notify::selected", self._on_monitor_selected)
        header.pack_start(self.monitor_dropdown)

        # Project actions (Neu, Öffnen, Speichern)
        proj_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        proj_box.add_css_class("linked")

        self.btn_new = Gtk.Button(icon_name=self._get_icon("document-new-symbolic", "list-add-symbolic"))
        self.btn_new.set_tooltip_text(tr("new_project"))
        self.btn_new.connect("clicked", lambda b: self.new_project())
        proj_box.append(self.btn_new)

        self.btn_open = Gtk.Button(icon_name=self._get_icon("document-open-symbolic"))
        self.btn_open.set_tooltip_text(tr("open_project"))
        self.btn_open.connect("clicked", lambda b: self.open_project_dialog())
        proj_box.append(self.btn_open)

        self.btn_save = Gtk.Button(icon_name=self._get_icon("document-save-symbolic"))
        self.btn_save.set_tooltip_text(tr("save_project"))
        self.btn_save.connect("clicked", lambda b: self.save_project())
        proj_box.append(self.btn_save)

        header.pack_start(proj_box)

        # Add image button
        self.btn_add = Gtk.Button(icon_name=self._get_icon("list-add-symbolic"))
        self.btn_add.set_tooltip_text(tr("add_images"))
        self.btn_add.connect("clicked", self._on_add_image_clicked)
        header.pack_start(self.btn_add)

        # Paste image button
        self.btn_paste = Gtk.Button(icon_name=self._get_icon("edit-paste-symbolic"))
        self.btn_paste.set_tooltip_text(tr("paste_clipboard"))
        self.btn_paste.connect("clicked", lambda b: self.paste_clipboard())
        header.pack_start(self.btn_paste)

        # Rescan monitors button
        self.btn_rescan = Gtk.Button(icon_name=self._get_icon("view-refresh-symbolic"))
        self.btn_rescan.set_tooltip_text(tr("rescan_monitors"))
        self.btn_rescan.connect("clicked", self._on_rescan_monitors_clicked)
        header.pack_start(self.btn_rescan)

        # Zoom buttons
        zoom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        zoom_box.add_css_class("linked")

        self.btn_zoom_out = Gtk.Button(icon_name=self._get_icon("zoom-out-symbolic"))
        self.btn_zoom_out.set_tooltip_text(tr("zoom_out"))
        self.btn_zoom_out.connect("clicked", lambda b: self.canvas.set_zoom_centered(self.canvas.zoom / 1.2, self.canvas.get_width()/2, self.canvas.get_height()/2))
        zoom_box.append(self.btn_zoom_out)

        self.btn_zoom_fit = Gtk.Button(icon_name=self._get_icon("zoom-fit-best-symbolic", "zoom-fit-symbolic", "zoom-original-symbolic", "view-fullscreen-symbolic"))
        self.btn_zoom_fit.set_tooltip_text(tr("zoom_fit"))
        self.btn_zoom_fit.connect("clicked", lambda b: self.canvas.fit_to_view())
        zoom_box.append(self.btn_zoom_fit)

        self.btn_zoom_in = Gtk.Button(icon_name=self._get_icon("zoom-in-symbolic"))
        self.btn_zoom_in.set_tooltip_text(tr("zoom_in"))
        self.btn_zoom_in.connect("clicked", lambda b: self.canvas.set_zoom_centered(self.canvas.zoom * 1.2, self.canvas.get_width()/2, self.canvas.get_height()/2))
        zoom_box.append(self.btn_zoom_in)

        header.pack_start(zoom_box)

        # Right side actions
        # Hamburger Menu Button
        self.btn_menu = Gtk.MenuButton()
        self.btn_menu.set_icon_name(self._get_icon("open-menu-symbolic"))
        self.btn_menu.set_tooltip_text(tr("main_menu"))
        self.btn_menu.set_popover(self._create_main_menu_popover())
        header.pack_end(self.btn_menu)

        # Toggle Sidebar button
        self.btn_toggle_sidebar = Gtk.Button(icon_name=self._get_icon("sidebar-show-symbolic", "view-sidebar-symbolic", "pan-end-symbolic"))
        self.btn_toggle_sidebar.set_tooltip_text(tr("toggle_sidebar"))
        self.btn_toggle_sidebar.connect("clicked", lambda b: self.split_view.set_show_sidebar(not self.split_view.get_show_sidebar()))
        header.pack_end(self.btn_toggle_sidebar)

        # Set Wallpaper Button (Suggested action)
        self.btn_apply = Gtk.Button(
            icon_name=self._get_icon("preferences-desktop-wallpaper-symbolic", "object-select-symbolic", "starred-symbolic"),
            label=tr("set_wallpaper")
        )
        self.btn_apply.add_css_class("suggested-action")
        self.btn_apply.set_tooltip_text(tr("apply_tooltip_single", name=self.current_monitor.name))
        self.btn_apply.connect("clicked", self._on_apply_wallpaper_clicked)
        header.pack_end(self.btn_apply)

        # Export Button
        self.btn_export = Gtk.Button(
            icon_name=self._get_icon("image-x-generic-symbolic", "document-save-as-symbolic", "insert-image-symbolic"),
            label=tr("export_wallpaper")
        )
        self.btn_export.set_tooltip_text(tr("export_tooltip"))
        self.btn_export.connect("clicked", self._on_export_clicked)
        header.pack_end(self.btn_export)

        return header

    def _create_canvas_status_overlay(self) -> Gtk.Widget:
        overlay_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        overlay_box.set_halign(Gtk.Align.CENTER)
        overlay_box.set_valign(Gtk.Align.END)
        overlay_box.set_margin_bottom(12)

        self.lbl_status = Gtk.Label(label=f"{self.current_monitor.short_label} • {tr('zoom_label')}: 100%")
        self.lbl_status.add_css_class("canvas-status-badge")
        overlay_box.append(self.lbl_status)

        self.lbl_tip = Gtk.Label(label=tr("tip_drag_drop"))
        self.lbl_tip.add_css_class("canvas-status-badge")
        overlay_box.append(self.lbl_tip)

        return overlay_box

        return overlay_box

    def _create_sidebar(self) -> Gtk.Box:
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        sidebar.set_margin_top(12)
        sidebar.set_margin_bottom(12)
        sidebar.set_margin_start(12)
        sidebar.set_margin_end(12)

        # -------------------------------------------------------------
        # Section 1: Monitor Details
        # -------------------------------------------------------------
        mon_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        mon_frame.add_css_class("sidebar-section")
        
        lbl_mon_head = Gtk.Label(label=tr("section_monitor"), xalign=0)
        lbl_mon_head.add_css_class("sidebar-title")
        mon_frame.append(lbl_mon_head)

        self.lbl_mon_name = Gtk.Label(label=f"{self.current_monitor.name}: {self.current_monitor.description}", xalign=0)
        self.lbl_mon_name.set_wrap(True)
        mon_frame.append(self.lbl_mon_name)

        self.lbl_mon_res = Gtk.Label(label=tr("monitor_res_label", w=self.current_monitor.width, h=self.current_monitor.height), xalign=0)
        mon_frame.append(self.lbl_mon_res)

        self.box_mon_switch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.box_mon_switch.add_css_class("linked")
        self.box_mon_switch.set_margin_top(4)
        self._update_mon_switch_buttons()
        mon_frame.append(self.box_mon_switch)

        # Custom Resolution Controls
        sep_res = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep_res.set_margin_top(6)
        sep_res.set_margin_bottom(2)
        mon_frame.append(sep_res)

        lbl_custom_sub = Gtk.Label(label=tr("custom_res_title"), xalign=0)
        lbl_custom_sub.add_css_class("sidebar-title")
        mon_frame.append(lbl_custom_sub)

        # Width & Height inputs
        res_inputs = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        box_w = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box_w.append(Gtk.Label(label=tr("width_short")))
        self.spin_custom_width = Gtk.SpinButton.new_with_range(100, 16000, 10)
        self.spin_custom_width.set_value(self.monitor_manager.custom_monitor.width)
        self.spin_custom_width.set_hexpand(True)
        self.spin_custom_width.connect("value-changed", self._on_custom_res_spin_changed)
        box_w.append(self.spin_custom_width)
        res_inputs.append(box_w)

        box_h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box_h.append(Gtk.Label(label=tr("height_short")))
        self.spin_custom_height = Gtk.SpinButton.new_with_range(100, 16000, 10)
        self.spin_custom_height.set_value(self.monitor_manager.custom_monitor.height)
        self.spin_custom_height.set_hexpand(True)
        self.spin_custom_height.connect("value-changed", self._on_custom_res_spin_changed)
        box_h.append(self.spin_custom_height)
        res_inputs.append(box_h)

        btn_swap_wh = Gtk.Button(label="⇄")
        btn_swap_wh.set_tooltip_text(tr("swap_dimensions_tip"))
        btn_swap_wh.add_css_class("flat")
        btn_swap_wh.connect("clicked", self._on_swap_custom_res_clicked)
        res_inputs.append(btn_swap_wh)
        mon_frame.append(res_inputs)

        # Presets row
        presets_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        presets_box.append(Gtk.Label(label=tr("presets_label"), xalign=0))

        custom_presets = [
            ("FHD", 1920, 1080, "Full HD (1920x1080)"),
            ("2K", 2560, 1440, "QHD / 2K (2560x1440)"),
            ("4K", 3840, 2160, "4K UHD (3840x2160)"),
            ("21:9", 3440, 1440, "Ultrawide (3440x1440)"),
            ("9:16", 1080, 1920, "Smartphone 9:16 (1080x1920)"),
            ("1:1", 1080, 1080, "Quadrat / Square (1080x1080)"),
        ]
        for p_lbl, pw, ph, tip in custom_presets:
            p_btn = Gtk.Button(label=p_lbl)
            p_btn.set_tooltip_text(tip)
            p_btn.add_css_class("flat")
            p_btn.connect("clicked", lambda b, w=pw, h=ph: self._apply_custom_preset(w, h))
            presets_box.append(p_btn)
        mon_frame.append(presets_box)

        # Apply button
        self.btn_apply_custom_res = Gtk.Button(
            label=tr("apply_custom_res"),
            icon_name=self._get_icon("object-select-symbolic", "dialog-ok-symbolic", "emblem-ok-symbolic")
        )
        self.btn_apply_custom_res.set_tooltip_text(tr("apply_custom_res_tip"))
        self.btn_apply_custom_res.connect("clicked", self._on_apply_custom_res_clicked)
        mon_frame.append(self.btn_apply_custom_res)

        sidebar.append(mon_frame)

        # -------------------------------------------------------------
        # Section 2: Canvas Background & Color Engine
        # -------------------------------------------------------------
        bg_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        bg_frame.add_css_class("sidebar-section")

        lbl_bg_head = Gtk.Label(label=tr("section_bg"), xalign=0)
        lbl_bg_head.add_css_class("sidebar-title")
        bg_frame.append(lbl_bg_head)

        # Color picker row
        color_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        color_row.append(Gtk.Label(label=tr("select_color"), xalign=0, hexpand=True))

        color_dialog = Gtk.ColorDialog.new()
        color_dialog.set_with_alpha(False)
        self.btn_color_picker = Gtk.ColorDialogButton.new(color_dialog)
        self.btn_color_picker.set_rgba(rgb_to_gdk_rgba(*self.canvas.bg_color))
        self.btn_color_picker.connect("notify::rgba", self._on_color_picker_rgba_changed)
        color_row.append(self.btn_color_picker)

        self.lbl_hex_color = Gtk.Label(label=rgb_to_hex(*self.canvas.bg_color))
        color_row.append(self.lbl_hex_color)
        bg_frame.append(color_row)

        # Button: Adapt background color to image colors on click
        self.btn_adapt_bg = Gtk.Button(
            icon_name="color-select-symbolic",
            label=tr("match_bg_to_image"),
        )
        self.btn_adapt_bg.set_tooltip_text(tr("match_bg_tip"))
        self.btn_adapt_bg.connect("clicked", self._on_adapt_bg_to_images_clicked)
        bg_frame.append(self.btn_adapt_bg)

        # Palette Chips container
        palette_label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        palette_label_box.append(Gtk.Label(label=tr("dominant_colors"), xalign=0, hexpand=True))

        btn_recalc = Gtk.Button(icon_name=self._get_icon("view-refresh-symbolic", "edit-redo-symbolic"))
        btn_recalc.set_tooltip_text(tr("recalc_palette"))
        btn_recalc.connect("clicked", lambda b: self._refresh_palette(force_adapt=False))
        palette_label_box.append(btn_recalc)
        bg_frame.append(palette_label_box)

        self.palette_flow = Gtk.FlowBox()
        self.palette_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.palette_flow.set_max_children_per_line(8)
        bg_frame.append(self.palette_flow)

        # Optional auto adapt switch (deactivated by default)
        auto_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_auto = Gtk.Label(label=tr("always_auto_adapt"), xalign=0, hexpand=True)
        lbl_auto.set_tooltip_text(tr("always_auto_adapt"))
        auto_row.append(lbl_auto)

        self.switch_auto_adapt = Gtk.Switch()
        self.switch_auto_adapt.set_active(self.auto_adapt_bg)
        self.switch_auto_adapt.connect("state-set", self._on_auto_adapt_toggled)
        auto_row.append(self.switch_auto_adapt)
        bg_frame.append(auto_row)

        sidebar.append(bg_frame)

        # -------------------------------------------------------------
        # Section 2.5: Auto Layout & Spacing (Alle Bilder)
        # -------------------------------------------------------------
        layout_frame = self._create_layout_section()
        sidebar.append(layout_frame)

        # -------------------------------------------------------------
        # Section 3: Selected Layer Properties
        # -------------------------------------------------------------
        self.layer_prop_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.layer_prop_frame.add_css_class("sidebar-section")

        lbl_layer_head = Gtk.Label(label=tr("section_selected"), xalign=0)
        lbl_layer_head.add_css_class("sidebar-title")
        self.layer_prop_frame.append(lbl_layer_head)

        self.lbl_layer_name = Gtk.Label(label=tr("no_layer_selected"), xalign=0)
        self.lbl_layer_name.set_wrap(True)
        self.layer_prop_frame.append(self.lbl_layer_name)

        # Layer controls container (shown when layer is selected)
        self.layer_controls_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.layer_prop_frame.append(self.layer_controls_box)

        # Position X & Y
        pos_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pos_box.append(Gtk.Label(label="X:"))
        self.spin_x = Gtk.SpinButton.new_with_range(-5000, 10000, 1)
        self.spin_x.connect("value-changed", self._on_spin_prop_changed)
        pos_box.append(self.spin_x)

        pos_box.append(Gtk.Label(label="Y:"))
        self.spin_y = Gtk.SpinButton.new_with_range(-5000, 10000, 1)
        self.spin_y.connect("value-changed", self._on_spin_prop_changed)
        pos_box.append(self.spin_y)
        self.layer_controls_box.append(pos_box)

        # Size W & H
        size_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        size_box.append(Gtk.Label(label=tr("width_short")))
        self.spin_w = Gtk.SpinButton.new_with_range(10, 15000, 1)
        self.spin_w.connect("value-changed", self._on_spin_size_changed)
        size_box.append(self.spin_w)

        size_box.append(Gtk.Label(label=tr("height_short")))
        self.spin_h = Gtk.SpinButton.new_with_range(10, 15000, 1)
        self.spin_h.connect("value-changed", self._on_spin_size_changed)
        size_box.append(self.spin_h)
        self.layer_controls_box.append(size_box)

        # Rotation slider
        rot_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rot_row.append(Gtk.Label(label=tr("rotation_label")))
        self.scale_rotation = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 360, 1)
        self.scale_rotation.set_hexpand(True)
        self.scale_rotation.connect("value-changed", self._on_rotation_changed)
        rot_row.append(self.scale_rotation)

        btn_rot_reset = Gtk.Button(label="0°")
        btn_rot_reset.set_tooltip_text(tr("btn_reset_rotation"))
        btn_rot_reset.connect("clicked", lambda b: self.scale_rotation.set_value(0.0))
        rot_row.append(btn_rot_reset)
        self.layer_controls_box.append(rot_row)

        # Opacity slider
        opac_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        opac_row.append(Gtk.Label(label=tr("opacity_label")))
        self.scale_opacity = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.scale_opacity.set_hexpand(True)
        self.scale_opacity.connect("value-changed", self._on_opacity_changed)
        opac_row.append(self.scale_opacity)
        self.layer_controls_box.append(opac_row)

        # -------------------------------------------------------------
        # Border & Frame Controls
        # -------------------------------------------------------------
        border_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        border_frame.set_margin_top(4)
        border_frame.set_margin_bottom(4)

        lbl_border_head = Gtk.Label(label=tr("section_border"), xalign=0)
        lbl_border_head.add_css_class("sidebar-title")
        border_frame.append(lbl_border_head)

        # Border thickness (Dicke)
        thick_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        thick_row.append(Gtk.Label(label=tr("border_width")))
        self.spin_border_width = Gtk.SpinButton.new_with_range(0, 100, 1)
        self.spin_border_width.set_hexpand(True)
        self.spin_border_width.connect("value-changed", self._on_border_prop_changed)
        thick_row.append(self.spin_border_width)

        btn_bw_0 = Gtk.Button(label="0px")
        btn_bw_0.set_tooltip_text(tr("border_none"))
        btn_bw_0.connect("clicked", lambda b: self.spin_border_width.set_value(0.0))
        thick_row.append(btn_bw_0)

        btn_bw_8 = Gtk.Button(label="8px")
        btn_bw_8.set_tooltip_text(tr("border_classic"))
        btn_bw_8.connect("clicked", lambda b: self.spin_border_width.set_value(8.0))
        thick_row.append(btn_bw_8)
        border_frame.append(thick_row)

        # Border color (Farbe)
        bcol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bcol_row.append(Gtk.Label(label=tr("border_color"), xalign=0, hexpand=True))

        border_color_dialog = Gtk.ColorDialog.new()
        border_color_dialog.set_with_alpha(False)
        self.btn_border_color_picker = Gtk.ColorDialogButton.new(border_color_dialog)
        self.btn_border_color_picker.set_rgba(rgb_to_gdk_rgba(255, 255, 255))
        self.btn_border_color_picker.connect("notify::rgba", self._on_border_color_picker_changed)
        bcol_row.append(self.btn_border_color_picker)

        self.lbl_border_hex = Gtk.Label(label="#ffffff")
        bcol_row.append(self.lbl_border_hex)
        border_frame.append(bcol_row)

        # Quick border color presets: Weiß, Schwarz, Akzent, Gold
        preset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        preset_box.append(Gtk.Label(label=tr("presets_label"), xalign=0))

        for p_name, p_rgb in [
            (tr("preset_white"), (255, 255, 255)),
            (tr("preset_black"), (20, 20, 20)),
            (tr("preset_accent"), (0, 210, 255)),
            (tr("preset_gold"), (255, 200, 50)),
        ]:
            p_btn = Gtk.Button(label=p_name)
            p_btn.add_css_class("flat")
            p_btn.connect("clicked", lambda b, col=p_rgb: self._set_layer_border_color(col))
            preset_box.append(p_btn)
        border_frame.append(preset_box)

        # Corner radius (Eckenrundung)
        radius_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        radius_row.append(Gtk.Label(label=tr("corner_radius")))
        self.spin_border_radius = Gtk.SpinButton.new_with_range(0, 200, 1)
        self.spin_border_radius.set_hexpand(True)
        self.spin_border_radius.connect("value-changed", self._on_border_radius_changed)
        radius_row.append(self.spin_border_radius)

        btn_rad_0 = Gtk.Button(label="0px")
        btn_rad_0.set_tooltip_text(tr("radius_square_tip"))
        btn_rad_0.connect("clicked", lambda b: self.spin_border_radius.set_value(0.0))
        radius_row.append(btn_rad_0)

        btn_rad_16 = Gtk.Button(label="16px")
        btn_rad_16.set_tooltip_text(tr("radius_rounded_tip"))
        btn_rad_16.connect("clicked", lambda b: self.spin_border_radius.set_value(16.0))
        radius_row.append(btn_rad_16)
        border_frame.append(radius_row)

        self.layer_controls_box.append(border_frame)

        # -------------------------------------------------------------
        # Shadow Controls
        # -------------------------------------------------------------
        shadow_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        shadow_frame.set_margin_top(4)
        shadow_frame.set_margin_bottom(4)

        lbl_shadow_head = Gtk.Label(label=tr("section_shadow"), xalign=0)
        lbl_shadow_head.add_css_class("sidebar-title")
        shadow_frame.append(lbl_shadow_head)

        # Shadow toggle switch row
        shadow_toggle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        shadow_toggle_row.append(Gtk.Label(label=tr("enable_shadow"), xalign=0, hexpand=True))
        self.switch_shadow = Gtk.Switch()
        self.switch_shadow.connect("state-set", self._on_shadow_toggle_state_set)
        shadow_toggle_row.append(self.switch_shadow)
        shadow_frame.append(shadow_toggle_row)

        # Shadow settings container (sensitive when shadow is enabled)
        self.shadow_settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        shadow_frame.append(self.shadow_settings_box)

        # Shadow Blur (Unschärfe / Weichzeichner)
        blur_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        blur_row.append(Gtk.Label(label=tr("shadow_blur")))
        self.scale_shadow_blur = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.scale_shadow_blur.set_hexpand(True)
        self.scale_shadow_blur.connect("value-changed", self._on_shadow_blur_changed)
        blur_row.append(self.scale_shadow_blur)
        self.shadow_settings_box.append(blur_row)

        # Shadow Opacity (Deckkraft)
        s_opac_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        s_opac_row.append(Gtk.Label(label=tr("shadow_opacity")))
        self.scale_shadow_opacity = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.scale_shadow_opacity.set_hexpand(True)
        self.scale_shadow_opacity.connect("value-changed", self._on_shadow_opacity_changed)
        s_opac_row.append(self.scale_shadow_opacity)
        self.shadow_settings_box.append(s_opac_row)

        # Shadow Offset X and Y
        offset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        offset_row.append(Gtk.Label(label=tr("shadow_offset_x")))
        self.spin_shadow_ox = Gtk.SpinButton.new_with_range(-150, 150, 1)
        self.spin_shadow_ox.connect("value-changed", self._on_shadow_offset_changed)
        offset_row.append(self.spin_shadow_ox)

        offset_row.append(Gtk.Label(label=tr("shadow_offset_y")))
        self.spin_shadow_oy = Gtk.SpinButton.new_with_range(-150, 150, 1)
        self.spin_shadow_oy.connect("value-changed", self._on_shadow_offset_changed)
        offset_row.append(self.spin_shadow_oy)
        self.shadow_settings_box.append(offset_row)

        # Shadow Color picker row
        s_color_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        s_color_row.append(Gtk.Label(label=tr("shadow_color"), xalign=0, hexpand=True))

        s_color_dialog = Gtk.ColorDialog.new()
        s_color_dialog.set_with_alpha(False)
        self.btn_shadow_color_picker = Gtk.ColorDialogButton.new(s_color_dialog)
        self.btn_shadow_color_picker.set_rgba(rgb_to_gdk_rgba(0, 0, 0))
        self.btn_shadow_color_picker.connect("notify::rgba", self._on_shadow_color_picker_changed)
        s_color_row.append(self.btn_shadow_color_picker)

        self.lbl_shadow_hex = Gtk.Label(label="#000000")
        s_color_row.append(self.lbl_shadow_hex)
        self.shadow_settings_box.append(s_color_row)

        # Quick Shadow Presets (Dezent, Standard, Schwebend, Glow)
        s_preset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        s_preset_box.append(Gtk.Label(label=tr("presets_label"), xalign=0))

        presets = [
            (tr("shadow_preset_subtle"), 15, 0, 8, 40, tr("shadow_tip_subtle")),
            (tr("shadow_preset_standard"), 25, 0, 15, 55, tr("shadow_tip_standard")),
            (tr("shadow_preset_floating"), 45, 0, 25, 65, tr("shadow_tip_floating")),
            (tr("shadow_preset_glow"), 30, 0, 0, 70, tr("shadow_tip_glow")),
        ]
        for p_name, p_blur, p_ox, p_oy, p_opac, p_tip in presets:
            p_btn = Gtk.Button(label=p_name)
            p_btn.add_css_class("flat")
            p_btn.set_tooltip_text(p_tip)
            p_btn.connect("clicked", lambda b, bl=p_blur, ox=p_ox, oy=p_oy, op=p_opac: self._apply_shadow_preset(bl, ox, oy, op))
            s_preset_box.append(p_btn)
        self.shadow_settings_box.append(s_preset_box)

        self.layer_controls_box.append(shadow_frame)

        # Style inheritance action & info
        style_actions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        style_actions_box.set_margin_top(4)
        style_actions_box.set_margin_bottom(6)

        btn_apply_all_style = Gtk.Button(
            icon_name=self._get_icon("view-refresh-symbolic", "edit-redo-symbolic"),
            label=tr("apply_style_all"),
        )
        btn_apply_all_style.set_tooltip_text(tr("apply_style_all_tip"))
        btn_apply_all_style.connect("clicked", self._on_apply_style_to_all_clicked)
        style_actions_box.append(btn_apply_all_style)

        lbl_style_hint = Gtk.Label(
            label=tr("style_hint"),
            xalign=0,
        )
        lbl_style_hint.add_css_class("dim-label")
        lbl_style_hint.set_wrap(True)
        style_actions_box.append(lbl_style_hint)

        self.layer_controls_box.append(style_actions_box)

        # Quick Align buttons
        align_label = Gtk.Label(label=tr("quick_align"), xalign=0)
        self.layer_controls_box.append(align_label)

        align_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_center = Gtk.Button(label=tr("center_label"))
        btn_center.connect("clicked", self._on_align_center_clicked)
        align_box.append(btn_center)

        btn_fit = Gtk.Button(label=tr("fit_label"))
        btn_fit.connect("clicked", self._on_align_fit_clicked)
        align_box.append(btn_fit)

        btn_fill = Gtk.Button(label=tr("fill_label"))
        btn_fill.connect("clicked", self._on_align_fill_clicked)
        align_box.append(btn_fill)
        self.layer_controls_box.append(align_box)

        # Multi-monitor per-screen alignment buttons
        self.box_multi_mon_align = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.layer_controls_box.append(self.box_multi_mon_align)

        # Layer order & delete buttons
        order_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_front = Gtk.Button(icon_name=self._get_icon("go-top-symbolic", "pan-up-symbolic"))
        btn_front.set_tooltip_text(tr("layer_bring_front"))
        btn_front.connect("clicked", lambda b: self.canvas.move_selected_layers_to_front())
        order_box.append(btn_front)

        btn_up = Gtk.Button(icon_name=self._get_icon("go-up-symbolic", "pan-up-symbolic"))
        btn_up.set_tooltip_text(tr("layer_step_forward"))
        btn_up.connect("clicked", lambda b: self.canvas.move_selected_layers_up())
        order_box.append(btn_up)

        btn_down = Gtk.Button(icon_name=self._get_icon("go-down-symbolic", "pan-down-symbolic"))
        btn_down.set_tooltip_text(tr("layer_step_backward"))
        btn_down.connect("clicked", lambda b: self.canvas.move_selected_layers_down())
        order_box.append(btn_down)

        btn_back = Gtk.Button(icon_name=self._get_icon("go-bottom-symbolic", "pan-down-symbolic"))
        btn_back.set_tooltip_text(tr("layer_send_back"))
        btn_back.connect("clicked", lambda b: self.canvas.move_selected_layers_to_back())
        order_box.append(btn_back)

        btn_del = Gtk.Button(icon_name=self._get_icon("user-trash-symbolic", "edit-delete-symbolic"))
        btn_del.add_css_class("destructive-action")
        btn_del.set_tooltip_text(tr("layer_delete"))
        btn_del.connect("clicked", lambda b: self.canvas.remove_selected_layers())
        order_box.append(btn_del)
        self.layer_controls_box.append(order_box)

        self.layer_controls_box.set_visible(False)
        sidebar.append(self.layer_prop_frame)

        # -------------------------------------------------------------
        # Section 4: Layers List
        # -------------------------------------------------------------
        list_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        list_frame.add_css_class("sidebar-section")

        lbl_list_head = Gtk.Label(label=tr("layer_overview"), xalign=0)
        lbl_list_head.add_css_class("sidebar-title")
        list_frame.append(lbl_list_head)

        self.layer_listbox = Gtk.ListBox()
        self.layer_listbox.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.layer_listbox.connect("selected-rows-changed", self._on_layer_listbox_selection_changed)
        list_frame.append(self.layer_listbox)

        sidebar.append(list_frame)

        return sidebar

    # -------------------------------------------------------------------------
    # Auto-Layout & Spacing UI & Handlers
    # -------------------------------------------------------------------------
    def _create_layout_section(self) -> Gtk.Box:
        layout_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        layout_frame.add_css_class("sidebar-section")

        lbl_head = Gtk.Label(label=tr("section_layout"), xalign=0)
        lbl_head.add_css_class("sidebar-title")
        layout_frame.append(lbl_head)

        lbl_desc = Gtk.Label(
            label=tr("layout_desc"),
            xalign=0,
        )
        lbl_desc.add_css_class("dim-label")
        layout_frame.append(lbl_desc)

        # Mode Selection Row
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        mode_box.set_homogeneous(True)

        self.btn_mode_dynamic = Gtk.Button(label=tr("mode_dynamic"))
        self.btn_mode_dynamic.set_tooltip_text(tr("tip_mode_dynamic"))
        self.btn_mode_dynamic.connect("clicked", lambda b: self._set_layout_mode("dynamic"))
        mode_box.append(self.btn_mode_dynamic)

        self.btn_mode_grid = Gtk.Button(label=tr("mode_grid"))
        self.btn_mode_grid.set_tooltip_text(tr("tip_mode_grid"))
        self.btn_mode_grid.connect("clicked", lambda b: self._set_layout_mode("grid"))
        mode_box.append(self.btn_mode_grid)

        self.btn_mode_row = Gtk.Button(label=tr("mode_row"))
        self.btn_mode_row.set_tooltip_text(tr("tip_mode_row"))
        self.btn_mode_row.connect("clicked", lambda b: self._set_layout_mode("row"))
        mode_box.append(self.btn_mode_row)

        self.btn_mode_col = Gtk.Button(label=tr("mode_col"))
        self.btn_mode_col.set_tooltip_text(tr("tip_mode_col"))
        self.btn_mode_col.connect("clicked", lambda b: self._set_layout_mode("col"))
        mode_box.append(self.btn_mode_col)

        self.btn_mode_per_mon = Gtk.Button(label=tr("mode_monitors"))
        self.btn_mode_per_mon.set_tooltip_text(tr("tip_mode_monitors"))
        self.btn_mode_per_mon.connect("clicked", lambda b: self._set_layout_mode("per_monitor"))
        mode_box.append(self.btn_mode_per_mon)

        layout_frame.append(mode_box)

        # Slider 1: Randabstand (Canvas Margin)
        margin_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        margin_hdr.append(Gtk.Label(label=tr("margin_label"), xalign=0, hexpand=True))
        self.lbl_margin_val = Gtk.Label(label=f"{int(self.layout_margin)} px")
        self.lbl_margin_val.add_css_class("dim-label")
        margin_hdr.append(self.lbl_margin_val)
        layout_frame.append(margin_hdr)

        self.scale_layout_margin = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 300, 2)
        self.scale_layout_margin.set_value(self.layout_margin)
        self.scale_layout_margin.set_hexpand(True)
        self.scale_layout_margin.connect("value-changed", self._on_margin_slider_changed)
        layout_frame.append(self.scale_layout_margin)

        # Margin presets
        m_preset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        m_preset_box.append(Gtk.Label(label=tr("presets_label"), xalign=0))
        for m_val in [0, 20, 40, 80, 150]:
            btn = Gtk.Button(label=f"{m_val}px")
            btn.add_css_class("flat")
            btn.connect("clicked", lambda b, v=m_val: self.scale_layout_margin.set_value(float(v)))
            m_preset_box.append(btn)
        layout_frame.append(m_preset_box)

        # Slider 2: Bildabstand (Zwischenraum / Gap)
        gap_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        gap_hdr.append(Gtk.Label(label=tr("gap_label"), xalign=0, hexpand=True))
        self.lbl_gap_val = Gtk.Label(label=f"{int(self.layout_gap)} px")
        self.lbl_gap_val.add_css_class("dim-label")
        gap_hdr.append(self.lbl_gap_val)
        layout_frame.append(gap_hdr)

        self.scale_layout_gap = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 200, 2)
        self.scale_layout_gap.set_value(self.layout_gap)
        self.scale_layout_gap.set_hexpand(True)
        self.scale_layout_gap.connect("value-changed", self._on_gap_slider_changed)
        layout_frame.append(self.scale_layout_gap)

        # Gap presets
        g_preset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        g_preset_box.append(Gtk.Label(label=tr("presets_label"), xalign=0))
        for g_val in [0, 10, 20, 40, 80]:
            btn = Gtk.Button(label=f"{g_val}px")
            btn.add_css_class("flat")
            btn.connect("clicked", lambda b, v=g_val: self.scale_layout_gap.set_value(float(v)))
            g_preset_box.append(btn)
        layout_frame.append(g_preset_box)

        # Cover toggle switch
        cover_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_cover = Gtk.Label(label=tr("cover_label"), xalign=0, hexpand=True)
        cover_row.append(lbl_cover)
        self.switch_layout_cover = Gtk.Switch()
        self.switch_layout_cover.set_active(self.layout_cover)
        self.switch_layout_cover.connect("state-set", self._on_layout_cover_toggled)
        cover_row.append(self.switch_layout_cover)
        layout_frame.append(cover_row)

        # Execute Auto Layout button
        self.btn_auto_layout = Gtk.Button(
            icon_name=self._get_icon("view-grid-symbolic", "format-justify-fill-symbolic"),
            label=tr("btn_layout_apply"),
        )
        self.btn_auto_layout.add_css_class("suggested-action")
        self.btn_auto_layout.connect("clicked", lambda b: self._apply_current_layout(user_triggered=True))
        layout_frame.append(self.btn_auto_layout)

        self._update_layout_mode_buttons()
        return layout_frame

    def _set_layout_mode(self, mode: str):
        self.current_layout_mode = mode
        self._update_layout_mode_buttons()
        self._apply_current_layout()

    def _update_layout_mode_buttons(self):
        if not hasattr(self, "btn_mode_dynamic"):
            return
        modes = {
            "dynamic": self.btn_mode_dynamic,
            "grid": self.btn_mode_grid,
            "row": self.btn_mode_row,
            "col": self.btn_mode_col,
            "per_monitor": self.btn_mode_per_mon,
        }
        for m_key, btn in modes.items():
            if m_key == self.current_layout_mode:
                btn.add_css_class("suggested-action")
            else:
                btn.remove_css_class("suggested-action")

        is_spanned = self.current_monitor.is_spanned and len(self.current_monitor.sub_monitors) > 1
        self.btn_mode_per_mon.set_sensitive(is_spanned)
        if not is_spanned and self.current_layout_mode == "per_monitor":
            self.current_layout_mode = "dynamic"
            self.btn_mode_dynamic.add_css_class("suggested-action")
            self.btn_mode_per_mon.remove_css_class("suggested-action")

    def _on_margin_slider_changed(self, scale: Gtk.Scale):
        if self._updating_ui:
            return
        val = scale.get_value()
        self.layout_margin = val
        self.lbl_margin_val.set_label(f"{int(val)} px")
        self._apply_current_layout()

    def _on_gap_slider_changed(self, scale: Gtk.Scale):
        if self._updating_ui:
            return
        val = scale.get_value()
        self.layout_gap = val
        self.lbl_gap_val.set_label(f"{int(val)} px")
        self._apply_current_layout()

    def _on_layout_cover_toggled(self, switch: Gtk.Switch, state: bool) -> bool:
        if self._updating_ui:
            return False
        self.layout_cover = state
        self._apply_current_layout()
        return False

    def _apply_current_layout(self, user_triggered: bool = False):
        if not self.canvas.layers:
            if user_triggered:
                self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_no_images_to_arrange")))
            return

        self.canvas.auto_layout_layers(
            mode=self.current_layout_mode,
            margin=self.layout_margin,
            gap=self.layout_gap,
            cover=self.layout_cover,
        )
        if user_triggered:
            mode_names = {
                "dynamic": tr("mode_dynamic"),
                "grid": tr("mode_grid"),
                "row": tr("mode_row"),
                "col": tr("mode_col"),
                "per_monitor": tr("mode_monitors"),
            }
            m_name = mode_names.get(self.current_layout_mode, self.current_layout_mode)
            self.toast_overlay.add_toast(
                Adw.Toast.new(
                    tr("toast_images_arranged", mode=m_name, m=int(self.layout_margin), g=int(self.layout_gap))
                )
            )

    # -------------------------------------------------------------------------
    # Monitor Management
    # -------------------------------------------------------------------------
    def _update_mon_switch_buttons(self):
        if not hasattr(self, "box_mon_switch"):
            return
        while True:
            child = self.box_mon_switch.get_first_child()
            if child is None:
                break
            self.box_mon_switch.remove(child)

        for i, mon in enumerate(self.monitor_manager.monitors):
            if mon.is_spanned:
                label = tr("mon_switch_all")
            elif mon.is_custom:
                label = tr("mon_switch_custom")
            else:
                label = mon.name
            btn = Gtk.Button(label=label)
            btn.set_tooltip_text(tr("switch_to_mon", name=mon.name, w=mon.width, h=mon.height))
            if mon == self.current_monitor:
                btn.add_css_class("suggested-action")
            btn.connect("clicked", lambda b, idx=i: self.monitor_dropdown.set_selected(idx))
            self.box_mon_switch.append(btn)

    def _update_monitor_dropdown_items(self):
        labels = [m.short_label for m in self.monitor_manager.monitors]
        model = Gtk.StringList.new(labels)
        curr_idx = 0
        for i, m in enumerate(self.monitor_manager.monitors):
            if m == self.current_monitor or (m.is_custom and getattr(self.current_monitor, "is_custom", False)):
                curr_idx = i
                break
        self.monitor_dropdown.set_model(model)
        self.monitor_dropdown.set_selected(curr_idx)
        self._update_mon_switch_buttons()

    def _on_monitor_selected(self, dropdown: Gtk.DropDown, param):
        idx = dropdown.get_selected()
        if 0 <= idx < len(self.monitor_manager.monitors):
            mon = self.monitor_manager.monitors[idx]
            self.current_monitor = mon
            self.canvas.set_monitor(mon)
            if mon.is_spanned and mon.sub_monitors:
                subs_text = " + ".join(f"{s.name} ({s.width}x{s.height})" for s in mon.sub_monitors)
                self.lbl_mon_name.set_label(tr("spanned_title", subs=subs_text))
                boundaries = [str(s.rel_x) for s in mon.sub_monitors[1:]]
                b_str = tr("spanned_boundary", boundaries=", ".join(boundaries)) if boundaries else ""
                self.lbl_mon_res.set_label(tr("spanned_area", w=mon.width, h=mon.height, boundary=b_str))
                self.btn_apply.set_tooltip_text(tr("apply_tooltip_multi"))
            elif mon.is_custom:
                self.lbl_mon_name.set_label(tr("custom_mon_name"))
                self.lbl_mon_res.set_label(tr("monitor_res_label", w=mon.width, h=mon.height))
                self.btn_apply.set_tooltip_text(tr("apply_tooltip_custom"))
                if hasattr(self, "spin_custom_width") and hasattr(self, "spin_custom_height"):
                    self._updating_ui = True
                    self.spin_custom_width.set_value(mon.width)
                    self.spin_custom_height.set_value(mon.height)
                    self._updating_ui = False
            else:
                self.lbl_mon_name.set_label(f"{mon.name}: {mon.description}")
                self.lbl_mon_res.set_label(tr("monitor_res_label", w=mon.width, h=mon.height))
                self.btn_apply.set_tooltip_text(tr("apply_tooltip_single", name=mon.name))
            self._update_mon_switch_buttons()
            self._update_multi_monitor_align_buttons()
            self._update_layout_mode_buttons()
            self._update_status_bar()

    def _on_custom_res_spin_changed(self, spin: Gtk.SpinButton):
        if self._updating_ui:
            return
        w = int(self.spin_custom_width.get_value())
        h = int(self.spin_custom_height.get_value())
        if self.current_monitor.is_custom:
            self._set_active_custom_resolution(w, h, switch_monitor=False)

    def _on_swap_custom_res_clicked(self, button: Gtk.Button):
        w = int(self.spin_custom_width.get_value())
        h = int(self.spin_custom_height.get_value())
        self._apply_custom_preset(h, w)

    def _apply_custom_preset(self, w: int, h: int):
        self._updating_ui = True
        self.spin_custom_width.set_value(w)
        self.spin_custom_height.set_value(h)
        self._updating_ui = False
        self._set_active_custom_resolution(w, h, switch_monitor=True)

    def _on_apply_custom_res_clicked(self, button: Optional[Gtk.Button] = None):
        w = int(self.spin_custom_width.get_value())
        h = int(self.spin_custom_height.get_value())
        self._set_active_custom_resolution(w, h, switch_monitor=True)
        self.toast_overlay.add_toast(
            Adw.Toast.new(tr("toast_custom_res_applied", w=w, h=h))
        )

    def _set_active_custom_resolution(self, w: int, h: int, switch_monitor: bool = True):
        custom_mon = self.monitor_manager.set_custom_resolution(w, h)
        custom_idx = next(
            (i for i, m in enumerate(self.monitor_manager.monitors) if m.is_custom),
            None
        )
        if switch_monitor and (self.current_monitor != custom_mon) and custom_idx is not None:
            self.monitor_dropdown.set_selected(custom_idx)
        else:
            if self.current_monitor == custom_mon or self.current_monitor.is_custom:
                self.canvas.update_custom_size(w, h)
                self.lbl_mon_res.set_label(tr("monitor_res_label", w=w, h=h))
                self._update_status_bar()
            self._update_monitor_dropdown_items()

    def _update_multi_monitor_align_buttons(self):
        if not hasattr(self, "box_multi_mon_align"):
            return
        while True:
            child = self.box_multi_mon_align.get_first_child()
            if child is None:
                break
            self.box_multi_mon_align.remove(child)

        if self.current_monitor.is_spanned and self.current_monitor.sub_monitors:
            lbl = Gtk.Label(label=tr("align_monitor"), xalign=0)
            self.box_multi_mon_align.append(lbl)
            for sub in self.current_monitor.sub_monitors:
                btn = Gtk.Button(label=sub.name)
                btn.set_tooltip_text(tr("center_on_sub", name=sub.name, w=sub.width, h=sub.height))
                btn.connect("clicked", lambda b, s=sub: self._center_layer_on_sub_monitor(s))
                self.box_multi_mon_align.append(btn)
            self.box_multi_mon_align.set_visible(True)
        else:
            self.box_multi_mon_align.set_visible(False)

    def _center_layer_on_sub_monitor(self, sub: MonitorInfo):
        if not self.canvas.selected_layers:
            return
        for layer in self.canvas.selected_layers:
            layer.monitor_name = sub.name
            layer.x = sub.width / 2.0
            layer.y = sub.height / 2.0
        self._on_canvas_selection_changed(self.canvas.selected_layer)
        self.canvas.queue_draw()

    def _on_rescan_monitors_clicked(self, button: Gtk.Button):
        self.monitor_manager.refresh()
        self._update_monitor_dropdown_items()
        self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_monitors_rescanned")))

    # -------------------------------------------------------------------------
    # Color Engine & Dominant Palette
    # -------------------------------------------------------------------------
    def _refresh_palette(self, force_adapt: bool = False):
        images = [l.pil_image for l in self.canvas.layers if l.pil_image is not None]
        self.current_dominant_palette = ColorEngine.extract_dominant_colors(images, max_colors=8)

        # Clear existing chips
        while True:
            child = self.palette_flow.get_first_child()
            if child is None:
                break
            self.palette_flow.remove(child)

        # Add chips for each dominant color
        for rgb in self.current_dominant_palette:
            hex_val = rgb_to_hex(*rgb)
            btn = Gtk.Button()
            btn.add_css_class("palette-chip")
            btn.set_tooltip_text(tr("set_color_as_bg", hex=hex_val))

            # Custom inline CSS for the chip color
            css = f"button {{ background-color: {hex_val}; }}"
            p = Gtk.CssProvider()
            p.load_from_data(css.encode("utf-8"))
            btn.get_style_context().add_provider(p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

            btn.connect("clicked", lambda b, col=rgb: self._apply_color_from_palette(col))
            self.palette_flow.append(btn)

        # Auto adapt if enabled or forced
        if (self.auto_adapt_bg or force_adapt) and self.canvas.layers:
            best_col = ColorEngine.get_best_background_color(self.current_dominant_palette)
            self.canvas.set_background_color(best_col)
            self._update_color_picker_widget(best_col)

    def _on_adapt_bg_to_images_clicked(self, button: Gtk.Button):
        """Adapt background color to image dominant color only when button is explicitly clicked."""
        if not self.canvas.layers:
            self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_no_images_on_canvas")))
            return

        # Determine target images: if a layer is selected and has an image, adapt to it; otherwise all layers
        if self.canvas.selected_layer and self.canvas.selected_layer.pil_image:
            images = [self.canvas.selected_layer.pil_image]
            target_desc = f" ({self.canvas.selected_layer.name})"
        else:
            images = [l.pil_image for l in self.canvas.layers if l.pil_image is not None]
            target_desc = ""

        palette = ColorEngine.extract_dominant_colors(images, max_colors=8)
        if palette:
            best_col = ColorEngine.get_best_background_color(palette)
            self.canvas.set_background_color(best_col)
            self._update_color_picker_widget(best_col)
            hex_col = rgb_to_hex(*best_col)
            self.toast_overlay.add_toast(
                Adw.Toast.new(tr("toast_bg_color_adapted", target=target_desc, hex=hex_col))
            )

    def _apply_color_from_palette(self, rgb: Tuple[int, int, int]):
        self.canvas.set_background_color(rgb)
        self._update_color_picker_widget(rgb)
        self.toast_overlay.add_toast(
            Adw.Toast.new(tr("toast_bg_color_set", hex=rgb_to_hex(*rgb)))
        )

    def _on_auto_adapt_toggled(self, switch: Gtk.Switch, state: bool):
        self.auto_adapt_bg = state
        if state:
            self._refresh_palette(force_adapt=True)
        return False

    def _on_color_picker_rgba_changed(self, button: Gtk.ColorDialogButton, param):
        if self._updating_ui:
            return
        rgba = button.get_rgba()
        rgb = gdk_rgba_to_rgb(rgba)
        self.lbl_hex_color.set_label(rgb_to_hex(*rgb))
        self.canvas.set_background_color(rgb)

    def _update_color_picker_widget(self, rgb: Tuple[int, int, int]):
        self._updating_ui = True
        try:
            self.btn_color_picker.set_rgba(rgb_to_gdk_rgba(*rgb))
            self.lbl_hex_color.set_label(rgb_to_hex(*rgb))
        finally:
            self._updating_ui = False

    def _on_canvas_bg_color_changed(self, rgb: Tuple[int, int, int]):
        self._update_color_picker_widget(rgb)

    # -------------------------------------------------------------------------
    # Layer & Canvas Event Listeners
    # -------------------------------------------------------------------------
    def _on_canvas_selection_changed(self, layer: Optional[Layer] = None):
        self._updating_ui = True
        try:
            sel_layers = self.canvas.selected_layers
            n_sel = len(sel_layers)

            if n_sel == 0:
                self.lbl_layer_name.set_label(tr("no_layer_selected"))
                self.layer_controls_box.set_visible(False)
            elif n_sel == 1:
                layer = sel_layers[0]
                self.lbl_layer_name.set_label(layer.name)
                self.spin_x.set_sensitive(True)
                self.spin_y.set_sensitive(True)
                self.spin_w.set_sensitive(True)
                self.spin_h.set_sensitive(True)
                self.spin_x.set_value(layer.x)
                self.spin_y.set_value(layer.y)
                self.spin_w.set_value(layer.width)
                self.spin_h.set_value(layer.height)
                self.scale_rotation.set_sensitive(True)
                self.scale_rotation.set_value(layer.rotation)
                self.scale_opacity.set_value(layer.opacity * 100.0)
                self.spin_border_width.set_value(layer.border_width)
                self.btn_border_color_picker.set_rgba(rgb_to_gdk_rgba(*layer.border_color))
                self.lbl_border_hex.set_label(rgb_to_hex(*layer.border_color))
                self.spin_border_radius.set_value(layer.border_radius)
                self.switch_shadow.set_active(layer.shadow_enabled)
                self.shadow_settings_box.set_sensitive(layer.shadow_enabled)
                self.scale_shadow_blur.set_value(layer.shadow_blur)
                self.scale_shadow_opacity.set_value(layer.shadow_opacity * 100.0)
                self.spin_shadow_ox.set_value(layer.shadow_offset_x)
                self.spin_shadow_oy.set_value(layer.shadow_offset_y)
                self.btn_shadow_color_picker.set_rgba(rgb_to_gdk_rgba(*layer.shadow_color))
                self.lbl_shadow_hex.set_label(rgb_to_hex(*layer.shadow_color))
                self.layer_controls_box.set_visible(True)
            else:
                self.lbl_layer_name.set_label(tr("section_selected_multi", count=n_sel))
                self.spin_x.set_sensitive(False)
                self.spin_y.set_sensitive(False)
                self.spin_w.set_sensitive(False)
                self.spin_h.set_sensitive(False)
                self.scale_rotation.set_sensitive(True)
                primary = sel_layers[-1]
                self.scale_rotation.set_value(primary.rotation)
                self.scale_opacity.set_value(primary.opacity * 100.0)
                self.spin_border_width.set_value(primary.border_width)
                self.btn_border_color_picker.set_rgba(rgb_to_gdk_rgba(*primary.border_color))
                self.lbl_border_hex.set_label(rgb_to_hex(*primary.border_color))
                self.spin_border_radius.set_value(primary.border_radius)
                self.switch_shadow.set_active(primary.shadow_enabled)
                self.shadow_settings_box.set_sensitive(primary.shadow_enabled)
                self.scale_shadow_blur.set_value(primary.shadow_blur)
                self.scale_shadow_opacity.set_value(primary.shadow_opacity * 100.0)
                self.spin_shadow_ox.set_value(primary.shadow_offset_x)
                self.spin_shadow_oy.set_value(primary.shadow_offset_y)
                self.btn_shadow_color_picker.set_rgba(rgb_to_gdk_rgba(*primary.shadow_color))
                self.lbl_shadow_hex.set_label(rgb_to_hex(*primary.shadow_color))
                self.layer_controls_box.set_visible(True)

            self._sync_layer_listbox_selection()
            self._update_status_bar()
        finally:
            self._updating_ui = False

    def _on_canvas_layers_changed(self):
        self._refresh_palette()
        self._update_layer_listbox()
        self._update_status_bar()

    def _update_status_bar(self):
        zoom_pct = int(round(self.canvas.zoom * 100))
        n_layers = len(self.canvas.layers)
        layer_text = tr("images_count_plural", count=n_layers) if n_layers != 1 else tr("images_count", count=n_layers)
        sel_count = len(self.canvas.selected_layers)
        if sel_count > 1:
            sel_text = f" • {tr('selected_count', count=sel_count)}"
        elif sel_count == 1:
            sel_text = f" • {tr('selected_count', count=1)}"
        else:
            sel_text = ""
        self.lbl_status.set_label(f"{self.current_monitor.short_label} • {layer_text}{sel_text} • {tr('zoom_label')}: {zoom_pct}%")

    def _update_layer_listbox(self):
        self._updating_ui = True
        try:
            while True:
                child = self.layer_listbox.get_first_child()
                if child is None:
                    break
                self.layer_listbox.remove(child)

            for layer in reversed(self.canvas.layers):
                row = Gtk.ListBoxRow()
                row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row_box.set_margin_top(4)
                row_box.set_margin_bottom(4)
                row_box.set_margin_start(6)
                row_box.set_margin_end(6)

                icon = Gtk.Image.new_from_icon_name(self._get_icon("image-x-generic-symbolic", "image-symbolic"))
                row_box.append(icon)

                lbl = Gtk.Label(label=layer.name, xalign=0, hexpand=True)
                lbl.set_ellipsize(3)  # Ellipsize end
                row_box.append(lbl)

                if self.current_monitor.is_spanned and layer.monitor_name:
                    badge_lbl = Gtk.Label(label=layer.monitor_name)
                    badge_lbl.add_css_class("canvas-status-badge")
                    row_box.append(badge_lbl)

                btn_del = Gtk.Button(icon_name=self._get_icon("user-trash-symbolic", "edit-delete-symbolic"))
                btn_del.add_css_class("flat")
                btn_del.set_tooltip_text(tr("layer_delete"))
                btn_del.connect("clicked", lambda b, l=layer: self.canvas.remove_layer(l))
                row_box.append(btn_del)

                row.set_child(row_box)
                row._layer = layer
                self.layer_listbox.append(row)

            # Sync selection
            sel_set = set(self.canvas.selected_layers)
            child = self.layer_listbox.get_first_child()
            while child is not None:
                if hasattr(child, "_layer"):
                    if child._layer in sel_set:
                        self.layer_listbox.select_row(child)
                    else:
                        self.layer_listbox.unselect_row(child)
                child = child.get_next_sibling()
        finally:
            self._updating_ui = False

    def _sync_layer_listbox_selection(self):
        self._updating_ui = True
        try:
            sel_set = set(self.canvas.selected_layers)
            child = self.layer_listbox.get_first_child()
            while child is not None:
                if hasattr(child, "_layer"):
                    if child._layer in sel_set:
                        self.layer_listbox.select_row(child)
                    else:
                        self.layer_listbox.unselect_row(child)
                child = child.get_next_sibling()
        finally:
            self._updating_ui = False

    def _on_layer_listbox_selection_changed(self, listbox: Gtk.ListBox):
        if self._updating_ui:
            return
        selected_rows = listbox.get_selected_rows()
        layers = [r._layer for r in selected_rows if hasattr(r, "_layer")]
        self.canvas.select_layers(layers)

    # -------------------------------------------------------------------------
    # Layer Property Controls Handlers
    # -------------------------------------------------------------------------
    def _on_spin_prop_changed(self, spin: Gtk.SpinButton):
        if self._updating_ui or self.canvas.selected_layer is None:
            return
        self.canvas.selected_layer.x = self.spin_x.get_value()
        self.canvas.selected_layer.y = self.spin_y.get_value()
        self.canvas.queue_draw()

    def _on_spin_size_changed(self, spin: Gtk.SpinButton):
        if self._updating_ui or self.canvas.selected_layer is None:
            return
        layer = self.canvas.selected_layer
        new_w = self.spin_w.get_value()
        new_h = self.spin_h.get_value()
        
        # Maintain aspect ratio based on which spin changed
        if spin == self.spin_w and layer.aspect_ratio > 0:
            new_h = new_w / layer.aspect_ratio
            self._updating_ui = True
            self.spin_h.set_value(new_h)
            self._updating_ui = False
        elif spin == self.spin_h and layer.aspect_ratio > 0:
            new_w = new_h * layer.aspect_ratio
            self._updating_ui = True
            self.spin_w.set_value(new_w)
            self._updating_ui = False

        layer.width = new_w
        layer.height = new_h
        self.canvas.queue_draw()

    def _on_rotation_changed(self, scale: Gtk.Scale):
        if self._updating_ui or not self.canvas.selected_layers:
            return
        val = scale.get_value()
        for layer in self.canvas.selected_layers:
            layer.rotation = val
        self.canvas.queue_draw()

    def _on_opacity_changed(self, scale: Gtk.Scale):
        if self._updating_ui or not self.canvas.selected_layers:
            return
        val = scale.get_value() / 100.0
        for layer in self.canvas.selected_layers:
            layer.opacity = val
        self.canvas.queue_draw()

    def _on_border_prop_changed(self, spin: Gtk.SpinButton):
        if self._updating_ui or not self.canvas.selected_layers:
            return
        val = self.spin_border_width.get_value()
        for layer in self.canvas.selected_layers:
            layer.border_width = val
        self.canvas.default_border_width = val
        self.canvas.queue_draw()

    def _on_border_radius_changed(self, spin: Gtk.SpinButton):
        if self._updating_ui or not self.canvas.selected_layers:
            return
        val = self.spin_border_radius.get_value()
        for layer in self.canvas.selected_layers:
            layer.border_radius = val
        self.canvas.default_border_radius = val
        self.canvas.queue_draw()

    def _on_border_color_picker_changed(self, button: Gtk.ColorDialogButton, param):
        if self._updating_ui or not self.canvas.selected_layers:
            return
        rgba = button.get_rgba()
        rgb = gdk_rgba_to_rgb(rgba)
        self.lbl_border_hex.set_label(rgb_to_hex(*rgb))
        for layer in self.canvas.selected_layers:
            layer.border_color = rgb
        self.canvas.default_border_color = rgb
        self.canvas.queue_draw()

    def _set_layer_border_color(self, rgb: Tuple[int, int, int]):
        if not self.canvas.selected_layers:
            return
        for layer in self.canvas.selected_layers:
            layer.border_color = rgb
        self.canvas.default_border_color = rgb
        self._updating_ui = True
        try:
            self.btn_border_color_picker.set_rgba(rgb_to_gdk_rgba(*rgb))
            self.lbl_border_hex.set_label(rgb_to_hex(*rgb))
        finally:
            self._updating_ui = False
        self.canvas.queue_draw()

    def _on_shadow_toggle_state_set(self, switch: Gtk.Switch, state: bool):
        if self._updating_ui or not self.canvas.selected_layers:
            return False
        for layer in self.canvas.selected_layers:
            layer.shadow_enabled = state
        self.canvas.default_shadow_enabled = state
        if self.canvas.selected_layer:
            primary = self.canvas.selected_layer
            self.canvas.default_shadow_blur = primary.shadow_blur
            self.canvas.default_shadow_offset_x = primary.shadow_offset_x
            self.canvas.default_shadow_offset_y = primary.shadow_offset_y
            self.canvas.default_shadow_opacity = primary.shadow_opacity
            self.canvas.default_shadow_color = primary.shadow_color
        self.shadow_settings_box.set_sensitive(state)
        self.canvas.queue_draw()
        return False

    def _on_shadow_blur_changed(self, scale: Gtk.Scale):
        if self._updating_ui or not self.canvas.selected_layers:
            return
        val = scale.get_value()
        for layer in self.canvas.selected_layers:
            layer.shadow_blur = val
        self.canvas.default_shadow_blur = val
        self.canvas.queue_draw()

    def _on_shadow_opacity_changed(self, scale: Gtk.Scale):
        if self._updating_ui or not self.canvas.selected_layers:
            return
        val = scale.get_value() / 100.0
        for layer in self.canvas.selected_layers:
            layer.shadow_opacity = val
        self.canvas.default_shadow_opacity = val
        self.canvas.queue_draw()

    def _on_shadow_offset_changed(self, spin: Gtk.SpinButton):
        if self._updating_ui or not self.canvas.selected_layers:
            return
        ox = self.spin_shadow_ox.get_value()
        oy = self.spin_shadow_oy.get_value()
        for layer in self.canvas.selected_layers:
            layer.shadow_offset_x = ox
            layer.shadow_offset_y = oy
        self.canvas.default_shadow_offset_x = ox
        self.canvas.default_shadow_offset_y = oy
        self.canvas.queue_draw()

    def _on_shadow_color_picker_changed(self, button: Gtk.ColorDialogButton, param):
        if self._updating_ui or not self.canvas.selected_layers:
            return
        rgba = button.get_rgba()
        rgb = gdk_rgba_to_rgb(rgba)
        self.lbl_shadow_hex.set_label(rgb_to_hex(*rgb))
        for layer in self.canvas.selected_layers:
            layer.shadow_color = rgb
        self.canvas.default_shadow_color = rgb
        self.canvas.queue_draw()

    def _apply_shadow_preset(self, blur: float, ox: float, oy: float, opac: float):
        if not self.canvas.selected_layers:
            return
        for layer in self.canvas.selected_layers:
            layer.shadow_enabled = True
            layer.shadow_blur = blur
            layer.shadow_offset_x = ox
            layer.shadow_offset_y = oy
            layer.shadow_opacity = opac / 100.0

        self.canvas.default_shadow_enabled = True
        self.canvas.default_shadow_blur = blur
        self.canvas.default_shadow_offset_x = ox
        self.canvas.default_shadow_offset_y = oy
        self.canvas.default_shadow_opacity = opac / 100.0

        self._updating_ui = True
        try:
            self.switch_shadow.set_active(True)
            self.shadow_settings_box.set_sensitive(True)
            self.scale_shadow_blur.set_value(blur)
            self.spin_shadow_ox.set_value(ox)
            self.spin_shadow_oy.set_value(oy)
            self.scale_shadow_opacity.set_value(opac)
        finally:
            self._updating_ui = False
        self.canvas.queue_draw()

    def _on_apply_style_to_all_clicked(self, button: Gtk.Button):
        if not self.canvas.layers:
            return
        self.canvas.apply_style_to_all_layers(self.canvas.selected_layer)
        count = len(self.canvas.layers)
        suf = "er" if get_language() == "de" and count != 1 else ("s" if get_language() == "en" and count != 1 else "")
        self.toast_overlay.add_toast(
            Adw.Toast.new(tr("toast_style_applied_all", count=count, suffix=suf))
        )

    def _on_align_center_clicked(self, button: Gtk.Button):
        if not self.canvas.selected_layers:
            return
        for layer in self.canvas.selected_layers:
            if self.current_monitor.is_spanned and self.current_monitor.sub_monitors:
                sub = self.canvas.get_sub_monitor_for_layer(layer) or self.current_monitor.sub_monitors[0]
                layer.x = sub.width / 2.0
                layer.y = sub.height / 2.0
            else:
                layer.x = self.current_monitor.width / 2.0
                layer.y = self.current_monitor.height / 2.0
        self._on_canvas_selection_changed(self.canvas.selected_layer)
        self.canvas.queue_draw()

    def _on_align_fit_clicked(self, button: Gtk.Button):
        if not self.canvas.selected_layers:
            return
        for layer in self.canvas.selected_layers:
            if self.current_monitor.is_spanned and self.current_monitor.sub_monitors:
                sub = self.canvas.get_sub_monitor_for_layer(layer) or self.current_monitor.sub_monitors[0]
                layer.fit_into(sub.width, sub.height, cover=False)
                layer.x = sub.width / 2.0
                layer.y = sub.height / 2.0
            else:
                layer.fit_into(self.current_monitor.width, self.current_monitor.height, cover=False)
                layer.x = self.current_monitor.width / 2.0
                layer.y = self.current_monitor.height / 2.0
        self._on_canvas_selection_changed(self.canvas.selected_layer)
        self.canvas.queue_draw()

    def _on_align_fill_clicked(self, button: Gtk.Button):
        if not self.canvas.selected_layers:
            return
        for layer in self.canvas.selected_layers:
            if self.current_monitor.is_spanned and self.current_monitor.sub_monitors:
                sub = self.canvas.get_sub_monitor_for_layer(layer) or self.current_monitor.sub_monitors[0]
                layer.fit_into(sub.width, sub.height, cover=True)
                layer.x = sub.width / 2.0
                layer.y = sub.height / 2.0
            else:
                layer.fit_into(self.current_monitor.width, self.current_monitor.height, cover=True)
                layer.x = self.current_monitor.width / 2.0
                layer.y = self.current_monitor.height / 2.0
        self._on_canvas_selection_changed(self.canvas.selected_layer)
        self.canvas.queue_draw()

    # -------------------------------------------------------------------------
    # Dialogs & Actions
    # -------------------------------------------------------------------------
    def _on_add_image_clicked(self, button: Gtk.Button):
        dialog = Gtk.FileDialog.new()
        dialog.set_title(tr("dialog_add_images"))

        filter_img = Gtk.FileFilter()
        filter_img.set_name(f"{tr('dialog_add_images')} (*.png, *.jpg, *.jpeg, *.webp, *.svg)")
        filter_img.add_mime_type("image/png")
        filter_img.add_mime_type("image/jpeg")
        filter_img.add_mime_type("image/webp")
        filter_img.add_mime_type("image/svg+xml")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_img)
        dialog.set_filters(filters)

        def on_open_done(d, res):
            try:
                files = d.open_multiple_finish(res)
                added = 0
                for i in range(files.get_n_items()):
                    f = files.get_item(i)
                    p = f.get_path()
                    if p:
                        self.canvas.add_layer_from_path(p)
                        added += 1
                if added > 0:
                    self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_images_added", count=added)))
            except Exception:
                pass

        dialog.open_multiple(self, None, on_open_done)

    def _on_export_clicked(self, button: Optional[Gtk.Button] = None):
        dialog = Gtk.FileDialog.new()
        dialog.set_title(tr("dialog_export_wallpaper"))
        if getattr(self.current_monitor, "is_custom", False):
            init_name = f"wallpaper_custom_{self.current_monitor.width}x{self.current_monitor.height}.png"
        else:
            init_name = f"wallpaper_{self.current_monitor.name}.png"
        dialog.set_initial_name(init_name)

        def on_save_done(d, res):
            try:
                file = d.save_finish(res)
                path = file.get_path()
                if path:
                    ok = WallpaperSetter.export_to_file(
                        path,
                        self.current_monitor.width,
                        self.current_monitor.height,
                        self.canvas.bg_color,
                        self.canvas.layers,
                    )
                    if ok:
                        self.toast_overlay.add_toast(
                            Adw.Toast.new(tr("toast_wallpaper_saved", filename=os.path.basename(path)))
                        )
                    else:
                        self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_export_error")))
            except Exception:
                pass

        dialog.save(self, None, on_save_done)

    def _on_apply_wallpaper_clicked(self, button: Optional[Gtk.Button] = None):
        if hasattr(self, "btn_apply"):
            self.btn_apply.set_sensitive(False)
        try:
            # Synchronize active layers into all_layers
            for l in self.canvas.layers:
                if l not in self.canvas.all_layers:
                    self.canvas.all_layers.append(l)

            layers_to_apply = (
                self.canvas.all_layers
                if (self.current_monitor.is_spanned and self.canvas.all_layers)
                else self.canvas.layers
            )
            ok, msg = WallpaperSetter.apply_wallpaper(
                self.current_monitor,
                self.canvas.bg_color,
                layers_to_apply,
            )
            toast = Adw.Toast.new(msg)
            toast.set_timeout(4 if ok else 6)
            self.toast_overlay.add_toast(toast)
        finally:
            if hasattr(self, "btn_apply"):
                self.btn_apply.set_sensitive(True)

    def _on_window_key_pressed(self, controller: Gtk.EventControllerKey, keyval: int, keycode: int, state: Gdk.ModifierType) -> bool:
        focus = self.get_focus()
        if isinstance(focus, (Gtk.Editable, Gtk.Entry, Gtk.TextView)):
            return False

        ctrl_pressed = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if ctrl_pressed:
            if keyval in [Gdk.KEY_a, Gdk.KEY_A]:
                self.canvas.select_all_layers()
                return True
            elif keyval in [Gdk.KEY_v, Gdk.KEY_V]:
                self.paste_clipboard()
                return True
            elif keyval in [Gdk.KEY_s, Gdk.KEY_S]:
                if shift_pressed:
                    self.save_project_as_dialog()
                else:
                    self.save_project()
                return True
            elif keyval in [Gdk.KEY_o, Gdk.KEY_O]:
                self.open_project_dialog()
                return True
            elif keyval in [Gdk.KEY_n, Gdk.KEY_N]:
                self.new_project()
                return True
            elif keyval in [Gdk.KEY_e, Gdk.KEY_E]:
                self._on_export_clicked(None)
                return True

        if keyval == Gdk.KEY_Escape:
            self.canvas.clear_selection()
            return True

        return False

    def paste_clipboard(self):
        """Read image or copied files from clipboard and add as canvas layer."""
        def on_success(paths: List[str]):
            added = 0
            for p in paths:
                layer = self.canvas.add_layer_from_path(p)
                if layer:
                    added += 1
            if added > 0:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(tr("toast_images_pasted", count=added))
                )

        def on_failure(msg: str):
            self.toast_overlay.add_toast(Adw.Toast.new(msg))

        ClipboardManager.paste_image(on_success=on_success, on_failure=on_failure)

    # -------------------------------------------------------------------------
    # Project Management (Save, Save As, Open, New, Session Restore)
    # -------------------------------------------------------------------------
    def _create_main_menu_popover(self) -> Gtk.Popover:
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        def add_item(label: str, icon_names: List[str], callback):
            btn = Gtk.Button()
            btn.add_css_class("flat")
            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            btn_box.append(Gtk.Image.new_from_icon_name(self._get_icon(*icon_names)))
            lbl = Gtk.Label(label=label, xalign=0, hexpand=True)
            btn_box.append(lbl)
            btn.set_child(btn_box)
            btn.connect("clicked", lambda b: (popover.popdown(), callback()))
            box.append(btn)

        add_item(tr("menu_new_project"), ["document-new-symbolic", "window-new-symbolic"], self.new_project)
        add_item(tr("menu_open_project"), ["document-open-symbolic", "folder-open-symbolic"], self.open_project_dialog)
        add_item(tr("menu_save_project"), ["document-save-symbolic", "media-floppy-symbolic"], self.save_project)
        add_item(tr("menu_save_project_as"), ["document-save-as-symbolic", "document-save-symbolic"], self.save_project_as_dialog)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        add_item(tr("menu_export"), ["image-x-generic-symbolic", "image-symbolic"], lambda: self._on_export_clicked(None))
        add_item(tr("menu_apply"), ["preferences-desktop-wallpaper-symbolic", "object-select-symbolic", "emblem-ok-symbolic"], lambda: self._on_apply_wallpaper_clicked(None))

        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        add_item(tr("menu_rescan"), ["view-refresh-symbolic", "edit-redo-symbolic"], lambda: self._on_rescan_monitors_clicked(None))
        add_item(tr("menu_custom_res"), ["video-display-symbolic", "preferences-desktop-display-symbolic", "preferences-system-symbolic"], lambda: self._on_apply_custom_res_clicked(None))

        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        add_item(tr("menu_switch_language"), ["preferences-desktop-locale-symbolic", "input-keyboard-symbolic", "help-about-symbolic"], self._toggle_language)

        popover.set_child(box)
        return popover

    def _toggle_language(self):
        new_lang = "en" if get_language() == "de" else "de"
        set_language(new_lang)
        self.monitor_manager.refresh()
        self._update_monitor_dropdown_items()
        self._update_status_bar()
        self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_language_switched")))

    def _get_current_project_data(self) -> dict:
        viewport = {
            "zoom": self.canvas.zoom,
            "pan_x": self.canvas.pan_x,
            "pan_y": self.canvas.pan_y,
        }
        defaults = {
            "default_border_width": self.canvas.default_border_width,
            "default_border_color": list(self.canvas.default_border_color),
            "default_border_radius": self.canvas.default_border_radius,
            "default_shadow_enabled": self.canvas.default_shadow_enabled,
            "default_shadow_blur": self.canvas.default_shadow_blur,
            "default_shadow_offset_x": self.canvas.default_shadow_offset_x,
            "default_shadow_offset_y": self.canvas.default_shadow_offset_y,
            "default_shadow_opacity": self.canvas.default_shadow_opacity,
            "default_shadow_color": list(self.canvas.default_shadow_color),
            "layout_mode": self.current_layout_mode,
            "layout_margin": self.layout_margin,
            "layout_gap": self.layout_gap,
            "layout_cover": self.layout_cover,
        }
        layers_to_save = self.canvas.all_layers if self.canvas.all_layers else self.canvas.layers
        return ProjectManager.serialize(
            self.current_monitor,
            self.canvas.bg_color,
            layers_to_save,
            canvas_defaults=defaults,
            viewport=viewport,
        )

    def save_project(self):
        """Save current project to file, or prompt for path if not saved yet."""
        if self.current_project_path:
            data = self._get_current_project_data()
            if ProjectManager.save_to_file(self.current_project_path, data):
                ProjectManager.save_session(data)
                name = os.path.basename(self.current_project_path)
                self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_project_saved", filename=name)))
            else:
                self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_save_error")))
        else:
            self.save_project_as_dialog()

    def save_project_as_dialog(self):
        """Open file dialog to choose target project file path."""
        dialog = Gtk.FileDialog.new()
        dialog.set_title(tr("dialog_save_project"))

        init_name = "wallpaper_projekt.wpp"
        if self.current_project_path:
            init_name = os.path.basename(self.current_project_path)
        dialog.set_initial_name(init_name)

        filter_wpp = Gtk.FileFilter()
        filter_wpp.set_name(tr("file_filter_projects"))
        filter_wpp.add_pattern("*.wpp")
        filter_wpp.add_pattern("*.json")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_wpp)
        dialog.set_filters(filters)

        def on_save_done(d, res):
            try:
                file = d.save_finish(res)
                path = file.get_path()
                if path:
                    if not path.endswith(".wpp") and not path.endswith(".json"):
                        path += ".wpp"
                    data = self._get_current_project_data()
                    if ProjectManager.save_to_file(path, data):
                        self.current_project_path = path
                        self.set_title(tr("app_title_with_file", filename=os.path.basename(path)))
                        ProjectManager.save_session(data)
                        self.toast_overlay.add_toast(
                            Adw.Toast.new(tr("toast_project_saved", filename=os.path.basename(path)))
                        )
                    else:
                        self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_save_error")))
            except Exception:
                pass

        dialog.save(self, None, on_save_done)

    def open_project_dialog(self):
        """Open file dialog to choose and open a saved project."""
        dialog = Gtk.FileDialog.new()
        dialog.set_title(tr("dialog_open_project"))

        filter_wpp = Gtk.FileFilter()
        filter_wpp.set_name(tr("file_filter_projects"))
        filter_wpp.add_pattern("*.wpp")
        filter_wpp.add_pattern("*.json")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_wpp)
        dialog.set_filters(filters)

        def on_open_done(d, res):
            try:
                file = d.open_finish(res)
                path = file.get_path()
                if path:
                    self.open_project_file(path)
            except Exception:
                pass

        dialog.open(self, None, on_open_done)

    def open_project_file(self, path: str):
        """Load a project file from path and apply its state."""
        data = ProjectManager.load_from_file(path)
        if data:
            self._apply_project_data(data, project_path=path)
        else:
            self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_project_load_error", filename=os.path.basename(path))))

    def _apply_project_data(self, data: dict, project_path: Optional[str] = None, is_session_restore: bool = False):
        """Restore full canvas and application state from project dictionary."""
        try:
            mon_data, bg_color, layers, defaults, viewport = ProjectManager.deserialize(data)

            # 1. Match monitor if possible
            if mon_data and "name" in mon_data:
                saved_name = mon_data["name"]
                if mon_data.get("is_custom"):
                    w = int(mon_data.get("width", 1920))
                    h = int(mon_data.get("height", 1080))
                    self._apply_custom_preset(w, h)
                else:
                    for i, m in enumerate(self.monitor_manager.monitors):
                        if m.name == saved_name or (m.is_spanned and mon_data.get("is_spanned")):
                            self.current_monitor = m
                            self.monitor_dropdown.set_selected(i)
                            self.canvas.set_monitor(m)
                            break

            # 2. Restore background color
            self.canvas.set_background_color(bg_color)
            self._update_color_picker_widget(bg_color)

            # 3. Restore default styling
            if defaults:
                self.canvas.default_border_width = defaults.get("default_border_width", 0.0)
                self.canvas.default_border_color = tuple(defaults.get("default_border_color", (255, 255, 255)))
                self.canvas.default_border_radius = defaults.get("default_border_radius", 0.0)
                self.canvas.default_shadow_enabled = defaults.get("default_shadow_enabled", False)
                self.canvas.default_shadow_blur = defaults.get("default_shadow_blur", 20.0)
                self.canvas.default_shadow_offset_x = defaults.get("default_shadow_offset_x", 0.0)
                self.canvas.default_shadow_offset_y = defaults.get("default_shadow_offset_y", 15.0)
                self.canvas.default_shadow_opacity = defaults.get("default_shadow_opacity", 0.5)
                self.canvas.default_shadow_color = tuple(defaults.get("default_shadow_color", (0, 0, 0)))

                if "layout_mode" in defaults:
                    self.current_layout_mode = defaults["layout_mode"]
                if "layout_margin" in defaults:
                    self.layout_margin = float(defaults["layout_margin"])
                    if hasattr(self, "scale_layout_margin"):
                        self.scale_layout_margin.set_value(self.layout_margin)
                        self.lbl_margin_val.set_label(f"{int(self.layout_margin)} px")
                if "layout_gap" in defaults:
                    self.layout_gap = float(defaults["layout_gap"])
                    if hasattr(self, "scale_layout_gap"):
                        self.scale_layout_gap.set_value(self.layout_gap)
                        self.lbl_gap_val.set_label(f"{int(self.layout_gap)} px")
                if "layout_cover" in defaults:
                    self.layout_cover = bool(defaults["layout_cover"])
                    if hasattr(self, "switch_layout_cover"):
                        self.switch_layout_cover.set_active(self.layout_cover)
                self._update_layout_mode_buttons()

            # 4. Restore layers
            self.canvas.all_layers = list(layers)
            if self.current_monitor.is_spanned:
                self.canvas.layers = list(layers)
            else:
                self.canvas.layers = [l for l in layers if (l.monitor_name == self.current_monitor.name or not l.monitor_name)]
                for l in self.canvas.layers:
                    if not l.monitor_name:
                        l.monitor_name = self.current_monitor.name
            self.canvas.select_layer(self.canvas.layers[-1] if self.canvas.layers else None)

            # 5. Restore viewport
            if viewport and "zoom" in viewport:
                self.canvas.zoom = viewport.get("zoom", self.canvas.zoom)
                self.canvas.pan_x = viewport.get("pan_x", self.canvas.pan_x)
                self.canvas.pan_y = viewport.get("pan_y", self.canvas.pan_y)
                self.canvas.user_panned_or_zoomed = True

            # 6. Update UI
            self._refresh_palette()
            self._update_layer_listbox()
            self._update_status_bar()
            self.canvas.queue_draw()

            if project_path:
                self.current_project_path = project_path
                self.set_title(tr("app_title_with_file", filename=os.path.basename(project_path)))
                self.toast_overlay.add_toast(
                    Adw.Toast.new(tr("toast_project_loaded", filename=os.path.basename(project_path), count=len(layers)))
                )
            elif is_session_restore:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(tr("toast_session_restored", count=len(layers)))
                )
        except Exception as e:
            print(f"Error applying project data: {e}")
            self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_project_apply_error")))

    def new_project(self):
        """Reset canvas to blank new project."""
        self.canvas.all_layers.clear()
        self.canvas.layers.clear()
        self.canvas.select_layer(None)
        default_bg = (26, 27, 38)
        self.canvas.set_background_color(default_bg)
        self._update_color_picker_widget(default_bg)
        self.current_project_path = None
        self.set_title(tr("app_title"))

        # Reset canvas styling defaults
        self.canvas.default_border_width = 0.0
        self.canvas.default_border_color = (255, 255, 255)
        self.canvas.default_border_radius = 0.0
        self.canvas.default_shadow_enabled = False
        self.canvas.default_shadow_blur = 20.0
        self.canvas.default_shadow_offset_x = 0.0
        self.canvas.default_shadow_offset_y = 15.0
        self.canvas.default_shadow_opacity = 0.5
        self.canvas.default_shadow_color = (0, 0, 0)

        # Reset layout settings
        self.current_layout_mode = "dynamic"
        self.layout_margin = 40.0
        self.layout_gap = 20.0
        self.layout_cover = False
        if hasattr(self, "scale_layout_margin"):
            self.scale_layout_margin.set_value(40.0)
            self.lbl_margin_val.set_label("40 px")
        if hasattr(self, "scale_layout_gap"):
            self.scale_layout_gap.set_value(20.0)
            self.lbl_gap_val.set_label("20 px")
        if hasattr(self, "switch_layout_cover"):
            self.switch_layout_cover.set_active(False)
        self._update_layout_mode_buttons()

        self._refresh_palette()
        self._update_layer_listbox()
        self._update_status_bar()
        self.canvas.fit_to_view()
        self.canvas.queue_draw()
        self.toast_overlay.add_toast(Adw.Toast.new(tr("toast_new_project")))

    def _on_window_close_request(self, window):
        try:
            if self.canvas.layers:
                data = self._get_current_project_data()
                ProjectManager.save_session(data)
        except Exception:
            pass
        return False

