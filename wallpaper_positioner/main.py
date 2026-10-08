#!/usr/bin/env python3
"""CLI and launcher script for Wallpaper Positioner."""

import sys
import os

# Add parent directory to sys.path so it works without package installation
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wallpaper_positioner.app import run_app

if __name__ == "__main__":
    sys.exit(run_app())
