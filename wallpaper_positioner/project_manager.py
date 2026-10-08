"""Project saving and loading for Wallpaper Positioner."""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .models import Layer
from .monitor_manager import MonitorInfo


class ProjectManager:
    """Handles serialization and deserialization of wallpaper projects (.wpp)."""

    CACHE_DIR = Path.home() / ".cache" / "wallpaper_positioner"
    RESTORE_DIR = CACHE_DIR / "restored"
    SESSION_FILE = CACHE_DIR / "last_session.wpp"

    @classmethod
    def _is_temp_or_cache_path(cls, path: str) -> bool:
        """Check if path is in temp or cache directory (e.g. pasted screenshots)."""
        p = os.path.abspath(path)
        cache_str = str(cls.CACHE_DIR)
        return p.startswith("/tmp") or p.startswith("/var/tmp") or p.startswith(cache_str)

    @classmethod
    def _encode_image(cls, path: str, max_size_bytes: int = 35 * 1024 * 1024) -> Optional[str]:
        """Encode image file to base64 string for standalone embedding."""
        try:
            if os.path.exists(path) and os.path.getsize(path) <= max_size_bytes:
                with open(path, "rb") as f:
                    return base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            print(f"ProjectManager: failed to encode image {path}: {e}")
        return None

    @classmethod
    def _decode_image(cls, name: str, b64_str: str) -> Optional[str]:
        """Decode base64 string into a persistent cached image file."""
        try:
            cls.RESTORE_DIR.mkdir(parents=True, exist_ok=True)
            safe_name = os.path.basename(name) or "restored_image.png"
            target_path = cls.RESTORE_DIR / f"{int(time.time() * 1000)}_{safe_name}"
            raw_bytes = base64.b64decode(b64_str.encode("ascii"))
            with open(target_path, "wb") as f:
                f.write(raw_bytes)
            return str(target_path)
        except Exception as e:
            print(f"ProjectManager: failed to decode embedded image {name}: {e}")
            return None

    @classmethod
    def serialize(
        cls,
        monitor: MonitorInfo,
        bg_color: Tuple[int, int, int],
        layers: List[Layer],
        canvas_defaults: Optional[Dict[str, Any]] = None,
        viewport: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Serialize current canvas session into a project dictionary."""
        layers_data = []
        for l in layers:
            item: Dict[str, Any] = {
                "name": l.name,
                "file_path": l.file_path,
                "x": float(l.x),
                "y": float(l.y),
                "width": float(l.width),
                "height": float(l.height),
                "rotation": float(l.rotation),
                "opacity": float(l.opacity),
                "visible": bool(l.visible),
                "locked": bool(l.locked),
                "orig_width": int(l.orig_width),
                "orig_height": int(l.orig_height),
                "aspect_ratio": float(l.aspect_ratio),
                # Border & Frame
                "border_width": float(l.border_width),
                "border_color": list(l.border_color),
                "border_radius": float(l.border_radius),
                "monitor_name": l.monitor_name,
                # Shadow
                "shadow_enabled": bool(l.shadow_enabled),
                "shadow_blur": float(l.shadow_blur),
                "shadow_offset_x": float(l.shadow_offset_x),
                "shadow_offset_y": float(l.shadow_offset_y),
                "shadow_opacity": float(l.shadow_opacity),
                "shadow_color": list(l.shadow_color),
            }

            # Embed base64 backup for temp / clipboard images or always as safety
            # If the path is temporary or clipboard-generated, embedding is mandatory
            # For regular files, we embed if <= 20MB so project is completely portable
            if l.file_path and os.path.exists(l.file_path):
                should_embed = cls._is_temp_or_cache_path(l.file_path) or (
                    os.path.getsize(l.file_path) <= 20 * 1024 * 1024
                )
                if should_embed:
                    b64_data = cls._encode_image(l.file_path)
                    if b64_data:
                        item["embedded_data"] = b64_data

            layers_data.append(item)

        sub_mons = []
        if monitor.is_spanned and monitor.sub_monitors:
            for s in monitor.sub_monitors:
                sub_mons.append({
                    "name": s.name,
                    "width": s.width,
                    "height": s.height,
                    "rel_x": s.rel_x,
                    "rel_y": s.rel_y,
                })

        return {
            "format": "WallpaperPositionerProject",
            "version": 1,
            "created_at": time.time(),
            "monitor": {
                "name": monitor.name,
                "width": monitor.width,
                "height": monitor.height,
                "is_spanned": monitor.is_spanned,
                "is_custom": getattr(monitor, "is_custom", False),
                "sub_monitors": sub_mons,
            },
            "bg_color": list(bg_color),
            "canvas_defaults": canvas_defaults or {},
            "viewport": viewport or {},
            "layers": layers_data,
        }

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> Tuple[Dict[str, Any], Tuple[int, int, int], List[Layer], Dict[str, Any], Dict[str, Any]]:
        """
        Deserialize project dictionary back into objects.
        Returns (monitor_dict, bg_color, list_of_layers, canvas_defaults, viewport).
        """
        bg_color_raw = data.get("bg_color", [26, 27, 38])
        bg_color = (int(bg_color_raw[0]), int(bg_color_raw[1]), int(bg_color_raw[2]))
        mon_data = data.get("monitor", {})
        canvas_defaults = data.get("canvas_defaults", {})
        viewport = data.get("viewport", {})

        layers: List[Layer] = []
        sub_mons_data = mon_data.get("sub_monitors", [])
        is_spanned = bool(mon_data.get("is_spanned"))

        for ld in data.get("layers", []):
            file_path = ld.get("file_path", "")

            # Check if file exists; if not, check embedded data
            if (not file_path or not os.path.exists(file_path)) and "embedded_data" in ld:
                restored = cls._decode_image(ld.get("name", "layer.png"), ld["embedded_data"])
                if restored:
                    file_path = restored

            if not file_path or not os.path.exists(file_path):
                # Cannot reconstruct layer without valid image file
                print(f"ProjectManager: image path not found and cannot restore: {file_path}")
                continue

            b_color = ld.get("border_color", [255, 255, 255])
            s_color = ld.get("shadow_color", [0, 0, 0])

            raw_x = float(ld.get("x", 0.0))
            raw_y = float(ld.get("y", 0.0))
            mon_name = ld.get("monitor_name", "")

            # Legacy migration: if monitor_name wasn't saved and project is spanned,
            # determine target sub-monitor and convert global canvas coords to local monitor coords
            if not mon_name:
                if is_spanned and len(sub_mons_data) >= 2:
                    sub0 = sub_mons_data[0]
                    sub1 = sub_mons_data[1]
                    # If x is >= sub0 width, assign to sub1
                    s0_w = sub0.get("width", 1920)
                    if raw_x >= s0_w:
                        mon_name = sub1.get("name", "")
                        raw_x = raw_x - sub1.get("rel_x", s0_w)
                        raw_y = raw_y - sub1.get("rel_y", 0)
                    else:
                        mon_name = sub0.get("name", "")
                        raw_x = raw_x - sub0.get("rel_x", 0)
                        raw_y = max(0.0, raw_y - sub0.get("rel_y", 0))
                else:
                    mon_name = mon_data.get("name", "")

            layer = Layer(
                file_path=file_path,
                name=ld.get("name", ""),
                x=raw_x,
                y=raw_y,
                width=float(ld.get("width", 100.0)),
                height=float(ld.get("height", 100.0)),
                rotation=float(ld.get("rotation", 0.0)),
                opacity=float(ld.get("opacity", 1.0)),
                visible=bool(ld.get("visible", True)),
                locked=bool(ld.get("locked", False)),
                monitor_name=mon_name,
                border_width=float(ld.get("border_width", 0.0)),
                border_color=(int(b_color[0]), int(b_color[1]), int(b_color[2])),
                border_radius=float(ld.get("border_radius", 0.0)),
                shadow_enabled=bool(ld.get("shadow_enabled", False)),
                shadow_blur=float(ld.get("shadow_blur", 20.0)),
                shadow_offset_x=float(ld.get("shadow_offset_x", 0.0)),
                shadow_offset_y=float(ld.get("shadow_offset_y", 15.0)),
                shadow_opacity=float(ld.get("shadow_opacity", 0.5)),
                shadow_color=(int(s_color[0]), int(s_color[1]), int(s_color[2])),
            )
            layers.append(layer)

        return mon_data, bg_color, layers, canvas_defaults, viewport

    @classmethod
    def save_to_file(cls, path: str, project_data: Dict[str, Any]) -> bool:
        """Write project dictionary as JSON to disk."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"ProjectManager: error saving to {path}: {e}")
            return False

    @classmethod
    def load_from_file(cls, path: str) -> Optional[Dict[str, Any]]:
        """Read and parse project JSON file from disk."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"ProjectManager: error reading {path}: {e}")
            return None

    @classmethod
    def save_session(cls, project_data: Dict[str, Any]) -> bool:
        """Save autosave session to cache."""
        try:
            cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            return cls.save_to_file(str(cls.SESSION_FILE), project_data)
        except Exception:
            return False

    @classmethod
    def load_session(cls) -> Optional[Dict[str, Any]]:
        """Load autosave session from cache if exists."""
        if cls.SESSION_FILE.exists():
            return cls.load_from_file(str(cls.SESSION_FILE))
        return None
