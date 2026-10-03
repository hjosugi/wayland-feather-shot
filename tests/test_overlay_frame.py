"""The overlay's background frame: picked in the "…" menu with a preview,
shown in the size label, and applied to what copy, save and pin hand out.

Needs a GTK display; skips otherwise.
Run:  python3 tests/test_overlay_frame.py
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import gi  # noqa: E402
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402
    HAVE_GTK_DISPLAY = Gdk.Display.get_default() is not None
except (ImportError, ValueError):
    HAVE_GTK_DISPLAY = False
if HAVE_GTK_DISPLAY:
    from wayland_feather_shot.editor import background as bg  # noqa: E402
    from wayland_feather_shot.overlay.window import OverlayWindow  # noqa: E402
    from wayland_feather_shot.settings import Settings  # noqa: E402


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.FrameTest")
        cls.app.register(None)

    def setUp(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8,
                                      400, 300)
        pixbuf.fill(0xffffffff)
        self.window = OverlayWindow(self.app, pixbuf, Settings())
        self.addCleanup(self.window.destroy)
        self.window.area.allocate(400, 300, -1, None)
        self.window._mon_rects = [(0, 0, 400, 300)]
        self.window.sel = (100, 50, 200, 100)
        self.window._selection_made()

    def pick_gradient(self):
        self.window._frame_widgets["fill"].set_selected(
            bg.FILLS.index("gradient"))

    def test_without_a_frame_the_result_is_the_selection(self):
        self.assertFalse(self.window.background.enabled)
        self.assertIsNone(self.window._framed_size())
        result = self.window._export_result()
        self.assertEqual((result.get_width(), result.get_height()), (200, 100))

    def test_the_frame_page_slides_in_and_shows_a_preview(self):
        pages = self.window._more_pages
        self.assertEqual(pages.get_visible_child_name(), "menu")
        menu = pages.get_child_by_name("menu")
        child = menu.get_first_child()
        frame_item = None
        while child is not None:
            if (isinstance(child, Gtk.Button)
                    and child.get_child().get_first_child().get_icon_name()
                    == "wfs-frame-symbolic"):
                frame_item = child
            child = child.get_next_sibling()
        frame_item.emit("clicked")
        self.assertEqual(pages.get_visible_child_name(), "frame")
        self.assertIsNotNone(self.window._frame_picture.get_paintable())

    def test_a_frame_goes_into_copy_save_and_pin(self):
        self.pick_gradient()
        self.assertTrue(self.window.background.enabled)
        w, h = self.window._framed_size()
        self.assertGreater(w, 200)
        self.assertGreater(h, 100)
        with patch("wayland_feather_shot.save.copy_pixbuf",
                   return_value="wl-copy") as copy:
            self.window.copy_and_close()
        copied = copy.call_args[0][0]
        self.assertEqual((copied.get_width(), copied.get_height()), (w, h))
        # The corner is the gradient, not the white screenshot.
        pixels = copied.get_pixels()
        self.assertNotEqual(tuple(pixels[:3]), (255, 255, 255))

    def test_reading_the_selection_ignores_the_frame(self):
        self.pick_gradient()
        crop = self.window._export_cropped()
        self.assertEqual((crop.get_width(), crop.get_height()), (200, 100))

    def test_the_preview_follows_the_controls(self):
        self.pick_gradient()
        first = self.window._frame_picture.get_paintable()
        self.window._frame_widgets["padding"].set_value(0.3)
        second = self.window._frame_picture.get_paintable()
        self.assertGreater(second.get_width() / second.get_height(), 0)
        self.assertNotEqual(
            (first.get_width(), first.get_height()),
            (second.get_width(), second.get_height()))

    def test_none_takes_the_frame_away_again(self):
        self.pick_gradient()
        self.window._frame_widgets["fill"].set_selected(bg.FILLS.index("none"))
        self.assertFalse(self.window.background.enabled)
        self.assertIsNone(self.window._framed_size())


if __name__ == "__main__":
    unittest.main()
