"""Clipboard handling for pasting images and files into Wallpaper Positioner."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional, List

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib


class ClipboardManager:
    """Handles reading images and files from Wayland/GDK clipboard."""

    CACHE_DIR = Path.home() / ".cache" / "wallpaper_positioner" / "clipboard"

    @classmethod
    def get_clipboard(cls) -> Gdk.Clipboard:
        display = Gdk.Display.get_default()
        return display.get_clipboard()

    @classmethod
    def paste_image(
        cls,
        on_success: Callable[[List[str]], None],
        on_failure: Callable[[str], None],
    ) -> None:
        """
        Asynchronously inspects clipboard and extracts image(s).
        Order of inspection:
        1. Gdk.Texture (Direct image pixels in clipboard, e.g. screenshot or browser copy)
        2. Gdk.FileList (Files copied via Ctrl+C in file manager)
        3. Text string (Path or file:// URI)
        4. Fallback to wl-paste if available
        """
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cb = cls.get_clipboard()

        # Step 1: Try reading as texture (Gdk.Texture)
        def on_texture_read(clipboard, res):
            try:
                texture = clipboard.read_texture_finish(res)
                if texture is not None:
                    timestamp = int(time.time() * 1000)
                    cache_file = cls.CACHE_DIR / f"paste_{timestamp}.png"
                    bytes_obj = texture.save_to_png_bytes()
                    with open(cache_file, "wb") as f:
                        f.write(bytes_obj.get_data())
                    on_success([str(cache_file)])
                    return
            except Exception as e:
                pass

            # Step 2: Try reading as FileList
            cls._try_read_file_list(cb, on_success, on_failure)

        cb.read_texture_async(None, on_texture_read)

    @classmethod
    def _try_read_file_list(
        cls,
        cb: Gdk.Clipboard,
        on_success: Callable[[List[str]], None],
        on_failure: Callable[[str], None],
    ) -> None:
        def on_file_list_read(clipboard, res):
            try:
                val = clipboard.read_value_finish(res)
                if val is not None:
                    # Check if val is Gdk.FileList
                    file_list = val.get_boxed() if hasattr(val, "get_boxed") else None
                    if file_list is not None and hasattr(file_list, "get_files"):
                        paths = []
                        for f in file_list.get_files():
                            p = f.get_path()
                            if p and cls._is_image_path(p):
                                paths.append(p)
                        if paths:
                            on_success(paths)
                            return
            except Exception:
                pass

            # Step 3: Try reading text (file path or file URI)
            cls._try_read_text(cb, on_success, on_failure)

        try:
            cb.read_value_async(Gdk.FileList, 0, None, on_file_list_read)
        except Exception:
            cls._try_read_text(cb, on_success, on_failure)

    @classmethod
    def _try_read_text(
        cls,
        cb: Gdk.Clipboard,
        on_success: Callable[[List[str]], None],
        on_failure: Callable[[str], None],
    ) -> None:
        def on_text_read(clipboard, res):
            try:
                text = clipboard.read_text_finish(res)
                if text:
                    text = text.strip()
                    lines = text.splitlines()
                    found_paths = []
                    for line in lines:
                        cleaned = line.strip().strip("'\"")
                        if cleaned.startswith("file://"):
                            cleaned = cleaned[7:]
                        if os.path.exists(cleaned) and cls._is_image_path(cleaned):
                            found_paths.append(cleaned)

                    if found_paths:
                        on_success(found_paths)
                        return
            except Exception:
                pass

            # Step 4: Fallback to wl-paste
            cls._try_wl_paste(on_success, on_failure)

        cb.read_text_async(None, on_text_read)

    @classmethod
    def _try_wl_paste(
        cls,
        on_success: Callable[[List[str]], None],
        on_failure: Callable[[str], None],
    ) -> None:
        if shutil.which("wl-paste"):
            try:
                # Check for image types in clipboard
                res_types = subprocess.run(["wl-paste", "--list-types"], capture_output=True, text=True, timeout=1)
                types_out = res_types.stdout if res_types.returncode == 0 else ""
                
                target_type = None
                for t in ["image/png", "image/jpeg", "image/webp"]:
                    if t in types_out:
                        target_type = t
                        break

                if target_type:
                    res_img = subprocess.run(
                        ["wl-paste", "--type", target_type],
                        capture_output=True,
                        timeout=2,
                    )
                    if res_img.returncode == 0 and len(res_img.stdout) > 0:
                        timestamp = int(time.time() * 1000)
                        ext = "png" if "png" in target_type else ("jpg" if "jpeg" in target_type else "webp")
                        cache_file = cls.CACHE_DIR / f"wl_paste_{timestamp}.{ext}"
                        with open(cache_file, "wb") as f:
                            f.write(res_img.stdout)
                        on_success([str(cache_file)])
                        return
            except Exception as e:
                print(f"wl-paste check failed: {e}")

        on_failure("Kein Bild oder kompatibler Bildpfad in der Zwischenablage gefunden.")

    @staticmethod
    def _is_image_path(path: str) -> bool:
        valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".bmp", ".gif", ".tiff"}
        ext = path.lower()[path.rfind("."):] if "." in path else ""
        return ext in valid_exts
