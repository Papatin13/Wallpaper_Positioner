"""Data models and geometry calculations for Wallpaper Positioner."""

from __future__ import annotations

import io
import math
import os
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Tuple, List
from PIL import Image, ImageFilter, ImageDraw
import cairo


class HandleType(Enum):
    TOP_LEFT = auto()
    TOP_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_RIGHT = auto()
    TOP = auto()
    BOTTOM = auto()
    LEFT = auto()
    RIGHT = auto()
    ROTATE = auto()


@dataclass
class Handle:
    handle_type: HandleType
    x: float
    y: float
    size: float = 10.0

    def contains_point(self, px: float, py: float, tolerance: float = 6.0) -> bool:
        r = (self.size / 2.0) + tolerance
        return (self.x - px) ** 2 + (self.y - py) ** 2 <= r ** 2


@dataclass(eq=False)
class Layer:
    """Represents an image placed on the canvas."""
    file_path: str
    name: str = ""
    x: float = 0.0          # Center X on canvas
    y: float = 0.0          # Center Y on canvas
    width: float = 100.0    # Rendered width
    height: float = 100.0   # Rendered height
    rotation: float = 0.0   # Rotation in degrees (clockwise)
    opacity: float = 1.0    # 0.0 to 1.0
    visible: bool = True
    locked: bool = False
    monitor_name: str = ""  # Name of target monitor (e.g. 'DP-1', 'HDMI-A-1')
    
    # Original image properties
    orig_width: int = 100
    orig_height: int = 100
    aspect_ratio: float = 1.0

    # Border & frame styling
    border_width: float = 0.0          # Border width in pixels (0.0 = none)
    border_color: Tuple[int, int, int] = (255, 255, 255)  # RGB border color
    border_radius: float = 0.0         # Corner radius in pixels

    # Shadow styling
    shadow_enabled: bool = False
    shadow_blur: float = 20.0          # Blur radius in pixels (0 - 100)
    shadow_offset_x: float = 0.0       # Horizontal offset (-100 to 100)
    shadow_offset_y: float = 15.0      # Vertical offset (-100 to 100)
    shadow_opacity: float = 0.5        # 0.0 to 1.0
    shadow_color: Tuple[int, int, int] = (0, 0, 0) # RGB shadow color

    # Cached resources
    _pil_image: Optional[Image.Image] = field(default=None, repr=False)
    _cairo_surface: Optional[cairo.ImageSurface] = field(default=None, repr=False)
    _shadow_surface: Optional[cairo.ImageSurface] = field(default=None, repr=False)
    _shadow_cache_key: Optional[tuple] = field(default=None, repr=False)

    def __post_init__(self):
        if not self.name and self.file_path:
            self.name = os.path.basename(self.file_path)
        if self._pil_image is None and os.path.exists(self.file_path):
            self.load_image()

    def load_image(self) -> None:
        """Load image from disk and initialize dimensions and cairo cache."""
        try:
            self._pil_image = Image.open(self.file_path)
            self._pil_image.load()
            self.orig_width, self.orig_height = self._pil_image.size
            if self.orig_height > 0:
                self.aspect_ratio = self.orig_width / self.orig_height
            else:
                self.aspect_ratio = 1.0
            self._update_cairo_surface()
        except Exception as e:
            print(f"Error loading image {self.file_path}: {e}")

    def _update_cairo_surface(self) -> None:
        """Create or update a Cairo ImageSurface from the PIL image."""
        if self._pil_image is None:
            return
        try:
            # We convert to RGBA
            img_rgba = self._pil_image.convert("RGBA")
            
            # To maintain performance for large raw images while zooming/panning,
            # we can create a cairo image surface from PNG buffer in memory
            buf = io.BytesIO()
            img_rgba.save(buf, format="PNG")
            buf.seek(0)
            self._cairo_surface = cairo.ImageSurface.create_from_png(buf)
        except Exception as e:
            print(f"Error creating cairo surface for {self.name}: {e}")
            self._cairo_surface = None

    @property
    def pil_image(self) -> Optional[Image.Image]:
        if self._pil_image is None and os.path.exists(self.file_path):
            self.load_image()
        return self._pil_image

    @property
    def cairo_surface(self) -> Optional[cairo.ImageSurface]:
        if self._cairo_surface is None and self.pil_image is not None:
            self._update_cairo_surface()
        return self._cairo_surface

    def get_shadow_surface(self) -> Optional[cairo.ImageSurface]:
        """Compute and cache a blurred Cairo shadow surface based on current dimensions, border, and shadow settings."""
        if not self.shadow_enabled or self.shadow_blur <= 0 or self.shadow_opacity <= 0 or self.width <= 0 or self.height <= 0:
            return None

        # Cache key independent of x, y, rotation, offset_x, offset_y
        cache_key = (
            int(round(self.width)),
            int(round(self.height)),
            int(round(self.border_width)),
            int(round(self.border_radius)),
            int(round(self.shadow_blur)),
            int(round(self.shadow_opacity * 100)),
            self.shadow_color,
        )

        if self._shadow_surface is not None and self._shadow_cache_key == cache_key:
            return self._shadow_surface

        try:
            w = int(round(self.width))
            h = int(round(self.height))
            bw = int(round(self.border_width))
            blur = max(1, int(round(self.shadow_blur)))
            outer_w = w + (2 * bw)
            outer_h = h + (2 * bw)
            total_rad = int(round(self.border_radius + bw))

            # Padding needed for Gaussian blur fade out
            pad = int(blur * 2.5) + 8
            shadow_w = outer_w + (2 * pad)
            shadow_h = outer_h + (2 * pad)

            # Create shadow mask in Pillow
            base = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(base)
            alpha_val = int(round(max(0.0, min(1.0, self.shadow_opacity)) * 255))
            sr, sg, sb = self.shadow_color

            if total_rad > 0:
                draw.rounded_rectangle(
                    [pad, pad, pad + outer_w - 1, pad + outer_h - 1],
                    radius=total_rad,
                    fill=(sr, sg, sb, alpha_val),
                )
            else:
                draw.rectangle(
                    [pad, pad, pad + outer_w - 1, pad + outer_h - 1],
                    fill=(sr, sg, sb, alpha_val),
                )

            # Apply Gaussian Blur
            blurred = base.filter(ImageFilter.GaussianBlur(radius=blur))

            # Convert to Cairo ImageSurface
            buf = io.BytesIO()
            blurred.save(buf, format="PNG")
            buf.seek(0)
            self._shadow_surface = cairo.ImageSurface.create_from_png(buf)
            self._shadow_cache_key = cache_key
            return self._shadow_surface
        except Exception as e:
            print(f"Error creating shadow surface: {e}")
            self._shadow_surface = None
            return None

    def to_layer_coords(self, px: float, py: float) -> Tuple[float, float]:
        """Convert a canvas point (px, py) to unrotated local layer coordinates relative to center."""
        # Vector from center to point
        dx = px - self.x
        dy = py - self.y
        rad = -math.radians(self.rotation)
        lx = dx * math.cos(rad) - dy * math.sin(rad)
        ly = dx * math.sin(rad) + dy * math.cos(rad)
        return lx, ly

    def from_layer_coords(self, lx: float, ly: float) -> Tuple[float, float]:
        """Convert local layer coordinate (relative to center) to canvas coordinate."""
        rad = math.radians(self.rotation)
        dx = lx * math.cos(rad) - ly * math.sin(rad)
        dy = lx * math.sin(rad) + ly * math.cos(rad)
        return self.x + dx, self.y + dy

    def contains_point(self, px: float, py: float) -> bool:
        """Check if canvas point (px, py) is inside this layer's bounds including border."""
        if not self.visible:
            return False
        lx, ly = self.to_layer_coords(px, py)
        hw = (self.width / 2.0) + self.border_width
        hh = (self.height / 2.0) + self.border_width
        return -hw <= lx <= hw and -hh <= ly <= hh

    def intersects_rect(self, rx: float, ry: float, rw: float, rh: float) -> bool:
        """Check if this layer intersects the given rectangle [rx, rx+rw] x [ry, ry+rh]."""
        if not self.visible or rw <= 0 or rh <= 0:
            return False

        # 1. Quick check: layer center inside rect
        if rx <= self.x <= (rx + rw) and ry <= self.y <= (ry + rh):
            return True

        # 2. Check 4 corners of the layer
        hw = (self.width / 2.0) + self.border_width
        hh = (self.height / 2.0) + self.border_width
        corners = [
            self.from_layer_coords(-hw, -hh),
            self.from_layer_coords(hw, -hh),
            self.from_layer_coords(hw, hh),
            self.from_layer_coords(-hw, hh),
        ]
        for cx, cy in corners:
            if rx <= cx <= (rx + rw) and ry <= cy <= (ry + rh):
                return True

        # 3. Check if any rect corner is inside the layer
        rect_corners = [
            (rx, ry),
            (rx + rw, ry),
            (rx + rw, ry + rh),
            (rx, ry + rh),
        ]
        for rcx, rcy in rect_corners:
            if self.contains_point(rcx, rcy):
                return True

        # 4. Check AABB overlap
        min_x = min(c[0] for c in corners)
        max_x = max(c[0] for c in corners)
        min_y = min(c[1] for c in corners)
        max_y = max(c[1] for c in corners)
        if max_x < rx or min_x > (rx + rw) or max_y < ry or min_y > (ry + rh):
            return False

        return True

    def get_handles(self, handle_size: float = 12.0) -> List[Handle]:
        """Return list of interactive handles in canvas coordinates."""
        hw = (self.width / 2.0) + self.border_width
        hh = (self.height / 2.0) + self.border_width
        rot_offset = 30.0  # Distance of rotation handle above top edge

        local_defs = [
            (HandleType.TOP_LEFT, -hw, -hh),
            (HandleType.TOP_RIGHT, hw, -hh),
            (HandleType.BOTTOM_LEFT, -hw, hh),
            (HandleType.BOTTOM_RIGHT, hw, hh),
            (HandleType.TOP, 0.0, -hh),
            (HandleType.BOTTOM, 0.0, hh),
            (HandleType.LEFT, -hw, 0.0),
            (HandleType.RIGHT, hw, 0.0),
            (HandleType.ROTATE, 0.0, -hh - rot_offset),
        ]

        handles = []
        for h_type, lx, ly in local_defs:
            cx, cy = self.from_layer_coords(lx, ly)
            handles.append(Handle(handle_type=h_type, x=cx, y=cy, size=handle_size))
        return handles

    def get_handle_at(self, px: float, py: float, tolerance: float = 8.0) -> Optional[Handle]:
        """Check if canvas point (px, py) hits any handle."""
        for handle in self.get_handles():
            if handle.contains_point(px, py, tolerance=tolerance):
                return handle
        return None

    def fit_into(self, max_w: float, max_h: float, cover: bool = False) -> None:
        """Scale layer to fit or cover the specified dimensions while preserving aspect ratio."""
        if self.orig_width <= 0 or self.orig_height <= 0:
            return
        
        ratio_w = max_w / self.orig_width
        ratio_h = max_h / self.orig_height

        scale = max(ratio_w, ratio_h) if cover else min(ratio_w, ratio_h)
        self.width = self.orig_width * scale
        self.height = self.orig_height * scale

    def reset_rotation(self) -> None:
        self.rotation = 0.0
