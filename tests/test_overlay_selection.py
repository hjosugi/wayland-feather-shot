"""The region overlay has no modes: everything follows from the selection.

Needs a GTK display; skips otherwise.  Run:  python3 tests/test_overlay_selection.py
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
    from wayland_feather_shot.overlay.window import OverlayWindow  # noqa: E402
    from wayland_feather_shot.settings import Settings  # noqa: E402


class FakeDrag:
    """Only what the drag handlers ask a Gtk.GestureDrag for."""

    def __init__(self, x, y):
        self.start = (x, y)

    def get_start_point(self):
        return (True, *self.start)


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlaySelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.SelectionTest")
        cls.app.register(None)

    def setUp(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 400, 300)
        pixbuf.fill(0xffffffff)
        self.window = OverlayWindow(self.app, pixbuf, Settings())
        self.addCleanup(self.window.destroy)
        self.window.area.allocate(400, 300, -1, None)
        self.window.set_visible(True)
        # Edge snapping follows the real monitor layout; pin it to the image
        # so the coordinates below mean what they say on any machine.
        self.window._mon_rects = [(0, 0, 400, 300)]

    def drag(self, x0, y0, x1, y1):
        gesture = FakeDrag(x0, y0)
        self.window._on_drag_begin(gesture, x0, y0)
        self.window._on_drag_update(gesture, x1 - x0, y1 - y0)
        self.window._on_drag_end(gesture, x1 - x0, y1 - y0)

    def bars_visible(self):
        return self.window._toolbar.get_visible()

    def test_starts_without_a_selection_or_controls(self):
        self.assertIsNone(self.window.sel)
        self.assertFalse(self.bars_visible())

    def test_a_drag_selects_and_shows_the_controls(self):
        self.drag(50, 50, 250, 200)
        self.assertEqual(self.window.sel, (50, 50, 200, 150))
        self.assertTrue(self.bars_visible())
        self.assertEqual(self.window.tool, "move")

    def test_undo_takes_the_first_selection_away_and_redo_brings_it_back(self):
        self.drag(50, 50, 250, 200)
        self.window.undo()
        self.assertIsNone(self.window.sel)
        self.assertFalse(self.bars_visible())
        self.window.redo()
        self.assertEqual(self.window.sel, (50, 50, 200, 150))
        self.assertTrue(self.bars_visible())

    def test_a_fresh_selection_is_undoable_back_to_the_previous_one(self):
        self.drag(50, 50, 250, 200)
        self.drag(280, 200, 360, 270)          # outside, clear of the snap zone
        self.assertEqual(self.window.sel, (280, 200, 80, 70))
        self.window.undo()
        self.assertEqual(self.window.sel, (50, 50, 200, 150))

    def test_resizing_by_a_handle_works_with_a_drawing_tool_and_is_undoable(self):
        self.drag(50, 50, 250, 200)
        self.window.select_tool("pen")
        self.drag(250, 200, 300, 250)          # the "se" handle
        self.assertEqual(self.window.sel, (50, 50, 250, 200))
        self.assertEqual(self.window.shapes, [])
        self.window.undo()
        self.assertEqual(self.window.sel, (50, 50, 200, 150))

    def test_dragging_a_handle_past_the_opposite_edge_flips_the_rectangle(self):
        self.drag(50, 50, 250, 200)
        self.drag(150, 50, 150, 260)           # the "n" handle, down past the bottom
        self.assertEqual(self.window.sel, (50, 200, 200, 60))
        self.drag(250, 230, 20, 230)           # the "e" handle, left past the left edge
        self.assertEqual(self.window.sel, (20, 200, 30, 60))

    def test_a_drag_out_past_the_image_edge_keeps_the_far_edge(self):
        # Clamping moved the near edge in but kept the width, which pushed
        # the far edge out by as much as the drag overshot.
        self.drag(-50, -30, 150, 200)
        self.assertEqual(self.window.sel, (0, 0, 150, 200))
        # Pointer positions are fractional; the far edge must not lose the
        # fraction of the near one.
        self.assertEqual(self.window._clamp_rect(10.7, 20.5, 339.3, 179.5),
                         (10, 20, 340, 180))

    def test_the_mode_bar_is_there_only_while_nothing_is_selected(self):
        self.assertTrue(self.window._mode_bar.get_visible())
        self.drag(50, 50, 250, 200)
        self.assertFalse(self.window._mode_bar.get_visible())
        self.window.undo()
        self.assertIsNone(self.window.sel)
        self.assertTrue(self.window._mode_bar.get_visible())

    def test_the_mode_bar_gets_out_of_the_way(self):
        # Of the region being dragged out, and of the toast.
        self.assertGreater(self.window._toast.get_margin_bottom(), 48)
        gesture = FakeDrag(50, 50)
        self.window._on_drag_begin(gesture, 50, 50)
        self.assertFalse(self.window._mode_bar.get_visible())
        self.window._on_drag_update(gesture, 100, 100)
        self.window._on_drag_end(gesture, 100, 100)
        self.assertEqual(self.window._toast.get_margin_bottom(), 48)

    def test_the_mode_bar_leaves_the_keyboard_to_the_overlay(self):
        # A focused toggle button swallows Enter before the window sees it.
        for button in self.window._mode_buttons.values():
            self.assertFalse(button.get_focusable())

    def test_screen_mode_takes_the_monitor_under_the_press(self):
        self.window._mon_rects = [(0, 0, 200, 300), (200, 0, 200, 300)]
        self.window._mode_buttons["screen"].set_active(True)
        self.drag(300, 100, 320, 120)          # a click, or a small drag
        self.assertEqual(self.window.sel, (200, 0, 200, 300))
        self.assertTrue(self.window._bars_visible)
        self.window.undo()
        self.assertIsNone(self.window.sel)

    def test_screen_mode_with_one_monitor_takes_everything(self):
        self.window._mon_rects = []
        self.window._mode_buttons["screen"].set_active(True)
        self.drag(120, 80, 200, 150)
        self.assertEqual(self.window.sel, (0, 0, 400, 300))

    def test_enter_in_screen_mode_takes_the_screen_under_the_pointer(self):
        self.window._mon_rects = [(0, 0, 200, 300), (200, 0, 200, 300)]
        self.window._mode_buttons["screen"].set_active(True)
        self.window._on_motion(None, 50, 50)
        self.window._on_key(None, Gdk.KEY_Return, 0, 0)
        self.assertEqual(self.window.sel, (0, 0, 200, 300))

    def test_selection_mode_still_drags_out_a_region(self):
        self.window._mon_rects = [(0, 0, 200, 300), (200, 0, 200, 300)]
        self.window._mode_buttons["screen"].set_active(True)
        self.window._mode_buttons["selection"].set_active(True)
        self.drag(60, 60, 160, 140)
        self.assertEqual(self.window.sel, (60, 60, 100, 80))

    def test_handles_show_a_resize_cursor_with_every_tool(self):
        self.drag(50, 50, 250, 200)
        self.window.select_tool("pen")
        self.window._on_motion(None, 250, 200)
        self.assertEqual(self.window.area.get_cursor().get_name(), "nwse-resize")
        self.window._on_motion(None, 150, 125)
        self.assertEqual(self.window.area.get_cursor().get_name(), "crosshair")

    def test_a_tiny_drag_outside_keeps_the_previous_selection(self):
        self.drag(50, 50, 250, 200)
        self.drag(300, 220, 301, 221)
        self.assertEqual(self.window.sel, (50, 50, 200, 150))
        self.assertTrue(self.bars_visible())

    def test_a_click_with_nothing_selected_takes_the_whole_screen(self):
        self.drag(10, 10, 11, 11)
        self.assertEqual(self.window.sel, (0, 0, 400, 300))
        self.window.undo()
        self.assertIsNone(self.window.sel)

    def test_enter_selects_everything_first_and_copies_afterwards(self):
        with patch.object(self.window, "copy_and_close") as copy:
            self.window._on_key(None, Gdk.KEY_Return, 0, 0)
            self.assertEqual(self.window.sel, (0, 0, 400, 300))
            copy.assert_not_called()
            self.window._on_key(None, Gdk.KEY_Return, 0, 0)
            copy.assert_called_once()

    def test_tool_keys_need_a_selection(self):
        self.window._on_key(None, Gdk.KEY_p, 0, 0)
        self.assertEqual(self.window.tool, "move")
        self.drag(50, 50, 250, 200)
        self.window._on_key(None, Gdk.KEY_p, 0, 0)
        self.assertEqual(self.window.tool, "pen")


if __name__ == "__main__":
    unittest.main()
