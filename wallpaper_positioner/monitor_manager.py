"""Monitor detection and management for Wayland / Hyprland and GDK."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

import gi
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk


from .i18n import tr


@dataclass
class MonitorInfo:
    id: str                  # e.g. "DP-1" or "0"
    name: str                # e.g. "DP-1", "HDMI-A-1"
    description: str         # Human friendly name, e.g. "Microstep MSI MAG271CQR"
    width: int               # Native pixel width, e.g. 2560
    height: int              # Native pixel height, e.g. 1440
    refresh_rate: float      # e.g. 144.0
    scale: float             # e.g. 1.0
    x: int                   # Desktop offset x
    y: int                   # Desktop offset y
    rel_x: int = 0           # Relative X coordinate on multi-monitor canvas
    rel_y: int = 0           # Relative Y coordinate on multi-monitor canvas
    is_spanned: bool = False # Whether this represents all monitors combined
    is_custom: bool = False  # Custom resolution
    sub_monitors: List[MonitorInfo] = field(default_factory=list)

    @property
    def display_label(self) -> str:
        if self.is_spanned:
            names = " + ".join(s.name for s in self.sub_monitors) if self.sub_monitors else tr("monitor_spanned_name")
            return tr("monitor_spanned_label", names=names, w=self.width, h=self.height)
        if self.is_custom:
            return tr("monitor_custom_label", w=self.width, h=self.height)
        
        rate_str = f" @ {int(round(self.refresh_rate))}Hz" if self.refresh_rate > 0 else ""
        return f"{self.name}: {self.description} ({self.width}x{self.height}{rate_str})"

    @property
    def short_label(self) -> str:
        if self.is_spanned:
            return tr("monitor_spanned_short", w=self.width, h=self.height)
        if self.is_custom:
            return tr("monitor_custom_short", w=self.width, h=self.height)
        return f"{self.name} ({self.width}x{self.height})"


class MonitorManager:
    """Manages connected monitors, prioritizing Hyprland IPC followed by GDK."""

    def __init__(self):
        self.monitors: List[MonitorInfo] = []
        self.custom_monitor: MonitorInfo = MonitorInfo(
            id="__custom__",
            name="Benutzerdefiniert",
            description=tr("monitor_custom_desc"),
            width=1920,
            height=1080,
            refresh_rate=60.0,
            scale=1.0,
            x=0,
            y=0,
            is_custom=True,
        )
        self.refresh()

    def refresh(self) -> List[MonitorInfo]:
        """Detect all monitors currently connected and active."""
        monitors = []
        if shutil.which("hyprctl"):
            monitors = self._query_hyprland()

        if not monitors:
            monitors = self._query_gdk()

        # If still none found, provide fallback standard monitor
        if not monitors:
            monitors.append(
                MonitorInfo(
                    id="default",
                    name="Standard",
                    description="Standard Bildschirm",
                    width=1920,
                    height=1080,
                    refresh_rate=60.0,
                    scale=1.0,
                    x=0,
                    y=0,
                )
            )

        # Add Spanned / Multi-monitor option if more than 1 physical monitor exists
        if len(monitors) > 1:
            min_y = min(m.y for m in monitors)
            monitors_sorted = sorted(monitors, key=lambda m: m.x)
            MONITOR_GAP = 120  # Visible gap between monitors on the canvas
            current_rel_x = 0
            sub_list = []
            for m in monitors_sorted:
                sub_copy = MonitorInfo(
                    id=m.id,
                    name=m.name,
                    description=m.description,
                    width=m.width,
                    height=m.height,
                    refresh_rate=m.refresh_rate,
                    scale=m.scale,
                    x=m.x,
                    y=m.y,
                    rel_x=current_rel_x,
                    rel_y=max(0, m.y - min_y),
                    is_spanned=False,
                )
                sub_list.append(sub_copy)
                current_rel_x += m.width + MONITOR_GAP

            total_w = current_rel_x - MONITOR_GAP
            total_h = max(s.rel_y + s.height for s in sub_list)

            spanned = MonitorInfo(
                id="__spanned__",
                name="Beide Bildschirme nebeneinander",
                description="Alle Bildschirme nebeneinander (separat dargestellt)",
                width=total_w,
                height=total_h,
                refresh_rate=0.0,
                scale=1.0,
                x=0,
                y=0,
                is_spanned=True,
                sub_monitors=sub_list,
            )
            monitors.append(spanned)

        # Always include custom resolution option
        if self.custom_monitor not in monitors:
            monitors.append(self.custom_monitor)

        self.monitors = monitors
        return self.monitors

    def set_custom_resolution(self, width: int, height: int) -> MonitorInfo:
        """Update width and height for custom resolution and return custom MonitorInfo."""
        self.custom_monitor.width = max(100, int(round(width)))
        self.custom_monitor.height = max(100, int(round(height)))
        return self.custom_monitor

    def _query_hyprland(self) -> List[MonitorInfo]:
        """Query active monitors from Hyprland via hyprctl monitors -j."""
        try:
            res = subprocess.run(
                ["hyprctl", "monitors", "-j"],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
            data = json.loads(res.stdout)
            result = []
            for m in data:
                # Only include enabled monitors
                if m.get("disabled", False):
                    continue
                name = m.get("name", "Unknown")
                desc = m.get("description", m.get("model", name))
                w = int(m.get("width", 1920))
                h = int(m.get("height", 1080))
                rate = float(m.get("refreshRate", 60.0))
                scale = float(m.get("scale", 1.0))
                x = int(m.get("x", 0))
                y = int(m.get("y", 0))
                result.append(
                    MonitorInfo(
                        id=name,
                        name=name,
                        description=desc,
                        width=w,
                        height=h,
                        refresh_rate=rate,
                        scale=scale,
                        x=x,
                        y=y,
                    )
                )
            return result
        except Exception as e:
            print(f"Warning: Failed to query Hyprland monitors: {e}")
            return []

    def _query_gdk(self) -> List[MonitorInfo]:
        """Query monitors via GDK4 display API."""
        try:
            display = Gdk.Display.get_default()
            if not display:
                return []
            gdk_monitors = display.get_monitors()
            result = []
            for i in range(gdk_monitors.get_n_items()):
                mon = gdk_monitors.get_item(i)
                geom = mon.get_geometry()
                scale = mon.get_scale_factor()
                model = mon.get_model() or f"Monitor {i+1}"
                desc = mon.get_description() or model
                w = geom.width * scale
                h = geom.height * scale
                result.append(
                    MonitorInfo(
                        id=f"gdk-{i}",
                        name=f"Monitor {i+1}",
                        description=desc,
                        width=w,
                        height=h,
                        refresh_rate=60.0,
                        scale=scale,
                        x=geom.x,
                        y=geom.y,
                    )
                )
            return result
        except Exception as e:
            print(f"Warning: Failed to query GDK monitors: {e}")
            return []

    def _calc_spanned_geometry(self, monitors: List[MonitorInfo]) -> tuple[int, int]:
        """Calculate total bounding box width and height for all physical monitors."""
        min_x = min(m.x for m in monitors)
        min_y = min(m.y for m in monitors)
        max_x = max(m.x + m.width for m in monitors)
        max_y = max(m.y + m.height for m in monitors)
        return max(1920, max_x - min_x), max(1080, max_y - min_y)

    def get_monitor_by_id(self, mon_id: str) -> Optional[MonitorInfo]:
        for m in self.monitors:
            if m.id == mon_id:
                return m
        return self.monitors[0] if self.monitors else None
