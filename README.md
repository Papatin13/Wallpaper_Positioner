# 🎨 Wallpaper Positioner

<div align="center">

![Wallpaper Positioner Banner](docs/screenshots/app_window.png)

**A modern, powerful image composition and wallpaper tool for Linux (Wayland & X11).**  
*Built with Python, GTK 4, Libadwaita, and Cairo.*

[English](#-english) • [Deutsch](#-deutsch) • [Features](#-features) • [Installation & Start](#-starten--installation)

</div>

---

## 📸 Screenshots

| 🖥️ Dual-Monitor Canvas (Deutsch) | 🌐 English UI Localization |
| :---: | :---: |
| ![Wallpaper Positioner UI](docs/screenshots/app_window.png) | ![Wallpaper Positioner English UI](docs/screenshots/app_window_en.png) |

---

## 🇩🇪 Deutsch

**Wallpaper Positioner** ist ein modernes Desktop-Werkzeug für Linux, mit dem du Bilder frei auf einem hochauflösenden Canvas anordnen, skalieren, rotieren, mit Rahmen und 3D-Schlagschatten versehen und direkt als Desktop-Wallpaper für deinen Monitor (oder mehrere Monitore) aktivieren kannst.

### ✨ Highlights
- **Multi-Monitor-Unterstützung:** Erkennt Monitore automatisch (Hyprland IPC & GDK-Fallback). Zeigt Monitore wahlweise separat mit sichtbarer Lücke oder einzeln an.
- **Eigene Canvas-Auflösung (Custom Resolution):** Wähle zwischen deinen physischen Bildschirmen oder stelle benutzerdefinierte Auflösungen (FHD, 2K, 4K, 21:9, 9:16, 1:1) ein.
- **Dynamisches Auto-Layout:** Ordnet Bilder auf Knopfdruck an. Größere Bilder erhalten proportional mehr Raum als kleinere. Schieberegler für Randabstand und Zwischenräume mit Live-Vorschau.
- **Stil & Effekte:** Rahmenstärke, Eckenrundung, Farben und 4 Schatten-Presets (*Dezent*, *Standard*, *Schwebend*, *Glow*).
- **Mehrfachauswahl & Gruppenaktionen:** Bilder mit `Strg`/`Shift`+Klick oder Rahmenauswahl (Gummiband) markieren, gemeinsam verschieben, drehen, skalieren oder stylen.
- **Farbharmonien:** Extrahiert dominante Farbpaletten aus deinen Bildern und passt die Hintergrundfarbe auf Wunsch an.
- **Zwischenablage (`Strg+V`):** Screenshots direkt einfügen und sofort platzieren.
- **Projektdateien (`.wpp`):** Speichere deine Layouts verlustfrei als editierbare Projekte oder exportiere sie als PNG/JPEG.
- **1-Klick Wallpaper-Aktivierung:** Unterstützt automatisch alle gängigen Wayland-Wallpaper-Daemons (`DMS`, `hyprpaper`, `swww`, `awww`, `swaybg`).
- **Zweisprachig:** Erkennt automatisch die Systemsprache (Deutsch oder Englisch) und bietet einen Sprachumschalter im Hauptmenü.

---

## 🇬🇧 English

**Wallpaper Positioner** is a native Linux desktop application for arranging, styling, and rendering multi-image desktop wallpapers across single or multi-monitor setups.

### ✨ Key Features
- **Multi-Monitor Awareness:** Automatically queries displays via Hyprland IPC or GDK fallback. Displays physical screens side-by-side with separate visual chassis and gap.
- **Custom Canvas Resolution:** Design wallpapers for any custom dimension with built-in presets (FHD, 2K, 4K, Ultrawide 21:9, Portrait 9:16, Square 1:1) and aspect-ratio swapping.
- **Dynamic Auto-Layout:** Proportional space distribution where larger artwork receives proportionally more canvas space. Real-time margin and gap sliders.
- **Drop Shadows & Borders:** Gaussian blur drop shadows with 4 quick presets (*Subtle*, *Standard*, *Floating*, *Glow*), custom offsets, opacity, border width, and rounded corners.
- **Rubberband & Multi-Selection:** Select multiple images with `Shift`/`Ctrl` or drag a selection box over the canvas to transform, rotate, style, or align them simultaneously.
- **Color Engine:** Automatically extracts dominant palettes from loaded artwork and lets you set matching canvas background tones with one click.
- **Clipboard Paste (`Ctrl+V`):** Seamlessly paste screenshots or copied images directly onto the canvas.
- **Editable Project Files (`.wpp`):** Save your entire canvas state and restore sessions anytime.
- **Native Wayland Daemon Integration:** One-click apply supports `DMS` (DankMaterialShell), `hyprpaper`, `swww`, `awww`, and `swaybg`.
- **Bilingual (i18n):** Automatically matches your system locale (German / English) with an on-the-fly language toggle in the menu.

---

## ⌨️ Steuerung & Tastenkürzel / Shortcuts

| Aktion / Action | Tastenkürzel / Shortcut | Beschreibung / Description |
| :--- | :--- | :--- |
| **Projekt speichern** | `Strg+S` / `Ctrl+S` | Speichert das Projekt als `.wpp` / Save project |
| **Projekt speichern unter** | `Strg+Umschalt+S` / `Ctrl+Shift+S` | Neuer Dateiname / Save project as |
| **Projekt öffnen** | `Strg+O` / `Ctrl+O` | Vorhandenes Projekt laden / Open project |
| **Neues Projekt** | `Strg+N` / `Ctrl+N` | Neues leeres Canvas / Blank new canvas |
| **Wallpaper exportieren** | `Strg+E` / `Ctrl+E` | Als PNG/JPEG exportieren / Export image |
| **Einfügen aus Zwischenablage** | `Strg+V` / `Ctrl+V` | Bild aus Clipboard einfügen / Paste image |
| **Alle Bilder auswählen** | `Strg+A` / `Ctrl+A` | Wählt alle Ebenen aus / Select all layers |
| **Auswahl aufheben** | `Esc` | Hebt Bildauswahl auf / Clear selection |
| **Ausgewählte Bilder löschen** | `Entf` / `Del` / `Backspace` | Entfernt markierte Bilder / Delete selected |
| **Canvas Verschieben (Pan)** | `Mittlere Maustaste` oder `Leertaste + Ziehen` | Verschiebt Ansicht / Pan canvas |
| **Canvas Zoomen** | `Mausrad` oder `+` / `-` / `0` | Zoomt die Ansicht / Zoom canvas |

---

## 🚀 Starten & Installation

### Voraussetzungen / Dependencies
- Python 3.10+
- GTK 4 & Libadwaita (`python-gobject`, `gtk4`, `libadwaita`)
- Pillow (`python-pillow`)
- Pycairo (`python-cairo`)

Unter Arch Linux / CachyOS / Manjaro:
```bash
sudo pacman -S python python-gobject gtk4 libadwaita python-pillow python-cairo
```

### Starten / Running
```bash
# Repository klonen (falls nicht lokal vorhanden)
git clone https://github.com/Papatin13/Wallpaper_Positioner.git
cd Wallpaper_Positioner

# Starten über das Skript:
./run.sh
```

Oder direkt als Python-Modul:
```bash
python3 -m wallpaper_positioner.main
```

---

## 📄 Lizenz
MIT License.
