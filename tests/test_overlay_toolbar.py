"""Checks for the controls shown below an in-place screenshot selection."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import cairo  # noqa: F401 - the overlay needs pycairo
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("Gsk", "4.0")
    gi.require_version("Graphene", "1.0")
    from gi.repository import Gdk, GdkPixbuf, Gsk, Graphene, Gtk
except (ImportError, ValueError):
    HAS_DISPLAY = False
else:
    HAS_DISPLAY = Gdk.Display.get_default() is not None

if HAS_DISPLAY:
    import wayland_feather_shot
    from wayland_feather_shot.app import FeatherShotApp
    from wayland_feather_shot.editor.shapes import TEXT_STYLE_BUTTONS
    from wayland_feather_shot.i18n import _
    from wayland_feather_shot.overlay.window import OVERLAY_TOOLS, OverlayWindow
    from wayland_feather_shot.settings import Settings


@unittest.skipUnless(HAS_DISPLAY, "GTK display unavailable")
class OverlayIconStartupTests(unittest.TestCase):
    def test_icons_are_available_after_app_startup_without_an_overlay(self):
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        icon_path = str(Path(wayland_feather_shot.__file__).resolve().parent / "icons")
        original_paths = theme.get_search_path()
        theme.set_search_path([path for path in original_paths if path != icon_path])
        try:
            app = FeatherShotApp(mode="gui", delay=0)
            app.set_application_id("io.github.hjosugi.WaylandFeatherShot.IconStartupTest")
            app.register(None)
            self.assertIn(icon_path, theme.get_search_path())
            self.assertTrue(theme.has_icon("wfs-tool-pen-symbolic"))
        finally:
            theme.set_search_path(original_paths)


@unittest.skipUnless(HAS_DISPLAY, "GTK display unavailable")
class OverlayToolbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = FeatherShotApp(mode="gui", delay=0)
        cls.app.set_application_id("io.github.hjosugi.WaylandFeatherShot.ToolbarTest")
        cls.app.register(None)

    def setUp(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 100, 100)
        pixbuf.fill(0xffffffff)
        self.window = OverlayWindow(self.app, pixbuf, Settings())

    def tearDown(self):
        self.window.destroy()

    def test_annotation_buttons_use_available_icons_and_full_tooltips(self):
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        for tool_id, _icon, tooltip in OVERLAY_TOOLS:
            with self.subTest(tool=tool_id):
                button = self.window._tool_buttons[tool_id]
                icon_name = button.get_icon_name()
                self.assertIsNotNone(icon_name)
                self.assertTrue(theme.has_icon(icon_name), icon_name)
                self.assertEqual(button.get_tooltip_text(), _(tooltip))
        for name, icon, _tip in TEXT_STYLE_BUTTONS:
            with self.subTest(text_style=name):
                self.assertTrue(theme.has_icon(icon), icon)

    def test_icon_buttons_keep_exclusive_tool_selection(self):
        buttons = self.window._tool_buttons
        self.assertTrue(buttons["move"].get_active())
        buttons["pen"].set_active(True)
        self.assertTrue(buttons["pen"].get_active())
        self.assertFalse(buttons["move"].get_active())

    def test_shape_icons_have_transparent_centers(self):
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        renderer = Gsk.CairoRenderer()
        renderer.realize_for_display(Gdk.Display.get_default())
        try:
            for tool_id in ("rect", "ellipse"):
                with self.subTest(tool=tool_id):
                    name = self.window._tool_buttons[tool_id].get_icon_name()
                    icon = theme.lookup_icon(
                        name, [], 20, 1, Gtk.TextDirection.NONE,
                        Gtk.IconLookupFlags.FORCE_SYMBOLIC,
                    )
                    snapshot = Gtk.Snapshot.new()
                    icon.snapshot(snapshot, 20, 20)
                    viewport = Graphene.Rect().init(0, 0, 20, 20)
                    texture = renderer.render_texture(snapshot.to_node(), viewport)
                    with tempfile.TemporaryDirectory() as directory:
                        filename = os.path.join(directory, "icon.png")
                        texture.save_to_png(filename)
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)
                        center_alpha = pixbuf.get_pixels()[
                            10 * pixbuf.get_rowstride() + 10 * 4 + 3
                        ]
                    self.assertEqual(center_alpha, 0)
        finally:
            renderer.unrealize()


if __name__ == "__main__":
    unittest.main()
