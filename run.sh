#!/usr/bin/env bash
# Startscript für Wallpaper Positioner
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/wallpaper_positioner/main.py" "$@"
