"""Automated test suite for Wallpaper Positioner."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
import numpy as np

from wallpaper_positioner.models import Layer, HandleType
from wallpaper_positioner.monitor_manager import MonitorManager, MonitorInfo
from wallpaper_positioner.color_engine import ColorEngine, rgb_to_hex, hex_to_rgb
from wallpaper_positioner.wallpaper_setter import WallpaperSetter


def test_monitor_manager():
    mm = MonitorManager()
    assert len(mm.monitors) >= 1, "Should find at least 1 monitor"
    print(f"✓ Monitor Manager found {len(mm.monitors)} monitors:")
    for m in mm.monitors:
        print(f"   - {m.display_label}")
        if m.is_spanned:
            assert len(m.sub_monitors) >= 2, "Spanned monitor should contain sub_monitors"
            for s in m.sub_monitors:
                print(f"       -> Screen {s.name}: ({s.rel_x}, {s.rel_y}) {s.width}x{s.height}")


def test_color_engine():
    # Create test image with distinct red and green sections
    arr = np.zeros((100, 100, 3), dtype=np.uint8)
    arr[:50, :] = [230, 40, 50]   # Red
    arr[50:, :] = [40, 180, 70]   # Green
    img = Image.fromarray(arr)

    palette = ColorEngine.extract_dominant_colors([img], max_colors=4)
    assert len(palette) >= 2, f"Should extract at least 2 colors, got {len(palette)}"
    print(f"✓ Color Engine extracted palette: {[rgb_to_hex(*c) for c in palette]}")

    best_bg = ColorEngine.get_best_background_color(palette)
    assert isinstance(best_bg, tuple) and len(best_bg) == 3
    print(f"✓ Best background color computed: {rgb_to_hex(*best_bg)}")


def test_layer_and_rendering():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a sample test image
        sample_path = os.path.join(tmpdir, "sample.png")
        sample_img = Image.new("RGBA", (200, 100), (255, 120, 0, 255))
        sample_img.save(sample_path)

        # Create Layer
        layer = Layer(file_path=sample_path, x=500, y=500, width=400, height=200)
        assert layer.orig_width == 200
        assert layer.orig_height == 100
        assert abs(layer.aspect_ratio - 2.0) < 0.01

        # Test point collision
        assert layer.contains_point(500, 500), "Center should be contained"
        assert layer.contains_point(400, 500), "Inside bounds should be contained"
        assert not layer.contains_point(100, 100), "Outside bounds should not be contained"

        # Test handles
        handles = layer.get_handles()
        assert len(handles) == 9, f"Should have 9 handles, got {len(handles)}"
        rot_handle = [h for h in handles if h.handle_type == HandleType.ROTATE][0]
        assert rot_handle.contains_point(rot_handle.x, rot_handle.y)

        # Test high-res rendering
        out_path = os.path.join(tmpdir, "rendered_wallpaper.png")
        success = WallpaperSetter.export_to_file(
            out_path,
            1920,
            1080,
            (25, 25, 35),
            [layer]
        )
        assert success, "Rendering export should succeed"
        assert os.path.exists(out_path), "Exported file should exist on disk"

        rendered = Image.open(out_path)
        assert rendered.size == (1920, 1080), f"Size should match, got {rendered.size}"
        print(f"✓ Successfully rendered {rendered.size[0]}x{rendered.size[1]} wallpaper image")


def test_clipboard_manager():
    from wallpaper_positioner.clipboard_manager import ClipboardManager
    cb = ClipboardManager.get_clipboard()
    assert cb is not None, "Gdk.Clipboard should be accessible"
    assert ClipboardManager._is_image_path("test.PNG")
    assert ClipboardManager._is_image_path("/some/path/image.webp")
    assert not ClipboardManager._is_image_path("document.pdf")
    print("✓ ClipboardManager initialized and format validators verified")


def test_border_and_frame():
    with tempfile.TemporaryDirectory() as tmpdir:
        sample_path = os.path.join(tmpdir, "photo.png")
        Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(sample_path)

        layer = Layer(
            file_path=sample_path,
            x=500,
            y=500,
            width=200,
            height=200,
            border_width=10.0,
            border_color=(255, 255, 255),
            border_radius=12.0,
        )
        assert layer.border_width == 10.0
        assert layer.border_color == (255, 255, 255)
        assert layer.border_radius == 12.0

        # Point inside original or border bounds
        assert layer.contains_point(500, 500)
        assert layer.contains_point(500 + 100 + 5, 500), "Point on border should be inside"
        assert not layer.contains_point(500 + 100 + 20, 500), "Point outside border should not be inside"

        out_path = os.path.join(tmpdir, "framed_wallpaper.png")
        success = WallpaperSetter.export_to_file(
            out_path,
            1000,
            1000,
            (10, 10, 15),
            [layer],
        )
        assert success
        assert os.path.exists(out_path)
        print("✓ Layer border & frame rendering verified successfully")


def test_shadow():
    with tempfile.TemporaryDirectory() as tmpdir:
        sample_path = os.path.join(tmpdir, "photo_shadow.png")
        Image.new("RGBA", (150, 150), (100, 200, 255, 255)).save(sample_path)

        layer = Layer(
            file_path=sample_path,
            x=500,
            y=500,
            width=200,
            height=200,
            shadow_enabled=True,
            shadow_blur=25.0,
            shadow_offset_x=10.0,
            shadow_offset_y=20.0,
            shadow_opacity=0.7,
            shadow_color=(0, 0, 0),
        )

        assert layer.shadow_enabled
        assert layer.shadow_blur == 25.0
        assert layer.shadow_offset_x == 10.0
        assert layer.shadow_offset_y == 20.0
        assert layer.shadow_opacity == 0.7

        # Check Cairo shadow surface generation
        shadow_surf = layer.get_shadow_surface()
        assert shadow_surf is not None, "Shadow surface should be generated"
        assert shadow_surf.get_width() > 200, "Shadow surface should include padding"

        # Check export with shadow
        out_path = os.path.join(tmpdir, "shadow_wallpaper.png")
        success = WallpaperSetter.export_to_file(
            out_path,
            1000,
            1000,
            (20, 25, 35),
            [layer],
        )
        assert success
        assert os.path.exists(out_path)
        print("✓ Layer shadow generation & rendering verified successfully")


def test_global_style_inheritance():
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    Gtk.init()

    from wallpaper_positioner.canvas import WallpaperCanvas
    mon = MonitorInfo(
        name="test-mon",
        id=0,
        description="Test Display",
        width=1920,
        height=1080,
        refresh_rate=60.0,
        scale=1.0,
        x=0,
        y=0,
    )
    canvas = WallpaperCanvas(mon)

    with tempfile.TemporaryDirectory() as tmpdir:
        p1 = os.path.join(tmpdir, "img1.png")
        p2 = os.path.join(tmpdir, "img2.png")
        Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(p1)
        Image.new("RGBA", (100, 100), (0, 255, 0, 255)).save(p2)

        l1 = canvas.add_layer_from_path(p1)
        assert l1 is not None
        assert l1.border_width == 0.0
        assert not l1.shadow_enabled

        # User modifies border & shadow on l1
        l1.border_width = 8.0
        l1.border_color = (0, 210, 255)
        l1.border_radius = 14.0
        l1.shadow_enabled = True
        l1.shadow_blur = 35.0
        l1.shadow_offset_x = 4.0
        l1.shadow_offset_y = 18.0
        l1.shadow_opacity = 0.8
        l1.shadow_color = (12, 14, 16)

        # Update persistent defaults
        canvas.set_default_style_from_layer(l1)

        # Add next image l2 (e.g. from file picker, paste Ctrl+V, or drag-and-drop)
        l2 = canvas.add_layer_from_path(p2)
        assert l2 is not None
        assert l2.border_width == 8.0
        assert l2.border_color == (0, 210, 255)
        assert l2.border_radius == 14.0
        assert l2.shadow_enabled is True
        assert l2.shadow_blur == 35.0
        assert l2.shadow_offset_x == 4.0
        assert l2.shadow_offset_y == 18.0
        assert l2.shadow_opacity == 0.8
        assert l2.shadow_color == (12, 14, 16)

        # Test apply style to all layers
        l2.border_width = 16.0
        canvas.apply_style_to_all_layers(l2)
        assert l1.border_width == 16.0
        assert l2.border_width == 16.0
        print("✓ Global style inheritance and apply-to-all verified successfully")


def test_background_adapt_on_button_click():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, Gio
    Adw.init()

    from wallpaper_positioner.window import WallpaperWindow
    app = Adw.Application(application_id="org.test.WallpaperPositionerBg", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def on_activate(app):
        win = WallpaperWindow(application=app)
        win.new_project()
        initial_bg = win.canvas.bg_color

        with tempfile.TemporaryDirectory() as tmpdir:
            p = os.path.join(tmpdir, "red_img.png")
            Image.new("RGBA", (100, 100), (220, 20, 30, 255)).save(p)
            win.canvas.add_layer_from_path(p)

            # 1. Background color should NOT have changed automatically
            assert win.canvas.bg_color == initial_bg, f"Background changed automatically: {win.canvas.bg_color}"

            # 2. Trigger adapt button
            win._on_adapt_bg_to_images_clicked(win.btn_adapt_bg)

            # 3. Background color should now have adapted
            assert win.canvas.bg_color != initial_bg, "Background did not adapt after clicking button"
            print("✓ Background color only adapts on explicit button click, not automatically")

        app.quit()

    app.connect("activate", on_activate)
    app.run([])


def test_project_save_and_load():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, Gio
    Adw.init()

    from wallpaper_positioner.window import WallpaperWindow
    from wallpaper_positioner.project_manager import ProjectManager
    app = Adw.Application(application_id="org.test.WallpaperPositionerSaveLoad", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def on_activate(app):
        win = WallpaperWindow(application=app)
        win.new_project()
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = os.path.join(tmpdir, "pic.png")
            Image.new("RGBA", (150, 100), (30, 140, 255, 255)).save(img_path)

            l1 = win.canvas.add_layer_from_path(img_path)
            l1.x = 420.0
            l1.y = 530.0
            l1.width = 600.0
            l1.height = 400.0
            l1.rotation = 25.0
            l1.border_width = 12.0
            l1.border_color = (255, 200, 50)
            l1.border_radius = 24.0
            l1.shadow_enabled = True
            l1.shadow_blur = 40.0
            l1.shadow_offset_x = 10.0
            l1.shadow_offset_y = 25.0
            l1.shadow_opacity = 0.8
            l1.shadow_color = (20, 20, 20)

            win.canvas.set_background_color((45, 20, 60))

            # Save project
            proj_path = os.path.join(tmpdir, "my_wallpaper.wpp")
            data = win._get_current_project_data()
            assert ProjectManager.save_to_file(proj_path, data)
            assert os.path.exists(proj_path)

            # Clear canvas (new project)
            win.new_project()
            assert len(win.canvas.layers) == 0
            assert win.canvas.bg_color == (26, 27, 38)

            # Load project back
            win.open_project_file(proj_path)
            assert len(win.canvas.layers) == 1
            assert win.canvas.bg_color == (45, 20, 60)

            rl = win.canvas.layers[0]
            assert rl.x == 420.0
            assert rl.y == 530.0
            assert rl.width == 600.0
            assert rl.height == 400.0
            assert rl.rotation == 25.0
            assert rl.border_width == 12.0
            assert rl.border_color == (255, 200, 50)
            assert rl.border_radius == 24.0
            assert rl.shadow_enabled is True
            assert rl.shadow_blur == 40.0
            assert rl.shadow_offset_x == 10.0
            assert rl.shadow_offset_y == 25.0
            assert rl.shadow_opacity == 0.8
            assert rl.shadow_color == (20, 20, 20)

            print("✓ Full project save & load roundtrip verified successfully")

        app.quit()

    app.connect("activate", on_activate)
    app.run([])


def test_auto_layout_and_spacing():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, Gio
    Adw.init()

    from wallpaper_positioner.window import WallpaperWindow
    app = Adw.Application(application_id="org.test.WallpaperPositionerLayout", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def on_activate(app):
        win = WallpaperWindow(application=app)
        win.new_project()

        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = os.path.join(tmpdir, "img1.png")
            p2 = os.path.join(tmpdir, "img2.png")
            p3 = os.path.join(tmpdir, "img3.png")
            p4 = os.path.join(tmpdir, "img4.png")
            Image.new("RGBA", (200, 200), (255, 0, 0, 255)).save(p1)
            Image.new("RGBA", (200, 200), (0, 255, 0, 255)).save(p2)
            Image.new("RGBA", (200, 200), (0, 0, 255, 255)).save(p3)
            Image.new("RGBA", (200, 200), (255, 255, 0, 255)).save(p4)

            l1 = win.canvas.add_layer_from_path(p1)
            l2 = win.canvas.add_layer_from_path(p2)

            # Test 1: Horizontal Row with margin=40 and gap=20
            win.scale_layout_margin.set_value(40.0)
            win.scale_layout_gap.set_value(20.0)
            win.switch_layout_cover.set_active(False)
            win._on_layout_cover_toggled(win.switch_layout_cover, False)
            win._set_layout_mode("row")

            assert win.current_layout_mode == "row"
            assert win.layout_margin == 40.0
            assert win.layout_gap == 20.0

            # Verify outer margins: left edge of l1 (including border) should be exactly 40px
            l1_left = l1.x - (l1.width / 2.0) - l1.border_width
            assert abs(l1_left - 40.0) < 1.0, f"l1_left={l1_left} should be 40"

            # Check gap between l1 right edge and l2 left edge
            l1_right = l1.x + (l1.width / 2.0) + l1.border_width
            l2_left = l2.x - (l2.width / 2.0) - l2.border_width
            gap_measured = l2_left - l1_right
            assert abs(gap_measured - 20.0) < 1.0, f"Gap between images should be 20px, got {gap_measured}"

            # Test 2: Live Slider Change (Margin=100, Gap=50)
            win.scale_layout_margin.set_value(100.0)
            win.scale_layout_gap.set_value(50.0)

            l1_left_new = l1.x - (l1.width / 2.0) - l1.border_width
            assert abs(l1_left_new - 100.0) < 1.0, f"l1_left_new={l1_left_new} should be 100"

            l1_right_new = l1.x + (l1.width / 2.0) + l1.border_width
            l2_left_new = l2.x - (l2.width / 2.0) - l2.border_width
            gap_new = l2_left_new - l1_right_new
            assert abs(gap_new - 50.0) < 1.0, f"New gap should be 50px, got {gap_new}"

            # Test 3: Grid Mode with 4 images (cover=False for proportional fit within grid bounds)
            win.canvas.add_layer_from_path(p3)
            win.canvas.add_layer_from_path(p4)
            assert len(win.canvas.layers) == 4

            win.switch_layout_cover.set_active(False)
            win._on_layout_cover_toggled(win.switch_layout_cover, False)
            win.scale_layout_margin.set_value(30.0)
            win.scale_layout_gap.set_value(15.0)
            win._set_layout_mode("grid")

            for layer in win.canvas.layers:
                # All layers must be upright and fit inside monitor bounds
                assert layer.rotation == 0.0
                assert (layer.x - layer.width / 2.0) >= 30.0 - 1e-3
                assert (layer.x + layer.width / 2.0) <= win.current_monitor.width - 30.0 + 1e-3
                assert (layer.y - layer.height / 2.0) >= 30.0 - 1e-3
                assert (layer.y + layer.height / 2.0) <= win.current_monitor.height - 30.0 + 1e-3

            # Test 4: Multi-Monitor Spanned mode="per_monitor"
            spanned_mon = [m for m in win.monitor_manager.monitors if m.is_spanned]
            if spanned_mon:
                smon = spanned_mon[0]
                win.current_monitor = smon
                win.canvas.set_monitor(smon)
                win._set_layout_mode("per_monitor")
                # 4 images distributed across sub_monitors
                sub0 = smon.sub_monitors[0]
                sub1 = smon.sub_monitors[1]
                # First two images should be in sub0
                for l in win.canvas.layers[:2]:
                    assert l.monitor_name == sub0.name
                    assert 0.0 <= l.x <= sub0.width
                    cx, _ = win.canvas.get_layer_canvas_pos(l)
                    assert sub0.rel_x <= cx <= (sub0.rel_x + sub0.width)
                # Next two images should be in sub1
                for l in win.canvas.layers[2:]:
                    assert l.monitor_name == sub1.name
                    assert 0.0 <= l.x <= sub1.width
                    cx, _ = win.canvas.get_layer_canvas_pos(l)
                    assert sub1.rel_x <= cx <= (sub1.rel_x + sub1.width)

            print("✓ Auto-Layout and Spacing Sliders verified with real-time live updates")

        app.quit()

    app.connect("activate", on_activate)
    app.run([])


def test_multi_selection():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, Gio
    Adw.init()

    from wallpaper_positioner.window import WallpaperWindow
    app = Adw.Application(application_id="org.test.WallpaperPositionerMultiSelect", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def on_activate(app):
        win = WallpaperWindow(application=app)
        win.new_project()
        single_mon = [m for m in win.monitor_manager.monitors if not m.is_spanned][0]
        win.current_monitor = single_mon
        win.canvas.set_monitor(single_mon)

        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = os.path.join(tmpdir, "img1.png")
            p2 = os.path.join(tmpdir, "img2.png")
            p3 = os.path.join(tmpdir, "img3.png")
            Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(p1)
            Image.new("RGBA", (100, 100), (0, 255, 0, 255)).save(p2)
            Image.new("RGBA", (100, 100), (0, 0, 255, 255)).save(p3)

            l1 = win.canvas.add_layer_from_path(p1, at_cx=100.0, at_cy=100.0)
            l2 = win.canvas.add_layer_from_path(p2, at_cx=300.0, at_cy=100.0)
            l3 = win.canvas.add_layer_from_path(p3, at_cx=600.0, at_cy=100.0)
            l1.width, l1.height = 100.0, 100.0
            l2.width, l2.height = 100.0, 100.0
            l3.width, l3.height = 100.0, 100.0

            # 1. Test Layer.intersects_rect
            assert l1.intersects_rect(0, 0, 120, 120), "l1 should intersect rect [0,0,120,120]"
            assert not l1.intersects_rect(200, 200, 100, 100), "l1 should not intersect disjoint rect"

            # 2. Test multi-selection API on canvas
            win.canvas.clear_selection()
            assert len(win.canvas.selected_layers) == 0

            # Select l1
            win.canvas.select_layer(l1)
            assert win.canvas.selected_layers == [l1]
            assert win.canvas.selected_layer == l1

            # Add l2 via toggle_layer_selection
            win.canvas.toggle_layer_selection(l2)
            assert win.canvas.selected_layers == [l1, l2]

            # Toggle l1 off -> only l2 remains
            win.canvas.toggle_layer_selection(l1)
            assert win.canvas.selected_layers == [l2]

            # Select all layers (Ctrl+A)
            win.canvas.select_all_layers()
            assert len(win.canvas.selected_layers) == 3
            assert set(win.canvas.selected_layers) == {l1, l2, l3}

            # 3. Test multi-layer movement
            pos1_before = (l1.x, l1.y)
            pos2_before = (l2.x, l2.y)
            pos3_before = (l3.x, l3.y)
            for l in win.canvas.selected_layers:
                l.x += 25.0
                l.y += 15.0
            assert l1.x == pos1_before[0] + 25.0
            assert l2.x == pos2_before[0] + 25.0
            assert l3.x == pos3_before[0] + 25.0

            # 4. Test batch styling across all selected layers
            win.spin_border_width.set_value(8.0)
            win._on_border_prop_changed(win.spin_border_width)
            assert l1.border_width == 8.0
            assert l2.border_width == 8.0
            assert l3.border_width == 8.0

            # Apply shadow preset to group
            win._apply_shadow_preset(blur=30.0, ox=5.0, oy=15.0, opac=60.0)
            for l in win.canvas.selected_layers:
                assert l.shadow_enabled is True
                assert l.shadow_blur == 30.0
                assert l.shadow_opacity == 0.6

            # 5. Test batch alignment
            win._on_align_center_clicked(None)
            for l in win.canvas.selected_layers:
                assert l.x == win.current_monitor.width / 2.0
                assert l.y == win.current_monitor.height / 2.0

            # 6. Test layer reordering of group
            win.canvas.select_layers([l1, l2])
            win.canvas.move_selected_layers_to_front()
            assert win.canvas.layers[-2:] == [l1, l2]

            # 7. Test batch deletion
            win.canvas.remove_selected_layers()
            assert len(win.canvas.layers) == 1
            assert win.canvas.layers[0] == l3
            # After removing selected layers, the remaining layer is automatically focused
            assert win.canvas.selected_layers == [l3]
            win.canvas.clear_selection()
            assert len(win.canvas.selected_layers) == 0

            print("✓ Multi-selection, rubberband intersection, batch styling, and group manipulation verified successfully")

        app.quit()

    app.connect("activate", on_activate)
    app.run([])


def test_separate_multi_monitor_and_layer_preservation():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, Gio
    Adw.init()

    from wallpaper_positioner.window import WallpaperWindow
    app = Adw.Application(application_id="org.test.WallpaperPositionerPreserve", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def on_activate(app):
        win = WallpaperWindow(application=app)
        win.new_project()

        spanned_mons = [m for m in win.monitor_manager.monitors if m.is_spanned]
        if not spanned_mons:
            print("No spanned monitor found on system, skipping multi-monitor preservation test")
            app.quit()
            return

        smon = spanned_mons[0]
        assert len(smon.sub_monitors) >= 2
        sub0 = smon.sub_monitors[0]
        sub1 = smon.sub_monitors[1]

        # Check visual separation gap between sub-monitors
        assert sub1.rel_x > sub0.rel_x + sub0.width, "Sub monitors must have a visual gap"

        # Switch to spanned view
        win.current_monitor = smon
        win.canvas.set_monitor(smon)

        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = os.path.join(tmpdir, "img1.png")
            p2 = os.path.join(tmpdir, "img2.png")
            Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(p1)
            Image.new("RGBA", (100, 100), (0, 0, 255, 255)).save(p2)

            # Add layer 1 on sub0, layer 2 on sub1
            l1 = win.canvas.add_layer_from_path(p1, at_cx=sub0.rel_x + 500, at_cy=sub0.rel_y + 400)
            l2 = win.canvas.add_layer_from_path(p2, at_cx=sub1.rel_x + 600, at_cy=sub1.rel_y + 300)

            assert l1.monitor_name == sub0.name
            assert abs(l1.x - 500) < 1e-3
            assert abs(l1.y - 400) < 1e-3

            assert l2.monitor_name == sub1.name
            assert abs(l2.x - 600) < 1e-3
            assert abs(l2.y - 300) < 1e-3

            # Verify canvas coordinates in spanned view
            cx1, cy1 = win.canvas.get_layer_canvas_pos(l1)
            cx2, cy2 = win.canvas.get_layer_canvas_pos(l2)
            assert cx1 == sub0.rel_x + 500
            assert cx2 == sub1.rel_x + 600

            # 1. Switch to sub0 single-monitor view
            win.canvas.set_monitor(sub0)
            win.current_monitor = sub0
            assert l1 in win.canvas.layers
            assert l2 not in win.canvas.layers
            # Position of l1 must be preserved identically!
            assert abs(l1.x - 500) < 1e-3
            assert abs(l1.y - 400) < 1e-3

            # Move l1 by +50 in single monitor view
            l1.x += 50.0

            # 2. Switch to sub1 single-monitor view
            win.canvas.set_monitor(sub1)
            win.current_monitor = sub1
            assert l2 in win.canvas.layers
            assert l1 not in win.canvas.layers
            # Position of l2 must be preserved identically!
            assert abs(l2.x - 600) < 1e-3
            assert abs(l2.y - 300) < 1e-3

            # 3. Switch back to Spanned mode
            win.canvas.set_monitor(smon)
            win.current_monitor = smon
            assert l1 in win.canvas.layers
            assert l2 in win.canvas.layers
            assert abs(l1.x - 550) < 1e-3
            assert abs(l2.x - 600) < 1e-3
            cx1_back, cy1_back = win.canvas.get_layer_canvas_pos(l1)
            assert cx1_back == sub0.rel_x + 550

            print("✓ Separate multi-monitor layout, visual separation gap, and layer coordinate preservation verified")

        app.quit()

    app.connect("activate", on_activate)
    app.run([])



def test_wallpaper_setter_live_application():
    from pathlib import Path
    import time
    from wallpaper_positioner.wallpaper_setter import WallpaperSetter
    from wallpaper_positioner.monitor_manager import MonitorInfo

    with tempfile.TemporaryDirectory() as tmpdir:
        # Override CACHE_DIR to temp directory for testing
        orig_cache = WallpaperSetter.CACHE_DIR
        WallpaperSetter.CACHE_DIR = Path(tmpdir)
        try:
            sample_path = os.path.join(tmpdir, "pic.png")
            Image.new("RGBA", (100, 100), (10, 20, 30, 255)).save(sample_path)

            l1 = Layer(file_path=sample_path, x=200, y=200, width=100, height=100, monitor_name="TEST-MON-1")
            l2 = Layer(file_path=sample_path, x=300, y=300, width=100, height=100, monitor_name="TEST-MON-2")

            sub1 = MonitorInfo(id="m1", name="TEST-MON-1", description="Mon 1", width=800, height=600, refresh_rate=60.0, scale=1.0, x=0, y=0)
            sub2 = MonitorInfo(id="m2", name="TEST-MON-2", description="Mon 2", width=800, height=600, refresh_rate=60.0, scale=1.0, x=800, y=0)
            spanned = MonitorInfo(id="spanned", name="Beide Bildschirme", description="All", width=1600, height=600, refresh_rate=60.0, scale=1.0, x=0, y=0, is_spanned=True, sub_monitors=[sub1, sub2])

            # 1. Single monitor test
            ok, msg = WallpaperSetter.apply_wallpaper(sub1, (20, 30, 40), [l1])
            files1 = list(Path(tmpdir).glob("wallpaper_TEST-MON-1_*.png"))
            assert len(files1) == 1, f"Should create exactly 1 timestamped file, got {files1}"
            first_file = files1[0]
            assert os.path.exists(first_file)

            # Sleep briefly to ensure distinct millisecond timestamp
            time.sleep(0.01)

            # Call again: verify new file created and old file cleaned up
            ok2, msg2 = WallpaperSetter.apply_wallpaper(sub1, (20, 30, 40), [l1])
            files2 = list(Path(tmpdir).glob("wallpaper_TEST-MON-1_*.png"))
            assert len(files2) == 1, f"Old cache should be cleaned up, got {files2}"
            assert files2[0] != first_file, "New timestamped cache file should be distinct from old"

            # 2. Spanned multi-monitor test
            ok_spanned, msg_spanned = WallpaperSetter.apply_wallpaper(spanned, (20, 30, 40), [l1, l2])
            sub1_files = list(Path(tmpdir).glob("wallpaper_TEST-MON-1_*.png"))
            sub2_files = list(Path(tmpdir).glob("wallpaper_TEST-MON-2_*.png"))
            assert len(sub1_files) == 1, "Sub1 should have 1 cached file"
            assert len(sub2_files) == 1, "Sub2 should have 1 cached file"

            print("✓ WallpaperSetter timestamped cache-busting, cleanup, and multi-monitor slice generation verified")
        finally:
            WallpaperSetter.CACHE_DIR = orig_cache



def test_dynamic_layout_proportional_sizing():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, Gio
    Adw.init()

    from wallpaper_positioner.window import WallpaperWindow
    app = Adw.Application(application_id="org.test.WallpaperPositionerDynamic", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def on_activate(app):
        win = WallpaperWindow(application=app)
        win.new_project()

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1 Large Hero image + 2 Small images
            p_big = os.path.join(tmpdir, "hero_large.png")
            p_sm1 = os.path.join(tmpdir, "small_1.png")
            p_sm2 = os.path.join(tmpdir, "small_2.png")
            Image.new("RGBA", (2560, 1440), (255, 50, 50, 255)).save(p_big)
            Image.new("RGBA", (500, 500), (50, 255, 50, 255)).save(p_sm1)
            Image.new("RGBA", (500, 500), (50, 50, 255, 255)).save(p_sm2)

            l_big = win.canvas.add_layer_from_path(p_big)
            l_sm1 = win.canvas.add_layer_from_path(p_sm1)
            l_sm2 = win.canvas.add_layer_from_path(p_sm2)

            win.scale_layout_margin.set_value(40.0)
            win.scale_layout_gap.set_value(20.0)
            win.switch_layout_cover.set_active(False)
            win._on_layout_cover_toggled(win.switch_layout_cover, False)

            # 1. Test "dynamic" mode
            win._set_layout_mode("dynamic")
            assert win.current_layout_mode == "dynamic"

            area_big = l_big.width * l_big.height
            area_sm1 = l_sm1.width * l_sm1.height
            area_sm2 = l_sm2.width * l_sm2.height

            # The large image MUST get substantially more space than each small image!
            assert area_big >= 1.8 * area_sm1, f"Big area ({area_big}) should be >= 1.8x small1 ({area_sm1})"
            assert area_big >= 1.8 * area_sm2, f"Big area ({area_big}) should be >= 1.8x small2 ({area_sm2})"

            # Verify no layers exceed the canvas margin
            m = win.layout_margin
            w_bound = win.current_monitor.width
            h_bound = win.current_monitor.height
            for l in [l_big, l_sm1, l_sm2]:
                assert (l.x - l.width / 2.0) >= m - 1e-2
                assert (l.x + l.width / 2.0) <= w_bound - m + 1e-2
                assert (l.y - l.height / 2.0) >= m - 1e-2
                assert (l.y + l.height / 2.0) <= h_bound - m + 1e-2

            # 2. Test "row" mode with proportional widths
            win._set_layout_mode("row")
            assert l_big.width > 1.4 * l_sm1.width, f"Big width ({l_big.width}) should be > 1.4x small ({l_sm1.width}) in row"

            # 3. Test "col" mode with proportional heights
            win._set_layout_mode("col")
            assert l_big.height > 1.4 * l_sm1.height, f"Big height ({l_big.height}) should be > 1.4x small ({l_sm1.height}) in col"

            print("✓ Dynamic auto-layout: larger images proportionally receive more space than smaller images")

        app.quit()

    app.connect("activate", on_activate)
    app.run([])


def test_custom_canvas_resolution():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, Gio
    Adw.init()
    from wallpaper_positioner.window import WallpaperWindow

    app = Adw.Application(application_id="org.test.WallpaperPositionerCustomResolution", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def on_activate(app):
        win = WallpaperWindow(application=app)
        win.new_project()

        # 1. Verify custom monitor exists in monitor_manager
        custom_mons = [m for m in win.monitor_manager.monitors if m.is_custom]
        assert len(custom_mons) == 1, "Should have exactly 1 custom monitor entry"
        c_mon = custom_mons[0]
        assert c_mon.is_custom is True
        assert c_mon.name == "Benutzerdefiniert"

        # 2. Test selecting preset 4K (3840x2160)
        win._apply_custom_preset(3840, 2160)
        assert win.current_monitor.is_custom is True
        assert win.current_monitor.width == 3840
        assert win.current_monitor.height == 2160
        assert win.canvas.monitor.width == 3840
        assert win.canvas.monitor.height == 2160
        assert win.spin_custom_width.get_value() == 3840.0
        assert win.spin_custom_height.get_value() == 2160.0

        # 3. Test swap width/height (3840x2160 -> 2160x3840)
        win._on_swap_custom_res_clicked(None)
        assert win.current_monitor.width == 2160
        assert win.current_monitor.height == 3840
        assert win.canvas.monitor.width == 2160
        assert win.canvas.monitor.height == 3840

        # 4. Test live spin button changes
        win.spin_custom_width.set_value(2560)
        win.spin_custom_height.set_value(1440)
        assert win.current_monitor.width == 2560
        assert win.current_monitor.height == 1440
        assert win.canvas.monitor.width == 2560
        assert win.canvas.monitor.height == 1440

        # 5. Add layers and perform auto-layout on custom canvas
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = os.path.join(tmpdir, "img1.png")
            Image.new("RGB", (800, 600), (255, 0, 0)).save(p1)
            p2 = os.path.join(tmpdir, "img2.png")
            Image.new("RGB", (600, 800), (0, 255, 0)).save(p2)

            win.canvas.add_layer_from_path(p1)
            win.canvas.add_layer_from_path(p2)
            assert len(win.canvas.layers) == 2

            win.canvas.auto_layout_layers(mode="dynamic", margin=40.0, gap=20.0)
            for l in win.canvas.layers:
                assert (l.x + l.width / 2.0) <= 2560.0 + 1e-2
                assert (l.y + l.height / 2.0) <= 1440.0 + 1e-2

            # 6. Test project serialization and restoration with custom resolution
            proj_data = win._get_current_project_data()
            assert proj_data["monitor"]["is_custom"] is True
            assert proj_data["monitor"]["width"] == 2560
            assert proj_data["monitor"]["height"] == 1440

            # Switch back to physical monitor
            phys_mon = [m for m in win.monitor_manager.monitors if not m.is_spanned and not m.is_custom][0]
            phys_idx = win.monitor_manager.monitors.index(phys_mon)
            win.monitor_dropdown.set_selected(phys_idx)
            assert win.current_monitor.is_custom is False

            # Restore project data -> must re-activate custom resolution 2560x1440
            win._apply_project_data(proj_data)
            assert win.current_monitor.is_custom is True
            assert win.current_monitor.width == 2560
            assert win.current_monitor.height == 1440
            assert len(win.canvas.layers) == 2

            # 7. Test Export with custom resolution
            export_path = os.path.join(tmpdir, "custom_export.png")
            ok = WallpaperSetter.export_to_file(
                export_path,
                win.current_monitor.width,
                win.current_monitor.height,
                win.canvas.bg_color,
                win.canvas.layers,
            )
            assert ok is True
            with Image.open(export_path) as exported_img:
                assert exported_img.size == (2560, 1440)

        print("✓ Custom canvas resolution selection, presets, live resizing, auto-layout, export, and project persistence verified")
        app.quit()

    app.connect("activate", on_activate)
    app.run([])


if __name__ == "__main__":
    test_monitor_manager()
    test_color_engine()
    test_layer_and_rendering()
    test_clipboard_manager()
    test_border_and_frame()
    test_shadow()
    test_global_style_inheritance()
    test_background_adapt_on_button_click()
    test_project_save_and_load()
    test_auto_layout_and_spacing()
    test_multi_selection()
    test_separate_multi_monitor_and_layer_preservation()
    test_wallpaper_setter_live_application()
    test_dynamic_layout_proportional_sizing()
    test_custom_canvas_resolution()
    print("\n🎉 ALL TESTS PASSED!")
