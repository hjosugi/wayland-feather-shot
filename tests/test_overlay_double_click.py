"""Selection overlay double-click behavior on a GTK display."""

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
except (ImportError, ValueError):
    HAVE_GTK_DISPLAY = False
else:
    HAVE_GTK_DISPLAY = Gdk.Display.get_default() is not None

if HAVE_GTK_DISPLAY:
    from wayland_feather_shot import save as save_mod  # noqa: E402
    from wayland_feather_shot.overlay.window import OverlayWindow  # noqa: E402
    from wayland_feather_shot.util.settings import Settings  # noqa: E402


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayDoubleClickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.DoubleClickTest")
        cls.app.register(None)

    def setUp(self):
        pixbuf = GdkPixbuf.Pixbuf.new(
            GdkPixbuf.Colorspace.RGB, True, 8, 400, 300)
        pixbuf.fill(0xffffffff)
        self.window = OverlayWindow(self.app, pixbuf, Settings())
        self.window.area.allocate(400, 300, -1, None)
        self.window.set_visible(True)
        self.window.sel = (50, 50, 200, 150)
        self.window._selection_made()
        controllers = self.window.area.observe_controllers()
        self.click = next(
            controllers.get_item(i)
            for i in range(controllers.get_n_items())
            if isinstance(controllers.get_item(i), Gtk.GestureClick)
        )
        self.drag = next(
            controllers.get_item(i)
            for i in range(controllers.get_n_items())
            if isinstance(controllers.get_item(i), Gtk.GestureDrag)
        )
        self.copied = []
        self.copy_patch = patch.object(save_mod, "copy_pixbuf", self._copy_pixbuf)
        self.copy_patch.start()
        # The wl-copy path, whatever desktop the tests run on.
        self.desktop_patch = patch.object(
            save_mod, "compositor_keeps_clipboard", return_value=False)
        self.desktop_patch.start()

    def tearDown(self):
        self.copy_patch.stop()
        self.desktop_patch.stop()
        self.window.destroy()

    def _copy_pixbuf(self, pixbuf):
        self.copied.append((pixbuf.get_width(), pixbuf.get_height()))
        return "wl-copy"

    def pointer_click(self, count, x, y):
        self.click.emit("pressed", count, x, y)
        self.click.emit("released", count, x, y)

    def test_double_click_inside_completed_selection_copies_its_image(self):
        self.pointer_click(1, 100, 100)
        self.assertEqual(self.copied, [])
        self.pointer_click(2, 100, 100)
        self.assertEqual(self.copied, [(200, 150)])
        self.assertFalse(self.window.get_visible())

    def test_drag_begin_without_motion_keeps_double_click_eligible(self):
        self.pointer_click(1, 100, 100)
        self.click.emit("pressed", 2, 100, 100)
        self.drag.emit("drag-begin", 100, 100)
        self.click.emit("released", 2, 100, 100)
        self.assertEqual(self.copied, [(200, 150)])

    def test_first_click_outside_selection_does_not_arm_copy(self):
        self.pointer_click(1, 49, 90)
        self.pointer_click(2, 51, 90)
        self.assertEqual(self.copied, [])

    def test_double_click_on_resize_handle_does_not_copy(self):
        self.pointer_click(1, 50, 50)
        self.pointer_click(2, 50, 50)
        self.assertEqual(self.copied, [])

    def test_double_click_with_annotation_tool_active_does_not_copy(self):
        self.window.select_tool("pen")
        self.pointer_click(1, 100, 100)
        self.pointer_click(2, 100, 100)
        self.assertEqual(self.copied, [])

    def test_starting_a_drag_on_the_second_press_cancels_copy(self):
        self.pointer_click(1, 100, 100)
        self.click.emit("pressed", 2, 100, 100)
        self.drag.emit("drag-begin", 100, 100)
        self.drag.emit("drag-update", 30, 0)
        self.click.emit("released", 2, 130, 100)
        self.assertEqual(self.copied, [])


if __name__ == "__main__":
    unittest.main()
