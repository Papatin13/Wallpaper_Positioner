"""Internationalization (i18n) and localization support for Wallpaper Positioner."""

from __future__ import annotations

import os
from typing import Dict, Any, Optional

# Supported languages: "de" (Deutsch), "en" (English)
_current_language: str = "en"

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "de": {
        # App / Window
        "app_title": "Wallpaper Positioner",
        "app_title_with_file": "Wallpaper Positioner — {filename}",
        
        # HeaderBar Buttons & Tooltips
        "new_project": "Neues Projekt (Strg+N)",
        "open_project": "Projekt öffnen (Strg+O)",
        "save_project": "Projekt speichern (Strg+S)",
        "add_images": "Bilder hinzufügen (Strg+O)",
        "paste_clipboard": "Aus Zwischenablage einfügen (Strg+V)",
        "rescan_monitors": "Monitore neu erkennen",
        "zoom_out": "Verkleinern (-)",
        "zoom_fit": "Einpassen (0)",
        "zoom_in": "Vergrößern (+)",
        "main_menu": "Hauptmenü",
        "toggle_sidebar": "Seitenleiste ein-/ausblenden",
        "set_wallpaper": "Als Wallpaper setzen",
        "export_wallpaper": "Exportieren...",
        "export_tooltip": "Wallpaper als Bilddatei speichern (Strg+E)",
        "apply_tooltip_single": "Direkt für {name} in Hyprland aktivieren",
        "apply_tooltip_multi": "Slices automatisch für beide Bildschirme in Hyprland aktivieren",
        "apply_tooltip_custom": "Als Wallpaper für den Desktop aktivieren (oder Bild exportieren)",

        # Status Overlay
        "tip_drag_drop": "Tipp: Bilder per Drag & Drop auf das Canvas ziehen",
        "zoom_label": "Zoom",
        "images_count": "{count} Bild",
        "images_count_plural": "{count} Bilder",
        "selected_count": "{count} ausgewählt",

        # Monitor Section
        "section_monitor": "BILDSCHIRM & AUFLÖSUNG",
        "monitor_res_label": "Auflösung: {w} x {h} px",
        "spanned_title": "Nebeneinander: {subs}",
        "spanned_area": "Gesamtfläche: {w} x {h} px{boundary}",
        "spanned_boundary": " • Lücke/Trennung bei x={boundaries}px",
        "mon_switch_all": "🖥️ Alle",
        "mon_switch_custom": "📐 Eigene",
        "switch_to_mon": "Zu {name} ({w}x{h}) wechseln",
        "custom_res_title": "EIGENE CANVAS-AUFLÖSUNG",
        "custom_mon_name": "Eigene Canvas-Auflösung (Benutzerdefiniert)",
        "width_short": "B:",
        "height_short": "H:",
        "swap_dimensions_tip": "Breite und Höhe vertauschen (Quer- / Hochformat)",
        "presets_label": "Presets:",
        "apply_custom_res": "Eigene Auflösung anwenden",
        "apply_custom_res_tip": "Schaltet das Canvas auf die gewählte Auflösung um",

        # Canvas Background & Colors
        "section_bg": "CANVAS HINTERGRUNDFARBE",
        "select_color": "Farbe wählen:",
        "match_bg_to_image": "Hintergrund an Bild anpassen",
        "match_bg_tip": "Passt die Hintergrundfarbe auf Knopfdruck an die stärkste Hauptfarbe des Bildes an",
        "dominant_colors": "Hauptfarben der Bilder:",
        "recalc_palette": "Farbpalette neu aus Bildern extrahieren",
        "set_color_as_bg": "Farbe {hex} als Hintergrund setzen",
        "always_auto_adapt": "Immer automatisch anpassen:",

        # Layout & Spacing
        "section_layout": "LAYOUT & AUTO-ANPASSUNG",
        "layout_desc": "Alle Bilder automatisch im Canvas anordnen:",
        "mode_dynamic": "Dynamisch",
        "mode_grid": "Raster",
        "mode_row": "Reihe",
        "mode_col": "Spalte",
        "mode_monitors": "Monitore",
        "tip_mode_dynamic": "Dynamische Flächenaufteilung (größere Bilder erhalten mehr Platz)",
        "tip_mode_grid": "Gleichmäßiges Raster (Zeilen und Spalten)",
        "tip_mode_row": "Bilder nebeneinander in einer Reihe",
        "tip_mode_col": "Bilder untereinander in einer Spalte",
        "tip_mode_monitors": "Bilder gleichmäßig auf Bildschirme aufteilen",
        "margin_label": "Randabstand (Canvas):",
        "gap_label": "Bildabstand (Zwischenraum):",
        "cover_label": "Zelle ganz ausfüllen (Cover):",
        "btn_layout_apply": "Bilder jetzt anordnen",

        # Layer Details
        "section_selected": "AUSGEWÄHLTES BILD",
        "section_selected_multi": "{count} Bilder ausgewählt (Mehrfachauswahl)",
        "no_layer_selected": "Kein Bild ausgewählt",
        "rotation_label": "Drehung:",
        "opacity_label": "Deckkraft:",
        "btn_reset_rotation": "Drehung auf 0° zurücksetzen",
        "section_border": "BILDRAHMEN & STIL",
        "border_width": "Rahmen-Dicke:",
        "border_none": "Kein Rahmen",
        "border_classic": "Klassischer Rahmen (8px)",
        "border_color": "Rahmen-Farbe:",
        "preset_white": "Weiß",
        "preset_black": "Schwarz",
        "preset_accent": "Akzent",
        "preset_gold": "Gold",
        "corner_radius": "Eckenrundung:",
        "radius_square": "0px",
        "radius_square_tip": "Eckig",
        "radius_rounded": "16px",
        "radius_rounded_tip": "Modern abgerundet (16px)",
        "section_shadow": "SCHATTEN (DROP SHADOW)",
        "enable_shadow": "Schatten aktivieren:",
        "shadow_blur": "Unschärfe:",
        "shadow_opacity": "Deckkraft:",
        "shadow_offset_x": "Offset X:",
        "shadow_offset_y": "Y:",
        "shadow_color": "Schatten-Farbe:",
        "shadow_preset_subtle": "Dezent",
        "shadow_preset_standard": "Standard",
        "shadow_preset_floating": "Schwebend",
        "shadow_preset_glow": "Glow",
        "shadow_tip_subtle": "Leichter, unaufdringlicher Schatten (Blur 15px, Y 8px)",
        "shadow_tip_standard": "Klassischer Schlagschatten (Blur 25px, Y 15px)",
        "shadow_tip_floating": "Tiefer 3D-Schwebeschatten (Blur 45px, Y 25px)",
        "shadow_tip_glow": "Rundum-Schein ohne Versatz (Blur 30px)",
        "section_style_actions": "STIL-AKTIONEN",
        "apply_style_all": "Stil auf alle Bilder anwenden",
        "apply_style_all_tip": "Wendet Rahmen und Schatten des ausgewählten Bildes auf alle vorhandenen Bilder an",
        "style_hint": "Hinweis: Neue Bilder übernehmen diesen Stil automatisch.",
        "quick_align": "Schnellausrichtung:",

        # Layer Arrangement
        "section_arrange": "ANORDNUNG & POSITION",
        "layer_bring_front": "Ganz nach oben",
        "layer_step_forward": "Eine Ebene vor",
        "layer_step_backward": "Eine Ebene zurück",
        "layer_send_back": "Ganz nach unten",
        "layer_delete": "Ausgewählte Bilder löschen (Entf)",
        "center_label": "Zentrieren",
        "fit_label": "Einpassen",
        "fill_label": "Ausfüllen",
        "align_monitor": "Auf Monitor:",
        "center_on_sub": "Auf {name} ({w}x{h}) zentrieren",

        # Layer List
        "section_layers": "BILDER / LAYER ({count})",
        "layer_overview": "EBENEN-ÜBERSICHT",
        "no_layers": "Keine Bilder auf dem Canvas",

        # Menu
        "menu_new_project": "Neues Projekt (Strg+N)",
        "menu_open_project": "Projekt öffnen... (Strg+O)",
        "menu_save_project": "Projekt speichern (Strg+S)",
        "menu_save_project_as": "Projekt speichern unter... (Strg+Umschalt+S)",
        "menu_export": "Als Bild exportieren... (Strg+E)",
        "menu_apply": "Als Wallpaper setzen",
        "menu_rescan": "Monitore neu erkennen",
        "menu_custom_res": "Eigene Canvas-Auflösung...",
        "menu_language": "Sprache / Language",
        "menu_switch_language": "Sprache wechseln (Deutsch / English)",

        # Toasts & Dialogs
        "toast_new_project": "Neues Projekt gestartet.",
        "toast_project_loaded": "Projekt geladen: {filename} ({count} Bilder)",
        "toast_session_restored": "Letzte Bearbeitung wiederhergestellt ({count} Bilder)",
        "toast_project_saved": "Projekt gespeichert: {filename}",
        "toast_save_error": "Fehler beim Speichern des Projekts.",
        "toast_project_load_error": "Fehler beim Laden von: {filename}",
        "toast_project_apply_error": "Fehler beim Anwenden der Projektdaten.",
        "toast_images_added": "{count} Bild(er) hinzugefügt.",
        "toast_images_pasted": "{count} Bild(er) aus der Zwischenablage eingefügt.",
        "toast_no_clipboard": "Kein Bild in der Zwischenablage gefunden.",
        "toast_wallpaper_saved": "Wallpaper gespeichert: {filename}",
        "toast_export_error": "Fehler beim Exportieren.",
        "toast_monitors_rescanned": "Bildschirme neu gescannt.",
        "toast_custom_res_applied": "Canvas auf eigene Auflösung gesetzt: {w} × {h} px",
        "toast_style_applied_all": "Stil (Rahmen & Schatten) auf alle {count} Bild{suffix} angewendet.",
        "toast_images_arranged": "Bilder angepasst: {mode} (Rand {m}px, Abstand {g}px)",
        "toast_no_images_to_arrange": "Keine Bilder zum Anordnen vorhanden.",
        "toast_no_images_on_canvas": "Keine Bilder auf dem Canvas vorhanden.",
        "toast_bg_color_adapted": "Hintergrundfarbe an Bild{target} angepasst: {hex}",
        "toast_bg_color_set": "Hintergrundfarbe gesetzt: {hex}",
        "toast_language_switched": "Sprache auf Deutsch umgestellt.",
        "file_filter_projects": "Wallpaper Positioner Projekt (*.wpp, *.json)",
        "dialog_open_project": "Projekt öffnen",
        "dialog_save_project": "Projekt speichern",
        "dialog_add_images": "Bilder hinzufügen",
        "dialog_export_wallpaper": "Wallpaper exportieren",

        # Monitor Names
        "monitor_spanned_name": "Beide Bildschirme nebeneinander",
        "monitor_spanned_desc": "Alle Bildschirme nebeneinander (separat dargestellt)",
        "monitor_spanned_short": "Nebeneinander ({w}x{h})",
        "monitor_spanned_label": "Nebeneinander: {names} ({w}x{h})",
        "monitor_custom_name": "Benutzerdefiniert",
        "monitor_custom_desc": "Eigene Canvas-Auflösung",
        "monitor_custom_short": "Benutzerdefiniert ({w}x{h})",
        "monitor_custom_label": "Benutzerdefiniert ({w}x{h})",
        "monitor_default_name": "Standard",
        "monitor_default_desc": "Standard Bildschirm",
        "canvas_badge_custom": "Canvas: {name} • {w} × {h} px",
        "canvas_badge_monitor": "Monitor: {name} • {w} × {h} px",
    },
    "en": {
        # App / Window
        "app_title": "Wallpaper Positioner",
        "app_title_with_file": "Wallpaper Positioner — {filename}",

        # HeaderBar Buttons & Tooltips
        "new_project": "New Project (Ctrl+N)",
        "open_project": "Open Project (Ctrl+O)",
        "save_project": "Save Project (Ctrl+S)",
        "add_images": "Add Images (Ctrl+O)",
        "paste_clipboard": "Paste from Clipboard (Ctrl+V)",
        "rescan_monitors": "Rescan Monitors",
        "zoom_out": "Zoom Out (-)",
        "zoom_fit": "Fit to View (0)",
        "zoom_in": "Zoom In (+)",
        "main_menu": "Main Menu",
        "toggle_sidebar": "Toggle Sidebar",
        "set_wallpaper": "Set as Wallpaper",
        "export_wallpaper": "Export...",
        "export_tooltip": "Save wallpaper as image file (Ctrl+E)",
        "apply_tooltip_single": "Apply directly for {name} in Hyprland",
        "apply_tooltip_multi": "Automatically apply slices to both monitors in Hyprland",
        "apply_tooltip_custom": "Apply as desktop wallpaper (or export image)",

        # Status Overlay
        "tip_drag_drop": "Tip: Drag & drop images onto the canvas",
        "zoom_label": "Zoom",
        "images_count": "{count} image",
        "images_count_plural": "{count} images",
        "selected_count": "{count} selected",

        # Monitor Section
        "section_monitor": "MONITOR & RESOLUTION",
        "monitor_res_label": "Resolution: {w} x {h} px",
        "spanned_title": "Spanned: {subs}",
        "spanned_area": "Total Area: {w} x {h} px{boundary}",
        "spanned_boundary": " • Gap/Separation at x={boundaries}px",
        "mon_switch_all": "🖥️ All",
        "mon_switch_custom": "📐 Custom",
        "switch_to_mon": "Switch to {name} ({w}x{h})",
        "custom_res_title": "CUSTOM CANVAS RESOLUTION",
        "custom_mon_name": "Custom Canvas Resolution",
        "width_short": "W:",
        "height_short": "H:",
        "swap_dimensions_tip": "Swap width and height (Landscape / Portrait)",
        "presets_label": "Presets:",
        "apply_custom_res": "Apply Custom Resolution",
        "apply_custom_res_tip": "Switches the canvas to the selected resolution",

        # Canvas Background & Colors
        "section_bg": "CANVAS BACKGROUND COLOR",
        "select_color": "Pick color:",
        "match_bg_to_image": "Match Background to Image",
        "match_bg_tip": "Sets background color to the most dominant color from images",
        "dominant_colors": "Dominant Image Colors:",
        "recalc_palette": "Extract color palette from images again",
        "set_color_as_bg": "Set color {hex} as background",
        "always_auto_adapt": "Always adapt automatically:",

        # Layout & Spacing
        "section_layout": "LAYOUT & AUTO-ARRANGE",
        "layout_desc": "Automatically arrange all images on canvas:",
        "mode_dynamic": "Dynamic",
        "mode_grid": "Grid",
        "mode_row": "Row",
        "mode_col": "Column",
        "mode_monitors": "Monitors",
        "tip_mode_dynamic": "Dynamic proportional area (larger images receive more space)",
        "tip_mode_grid": "Uniform grid (rows and columns)",
        "tip_mode_row": "Images side by side in a row",
        "tip_mode_col": "Images stacked in a column",
        "tip_mode_monitors": "Distribute images across monitors evenly",
        "margin_label": "Canvas Margin:",
        "gap_label": "Image Spacing (Gap):",
        "cover_label": "Fill entire cell (Cover):",
        "btn_layout_apply": "Arrange Images Now",

        # Layer Details
        "section_selected": "SELECTED IMAGE",
        "section_selected_multi": "{count} images selected (Multiple selection)",
        "no_layer_selected": "No image selected",
        "rotation_label": "Rotation:",
        "opacity_label": "Opacity:",
        "btn_reset_rotation": "Reset rotation to 0°",
        "section_border": "BORDER & STYLE",
        "border_width": "Border width:",
        "border_none": "No border",
        "border_classic": "Classic border (8px)",
        "border_color": "Border color:",
        "preset_white": "White",
        "preset_black": "Black",
        "preset_accent": "Accent",
        "preset_gold": "Gold",
        "corner_radius": "Corner radius:",
        "radius_square": "0px",
        "radius_square_tip": "Square",
        "radius_rounded": "16px",
        "radius_rounded_tip": "Modern rounded (16px)",
        "section_shadow": "DROP SHADOW",
        "enable_shadow": "Enable shadow:",
        "shadow_blur": "Blur:",
        "shadow_opacity": "Opacity:",
        "shadow_offset_x": "Offset X:",
        "shadow_offset_y": "Y:",
        "shadow_color": "Shadow color:",
        "shadow_preset_subtle": "Subtle",
        "shadow_preset_standard": "Standard",
        "shadow_preset_floating": "Floating",
        "shadow_preset_glow": "Glow",
        "shadow_tip_subtle": "Subtle, unobtrusive shadow (Blur 15px, Y 8px)",
        "shadow_tip_standard": "Classic drop shadow (Blur 25px, Y 15px)",
        "shadow_tip_floating": "Deep 3D floating shadow (Blur 45px, Y 25px)",
        "shadow_tip_glow": "Uniform halo glow without offset (Blur 30px)",
        "section_style_actions": "STYLE ACTIONS",
        "apply_style_all": "Apply style to all images",
        "apply_style_all_tip": "Applies border and shadow of selected image to all other images",
        "style_hint": "Note: New images inherit this style automatically.",
        "quick_align": "Quick Alignment:",

        # Layer Arrangement
        "section_arrange": "ARRANGEMENT & POSITION",
        "layer_bring_front": "Bring to Front",
        "layer_step_forward": "Bring Forward",
        "layer_step_backward": "Send Backward",
        "layer_send_back": "Send to Back",
        "layer_delete": "Delete selected images (Del)",
        "center_label": "Center",
        "fit_label": "Fit",
        "fill_label": "Fill",
        "align_monitor": "On Monitor:",
        "center_on_sub": "Center on {name} ({w}x{h})",

        # Layer List
        "section_layers": "IMAGES / LAYERS ({count})",
        "layer_overview": "LAYER OVERVIEW",
        "no_layers": "No images on canvas",

        # Menu
        "menu_new_project": "New Project (Ctrl+N)",
        "menu_open_project": "Open Project... (Ctrl+O)",
        "menu_save_project": "Save Project (Ctrl+S)",
        "menu_save_project_as": "Save Project As... (Ctrl+Shift+S)",
        "menu_export": "Export as Image... (Ctrl+E)",
        "menu_apply": "Set as Wallpaper",
        "menu_rescan": "Rescan Monitors",
        "menu_custom_res": "Custom Canvas Resolution...",
        "menu_language": "Language / Sprache",
        "menu_switch_language": "Switch Language (Deutsch / English)",

        # Toasts & Dialogs
        "toast_new_project": "New project started.",
        "toast_project_loaded": "Project loaded: {filename} ({count} images)",
        "toast_session_restored": "Restored last session ({count} images)",
        "toast_project_saved": "Project saved: {filename}",
        "toast_save_error": "Error saving project.",
        "toast_project_load_error": "Error loading: {filename}",
        "toast_project_apply_error": "Error applying project data.",
        "toast_images_added": "{count} image(s) added.",
        "toast_images_pasted": "{count} image(s) pasted from clipboard.",
        "toast_no_clipboard": "No image found in clipboard.",
        "toast_wallpaper_saved": "Wallpaper saved: {filename}",
        "toast_export_error": "Error exporting wallpaper.",
        "toast_monitors_rescanned": "Monitors rescanned.",
        "toast_custom_res_applied": "Canvas set to custom resolution: {w} × {h} px",
        "toast_style_applied_all": "Style (border & shadow) applied to all {count} image{suffix}.",
        "toast_images_arranged": "Images arranged: {mode} (Margin {m}px, Spacing {g}px)",
        "toast_no_images_to_arrange": "No images to arrange.",
        "toast_no_images_on_canvas": "No images on canvas.",
        "toast_bg_color_adapted": "Background color adapted to image{target}: {hex}",
        "toast_bg_color_set": "Background color set: {hex}",
        "toast_language_switched": "Language switched to English.",
        "file_filter_projects": "Wallpaper Positioner Project (*.wpp, *.json)",
        "dialog_open_project": "Open Project",
        "dialog_save_project": "Save Project",
        "dialog_add_images": "Add Images",
        "dialog_export_wallpaper": "Export Wallpaper",

        # Monitor Names
        "monitor_spanned_name": "All monitors side by side",
        "monitor_spanned_desc": "All monitors side by side (rendered separately)",
        "monitor_spanned_short": "Spanned ({w}x{h})",
        "monitor_spanned_label": "Side-by-side: {names} ({w}x{h})",
        "monitor_custom_name": "Custom",
        "monitor_custom_desc": "Custom canvas resolution",
        "monitor_custom_short": "Custom ({w}x{h})",
        "monitor_custom_label": "Custom ({w}x{h})",
        "monitor_default_name": "Default",
        "monitor_default_desc": "Default Display",
        "canvas_badge_custom": "Canvas: {name} • {w} × {h} px",
        "canvas_badge_monitor": "Monitor: {name} • {w} × {h} px",
    }
}


def detect_system_language() -> str:
    """Detect default system language: returns 'de' if German, otherwise 'en'."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "").strip()
        if val:
            code = val.split(".")[0].split("_")[0].lower()
            if code == "de":
                return "de"
            elif code:
                return "en"
    return "en"


def init_language(forced_lang: Optional[str] = None):
    """Initialize active language from environment or explicit choice."""
    global _current_language
    if forced_lang in TRANSLATIONS:
        _current_language = forced_lang
    else:
        _current_language = detect_system_language()


# Automatically initialize upon import
init_language()


def set_language(lang: str):
    """Switch active UI language ('de' or 'en')."""
    global _current_language
    if lang in TRANSLATIONS:
        _current_language = lang


def get_language() -> str:
    """Get active language code ('de' or 'en')."""
    return _current_language


def tr(key: str, **kwargs) -> str:
    """Translate string key for the active language with optional format arguments."""
    lang_dict = TRANSLATIONS.get(_current_language, TRANSLATIONS["en"])
    template = lang_dict.get(key)
    if template is None:
        template = TRANSLATIONS["en"].get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template
