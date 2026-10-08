"""Rendering and applying wallpaper to Wayland / Hyprland desktops."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageOps, ImageChops, ImageFilter

from .models import Layer
from .monitor_manager import MonitorInfo


class WallpaperSetter:
    """Renders composite wallpapers and applies them to Wayland / Hyprland."""

    CACHE_DIR = Path.home() / ".cache" / "wallpaper_positioner"

    @classmethod
    def render_canvas(
        cls,
        width: int,
        height: int,
        background_rgb: Tuple[int, int, int],
        layers: List[Layer],
    ) -> Image.Image:
        """Render high-resolution composite canvas image using PIL Lanczos filtering."""
        width = max(100, int(round(width)))
        height = max(100, int(round(height)))

        # Create base canvas with background color
        canvas = Image.new("RGBA", (width, height), (*background_rgb, 255))

        for layer in layers:
            if not layer.visible or layer.width <= 0 or layer.height <= 0:
                continue

            pil_src = layer.pil_image
            if pil_src is None:
                continue

            try:
                # Target scale
                target_w = max(1, int(round(layer.width)))
                target_h = max(1, int(round(layer.height)))

                # Scale using Lanczos for crisp output
                scaled = pil_src.convert("RGBA").resize(
                    (target_w, target_h), Image.Resampling.LANCZOS
                )

                # Apply corner radius if specified
                if layer.border_radius > 0:
                    rad = int(round(layer.border_radius))
                    mask = Image.new("L", (target_w, target_h), 0)
                    draw_m = ImageDraw.Draw(mask)
                    draw_m.rounded_rectangle([0, 0, target_w - 1, target_h - 1], radius=rad, fill=255)
                    curr_alpha = scaled.getchannel("A")
                    final_alpha = ImageChops.multiply(curr_alpha, mask)
                    scaled.putalpha(final_alpha)

                # Apply border frame if specified
                if layer.border_width > 0:
                    bw = int(round(layer.border_width))
                    br, bg, bb = layer.border_color
                    border_rgba = (br, bg, bb, 255)
                    if layer.border_radius > 0:
                        out_w = target_w + (2 * bw)
                        out_h = target_h + (2 * bw)
                        framed = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
                        draw_f = ImageDraw.Draw(framed)
                        draw_f.rounded_rectangle(
                            [bw // 2, bw // 2, out_w - 1 - (bw // 2), out_h - 1 - (bw // 2)],
                            radius=int(round(layer.border_radius + bw)),
                            outline=border_rgba,
                            width=bw,
                        )
                        framed.alpha_composite(scaled, dest=(bw, bw))
                        scaled = framed
                    else:
                        scaled = ImageOps.expand(scaled, border=bw, fill=border_rgba)

                # Apply opacity if < 1.0
                if layer.opacity < 0.999:
                    r, g, b, a = scaled.split()
                    a = a.point(lambda p: int(p * max(0.0, min(1.0, layer.opacity))))
                    scaled.putalpha(a)

                # Render Drop Shadow (underneath image) if enabled
                if layer.shadow_enabled and layer.shadow_blur > 0 and layer.shadow_opacity > 0:
                    blur = max(1, int(round(layer.shadow_blur)))
                    pad = int(blur * 2.5) + 8
                    fw, fh = scaled.size
                    sw = fw + (2 * pad)
                    sh = fh + (2 * pad)

                    s_base = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
                    s_draw = ImageDraw.Draw(s_base)
                    s_alpha = int(round(max(0.0, min(1.0, layer.shadow_opacity * layer.opacity)) * 255))
                    sr, sg, sb = layer.shadow_color
                    total_rad = int(round(layer.border_radius + layer.border_width))

                    if total_rad > 0:
                        s_draw.rounded_rectangle(
                            [pad, pad, pad + fw - 1, pad + fh - 1],
                            radius=total_rad,
                            fill=(sr, sg, sb, s_alpha),
                        )
                    else:
                        s_draw.rectangle(
                            [pad, pad, pad + fw - 1, pad + fh - 1],
                            fill=(sr, sg, sb, s_alpha),
                        )

                    s_blurred = s_base.filter(ImageFilter.GaussianBlur(radius=blur))

                    if abs(layer.rotation % 360) > 0.01:
                        s_blurred = s_blurred.rotate(
                            -layer.rotation,
                            resample=Image.Resampling.BICUBIC,
                            expand=True,
                        )

                    sp_w, sp_h = s_blurred.size
                    sp_x = int(round(layer.x + layer.shadow_offset_x - (sp_w / 2.0)))
                    sp_y = int(round(layer.y + layer.shadow_offset_y - (sp_h / 2.0)))
                    canvas.alpha_composite(s_blurred, dest=(sp_x, sp_y))

                # Rotate if needed
                if abs(layer.rotation % 360) > 0.01:
                    # Negative rotation because PIL rotates counter-clockwise
                    scaled = scaled.rotate(
                        -layer.rotation,
                        resample=Image.Resampling.BICUBIC,
                        expand=True,
                    )

                # Calculate placement position so layer's center matches (layer.x, layer.y)
                paste_w, paste_h = scaled.size
                paste_x = int(round(layer.x - (paste_w / 2.0)))
                paste_y = int(round(layer.y - (paste_h / 2.0)))

                # Alpha composite
                canvas.alpha_composite(scaled, dest=(paste_x, paste_y))
            except Exception as e:
                print(f"Error rendering layer {layer.name}: {e}")

        # Return RGB image (wallpapers don't need alpha)
        return canvas.convert("RGB")

    @classmethod
    def export_to_file(
        cls,
        output_path: str,
        width: int,
        height: int,
        background_rgb: Tuple[int, int, int],
        layers: List[Layer],
        quality: int = 95,
    ) -> bool:
        """Render and save wallpaper to specified path."""
        try:
            img = cls.render_canvas(width, height, background_rgb, layers)
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            if output_path.lower().endswith(".jpg") or output_path.lower().endswith(".jpeg"):
                img.save(output_path, "JPEG", quality=quality)
            else:
                img.save(output_path, "PNG")
            return True
        except Exception as e:
            print(f"Error exporting wallpaper to {output_path}: {e}")
            return False

    @classmethod
    def _clean_old_cache(cls, prefix: str, keep_file: Path):
        """Purge previous cached wallpapers for a monitor to prevent stale cache buildup."""
        try:
            for old_file in cls.CACHE_DIR.glob(f"{prefix}_*.png"):
                if old_file != keep_file:
                    try:
                        old_file.unlink()
                    except Exception:
                        pass
            # Also clean legacy un-timestamped file if it exists
            legacy = cls.CACHE_DIR / f"{prefix}.png"
            if legacy.exists() and legacy != keep_file:
                try:
                    legacy.unlink()
                except Exception:
                    pass
        except Exception as e:
            print(f"Error cleaning old cache files for {prefix}: {e}")

    @classmethod
    def _apply_to_backends(cls, monitor_name: str, file_path: Path, is_custom: bool = False) -> List[str]:
        """Apply wallpaper to active desktop managers / daemons."""
        applied = []
        file_str = str(file_path.resolve())

        # Method 1: DankMaterialShell (DMS) IPC
        if shutil.which("dms"):
            try:
                if is_custom:
                    cmd = ["dms", "ipc", "call", "wallpaper", "set", file_str]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                    if res.returncode == 0 and res.stdout and "SUCCESS" in res.stdout and not res.stdout.strip().startswith("ERROR:"):
                        applied.append("DMS")
                else:
                    # First try per-monitor IPC endpoint
                    cmd = ["dms", "ipc", "call", "wallpaper", "setFor", monitor_name, file_str]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                    if res.returncode == 0 and res.stdout and "SUCCESS" in res.stdout and not res.stdout.strip().startswith("ERROR:"):
                        applied.append("DMS")
                    else:
                        # Fallback to global set endpoint if setFor was rejected
                        cmd_fallback = ["dms", "ipc", "call", "wallpaper", "set", file_str]
                        res_fb = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=3)
                        if res_fb.returncode == 0 and res_fb.stdout and "SUCCESS" in res_fb.stdout and not res_fb.stdout.strip().startswith("ERROR:"):
                            applied.append("DMS")
            except Exception as e:
                print(f"DMS wallpaper application failed: {e}")

        # Method 2: awww (Wayland wallpaper daemon used in Aphotic-Hypr)
        if shutil.which("awww"):
            try:
                chk = subprocess.run(["awww", "query"], capture_output=True, text=True, timeout=1)
                if chk.returncode == 0:
                    if is_custom:
                        res = subprocess.run(
                            ["awww", "img", file_str],
                            capture_output=True,
                            text=True,
                            timeout=3,
                        )
                    else:
                        res = subprocess.run(
                            ["awww", "img", "-o", monitor_name, file_str],
                            capture_output=True,
                            text=True,
                            timeout=3,
                        )
                    if res.returncode == 0:
                        applied.append("awww")
            except Exception as e:
                print(f"awww application failed: {e}")

        # Method 3: hyprpaper
        if shutil.which("hyprctl"):
            try:
                sub_preload = subprocess.run(
                    ["hyprctl", "hyprpaper", "preload", file_str],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if sub_preload.returncode == 0 and "ok" in sub_preload.stdout.lower():
                    if is_custom:
                        sub_apply = subprocess.run(
                            ["hyprctl", "hyprpaper", "wallpaper", f",{file_str}"],
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )
                    else:
                        sub_apply = subprocess.run(
                            ["hyprctl", "hyprpaper", "wallpaper", f"{monitor_name},{file_str}"],
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )
                    if sub_apply.returncode == 0:
                        applied.append("hyprpaper")
            except Exception as e:
                print(f"hyprpaper application failed: {e}")

        # Method 4: swww
        if shutil.which("swww"):
            try:
                chk = subprocess.run(["swww", "query"], capture_output=True, text=True, timeout=1)
                if chk.returncode == 0:
                    if is_custom:
                        res = subprocess.run(
                            ["swww", "img", file_str],
                            capture_output=True,
                            text=True,
                            timeout=3,
                        )
                    else:
                        res = subprocess.run(
                            ["swww", "img", "-o", monitor_name, file_str],
                            capture_output=True,
                            text=True,
                            timeout=3,
                        )
                    if res.returncode == 0:
                        applied.append("swww")
            except Exception as e:
                print(f"swww application failed: {e}")

        # Method 5: swaybg
        if shutil.which("swaybg"):
            try:
                chk = subprocess.run(["pgrep", "-x", "swaybg"], capture_output=True, text=True)
                if chk.returncode == 0:
                    if is_custom:
                        subprocess.Popen(["swaybg", "-i", file_str])
                    else:
                        subprocess.Popen(["swaybg", "-o", monitor_name, "-i", file_str])
                    applied.append("swaybg")
            except Exception as e:
                print(f"swaybg application failed: {e}")

        return applied

    @classmethod
    def apply_wallpaper(
        cls,
        monitor: MonitorInfo,
        background_rgb: Tuple[int, int, int],
        layers: List[Layer],
    ) -> Tuple[bool, str]:
        """
        Renders wallpaper and applies it directly to Hyprland / Wayland.
        Uses cache-busting timestamped filenames so Wayland shells (DMS / Qt Quick)
        instantly and reliably reload the wallpaper texture from disk.
        """
        import time
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)

        # Multi-monitor mode: Render each physical monitor slice individually
        if monitor.is_spanned and monitor.sub_monitors:
            applied_subs = []
            applied_methods = set()

            def get_sub_for_layer(l: Layer) -> MonitorInfo:
                for s in monitor.sub_monitors:
                    if s.name == l.monitor_name:
                        return s
                return monitor.sub_monitors[0]

            for sub in monitor.sub_monitors:
                sub_layers = [l for l in layers if get_sub_for_layer(l).name == sub.name]
                try:
                    slice_img = cls.render_canvas(
                        sub.width,
                        sub.height,
                        background_rgb,
                        sub_layers,
                    )
                except Exception as e:
                    return False, f"Fehler beim Rendern des Wallpapers für {sub.name}: {e}"

                sub_safe = sub.name.replace("/", "_").replace(" ", "_")
                sub_cache = cls.CACHE_DIR / f"wallpaper_{sub_safe}_{timestamp}.png"
                slice_img.save(str(sub_cache), "PNG")
                cls._clean_old_cache(f"wallpaper_{sub_safe}", sub_cache)

                methods = cls._apply_to_backends(sub.name, sub_cache)
                if methods:
                    applied_methods.update(methods)
                applied_subs.append(sub.name)

            if applied_methods:
                if shutil.which("notify-send"):
                    try:
                        subprocess.run(
                            [
                                "notify-send",
                                "-a",
                                "Wallpaper Positioner",
                                "Multi-Monitor Wallpaper aktualisiert",
                                f"Wallpapers für {', '.join(applied_subs)} gesetzt ({', '.join(applied_methods)}).",
                            ],
                            timeout=2,
                        )
                    except Exception:
                        pass
                return True, f"Wallpapers erfolgreich für beide Bildschirme ({', '.join(applied_subs)}) gesetzt! (via {', '.join(applied_methods)})"

            return False, f"Wallpapers für {', '.join(applied_subs)} gerendert, aber kein aktiver Desktop-Daemon (DMS, hyprpaper, awww, swww) konnte sie anwenden."

        safe_name = monitor.name.replace("/", "_").replace(" ", "_")
        cache_file = cls.CACHE_DIR / f"wallpaper_{safe_name}_{timestamp}.png"

        # Render wallpaper for this specific monitor
        mon_layers = [l for l in layers if (l.monitor_name == monitor.name or not l.monitor_name)]
        success = cls.export_to_file(
            str(cache_file),
            monitor.width,
            monitor.height,
            background_rgb,
            mon_layers,
        )
        if not success:
            return False, "Fehler beim Rendern des Wallpapers."

        cls._clean_old_cache(f"wallpaper_{safe_name}", cache_file)

        applied_methods = cls._apply_to_backends(monitor.name, cache_file, is_custom=getattr(monitor, "is_custom", False))

        if applied_methods:
            if shutil.which("notify-send"):
                try:
                    subprocess.run(
                        [
                            "notify-send",
                            "-a",
                            "Wallpaper Positioner",
                            "-i",
                            str(cache_file),
                            "Wallpaper aktualisiert",
                            f"Neues Wallpaper für {monitor.name} ({monitor.width}x{monitor.height}) gesetzt ({', '.join(applied_methods)}).",
                        ],
                        timeout=2,
                    )
                except Exception:
                    pass
            return True, f"Wallpaper erfolgreich gesetzt für {monitor.name} (via {', '.join(applied_methods)})"

        return False, f"Wallpaper gerendert unter:\n{cache_file}\n(Kein aktiver Wallpaper-Daemon hat reagiert.)"
