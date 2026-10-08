"""Color analysis and dominant palette extraction using Pillow and NumPy."""

from __future__ import annotations

import colorsys
import math
from typing import List, Tuple, Optional
import numpy as np
from PIL import Image

import gi
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Format RGB integer values (0-255) as hex string #RRGGBB."""
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Parse #RRGGBB to (r, g, b) 0-255."""
    s = hex_str.lstrip("#")
    if len(s) == 3:
        s = "".join([c * 2 for c in s])
    if len(s) != 6:
        return (26, 27, 38)  # fallback dark theme
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def rgb_to_gdk_rgba(r: int, g: int, b: int, a: float = 1.0) -> Gdk.RGBA:
    """Create Gdk.RGBA object from 0-255 RGB values."""
    rgba = Gdk.RGBA()
    rgba.red = max(0.0, min(1.0, r / 255.0))
    rgba.green = max(0.0, min(1.0, g / 255.0))
    rgba.blue = max(0.0, min(1.0, b / 255.0))
    rgba.alpha = max(0.0, min(1.0, a))
    return rgba


def gdk_rgba_to_rgb(rgba: Gdk.RGBA) -> Tuple[int, int, int]:
    """Convert Gdk.RGBA to 0-255 RGB tuple."""
    return (
        int(round(rgba.red * 255)),
        int(round(rgba.green * 255)),
        int(round(rgba.blue * 255)),
    )


def color_distance(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    """Calculate Euclidean distance between two RGB colors with human eye perceptual weighting."""
    # Weighted Euclidean distance: red (0.3), green (0.59), blue (0.11)
    dr = c1[0] - c2[0]
    dg = c1[1] - c2[1]
    db = c1[2] - c2[2]
    return math.sqrt(0.3 * (dr ** 2) + 0.59 * (dg ** 2) + 0.11 * (db ** 2))


class ColorEngine:
    """Extracts dominant colors and provides auto-adapting wallpaper backgrounds."""

    @staticmethod
    def extract_dominant_colors(
        pil_images: List[Image.Image],
        max_colors: int = 8,
        min_distance: float = 28.0,
    ) -> List[Tuple[int, int, int]]:
        """
        Extract prominent colors from a list of images.
        Uses image quantization and perceptual distance clustering.
        """
        if not pil_images:
            # Default aesthetic palette (Hyprland / Tokyo Night / Catppuccin style)
            return [
                (26, 27, 38),   # Dark slate
                (36, 40, 59),   # Navy
                (122, 162, 247), # Sky blue
                (187, 154, 247), # Lavender
                (158, 206, 106), # Green
                (224, 175, 104), # Amber
                (247, 118, 142), # Rose
                (24, 25, 38),   # Deep dark
            ]

        sample_pixels = []

        # Downsample images for speed and combine sample pixels
        for img in pil_images:
            try:
                # Downsample to maximum 128x128 thumbnail
                thumb = img.convert("RGB")
                thumb.thumbnail((120, 120), Image.Resampling.BOX)
                
                # Quantize down to 16 colors using MEDIANCUT
                quantized = thumb.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
                palette = quantized.getpalette()[: 16 * 3]
                
                # Count frequencies of each palette color in the image
                counts = np.bincount(np.array(quantized).flatten(), minlength=16)
                
                for idx in range(16):
                    if counts[idx] > 0 and (idx * 3 + 2) < len(palette):
                        rgb = (
                            palette[idx * 3],
                            palette[idx * 3 + 1],
                            palette[idx * 3 + 2],
                        )
                        sample_pixels.append((int(counts[idx]), rgb))
            except Exception as e:
                print(f"Error sampling image colors: {e}")

        if not sample_pixels:
            return [(30, 30, 30)]

        # Sort sampled colors by frequency descending
        sample_pixels.sort(key=lambda item: item[0], reverse=True)

        # Filter out duplicates and visually indistinguishable colors
        unique_colors: List[Tuple[int, int, int]] = []
        for count, rgb in sample_pixels:
            is_distinct = True
            for existing in unique_colors:
                if color_distance(rgb, existing) < min_distance:
                    is_distinct = False
                    break
            if is_distinct:
                unique_colors.append(rgb)
            if len(unique_colors) >= max_colors:
                break

        return unique_colors

    @staticmethod
    def get_best_background_color(
        dominant_colors: List[Tuple[int, int, int]],
        mode: str = "harmonious_dark",
    ) -> Tuple[int, int, int]:
        """
        Choose the best wallpaper background color from dominant colors.
        Modes:
        - 'primary': Most frequent dominant color
        - 'harmonious_dark': Deep, rich tone of the dominant palette (ideal for desktop icons & window readability)
        - 'vibrant': Most saturated color in the palette
        """
        if not dominant_colors:
            return (26, 27, 38)

        if mode == "primary":
            return dominant_colors[0]

        if mode == "vibrant":
            # Sort by HSV saturation
            def sat(rgb):
                r, g, b = [x / 255.0 for x in rgb]
                h, s, v = colorsys.rgb_to_hsv(r, g, b)
                return s * v
            return max(dominant_colors, key=sat)

        # Default 'harmonious_dark': Pick a dominant color with rich depth or deepen the primary color
        primary = dominant_colors[0]
        r, g, b = [x / 255.0 for x in primary]
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        
        # If primary is already dark (value <= 0.35), use it directly
        if v <= 0.35:
            return primary
        
        # Look for a dark palette entry with similar hue or depth
        dark_options = [c for c in dominant_colors if colorsys.rgb_to_hsv(c[0]/255, c[1]/255, c[2]/255)[2] <= 0.35]
        if dark_options:
            return dark_options[0]

        # Alternatively, create a darkened, harmonious wallpaper tone from the primary color
        dark_v = max(0.12, min(0.25, v * 0.3))
        dark_s = min(0.65, s * 1.1)
        dr, dg, db = colorsys.hsv_to_rgb(h, dark_s, dark_v)
        return (int(dr * 255), int(dg * 255), int(db * 255))
