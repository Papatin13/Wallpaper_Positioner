"""Adw.Application implementation for Wallpaper Positioner."""

from __future__ import annotations

import sys
from typing import List

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib

from .window import WallpaperWindow


class WallpaperApplication(Adw.Application):
    """Main Application instance."""

    def __init__(self, initial_files: List[str] = None):
        super().__init__(
            application_id="com.github.wallpaperpositioner",
            flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.initial_files = initial_files or []
        self.window: WallpaperWindow = None

    def do_activate(self):
        if not self.window:
            self.window = WallpaperWindow(application=self)
            # Load any initial files passed via CLI
            for f in self.initial_files:
                if f.lower().endswith(".wpp") or f.lower().endswith(".json"):
                    self.window.open_project_file(f)
                else:
                    self.window.canvas.add_layer_from_path(f)
        self.window.present()

    def do_open(self, files, n_files, hint):
        self.activate()
        if self.window:
            for i in range(n_files):
                p = files[i].get_path()
                if p:
                    if p.lower().endswith(".wpp") or p.lower().endswith(".json"):
                        self.window.open_project_file(p)
                    else:
                        self.window.canvas.add_layer_from_path(p)


def run_app():
    """Entry point for running the application."""
    initial_files = sys.argv[1:] if len(sys.argv) > 1 else []
    app = WallpaperApplication(initial_files=initial_files)
    return app.run([sys.argv[0]])
