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
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402
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

    def copied_after(self, act):
        """Run *act* in copy mode and count the copies it leads to."""
        copies = []
        self.window.copy_on_select = True
        self.window.copy_and_close = lambda: copies.append(self.window.sel)
        act()
        context = GLib.MainContext.default()
        while context.iteration(False):
            pass
        return copies

    def test_copy_mode_copies_the_selection_as_soon_as_it_is_made(self):
        self.assertEqual(self.copied_after(lambda: self.drag(50, 50, 250, 200)),
                         [(50, 50, 200, 150)])

    def test_copy_mode_click_and_enter_copy_the_whole_screen(self):
        self.assertEqual(self.copied_after(lambda: self.drag(80, 80, 81, 81)),
                         [(0, 0, 400, 300)])
        self.window.undo()
        self.assertEqual(self.copied_after(
            lambda: self.window._on_key(None, Gdk.KEY_Return, 0, 0)),
            [(0, 0, 400, 300)])

    def test_the_ordinary_overlay_does_not_copy_on_select(self):
        copies = []
        self.window.copy_and_close = lambda: copies.append(True)
        self.drag(50, 50, 250, 200)
        context = GLib.MainContext.default()
        while context.iteration(False):
            pass
        self.assertEqual(copies, [])

    def full_overlay(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 400, 300)
        pixbuf.fill(0xffffffff)
        window = OverlayWindow(self.app, pixbuf, Settings(), select_all=True)
        self.addCleanup(window.destroy)
        window.area.allocate(400, 300, -1, None)
        return window

    def test_full_screen_starts_with_everything_selected(self):
        window = self.full_overlay()
        self.assertEqual(window.sel, (0, 0, 400, 300))
        self.assertTrue(window._bars_visible)
        # Nothing to undo back to: the whole screen stays selected.
        window.undo()
        self.assertEqual(window.sel, (0, 0, 400, 300))

    def test_full_screen_can_still_be_cut_down_with_a_handle(self):
        window = self.full_overlay()
        gesture = FakeDrag(400, 300)              # the "se" handle
        window._on_drag_begin(gesture, 400, 300)
        window._on_drag_update(gesture, -100, -80)
        window._on_drag_end(gesture, -100, -80)
        self.assertEqual(window.sel, (0, 0, 300, 220))
        window.undo()
        self.assertEqual(window.sel, (0, 0, 400, 300))

    def test_clicking_the_bars_leaves_enter_to_the_overlay(self):
        # A focused button takes Enter for itself; with the toolbar showing
        # from the start (full mode) Enter did nothing.
        window = self.full_overlay()
        buttons, stack = [], [window._toolbar, window._action_bar]
        while stack:
            widget = stack.pop()
            if isinstance(widget, Gtk.Button):
                buttons.append(widget)
            child = widget.get_first_child()
            while child is not None:
                stack.append(child)
                child = child.get_next_sibling()
        self.assertGreater(len(buttons), 10)
        self.assertFalse(any(b.get_focus_on_click() for b in buttons))

    def test_the_bars_follow_the_window_size(self):
        # A selection made before the window has its size (full mode) gets
        # its bars placed once the canvas is allocated.
        window = self.full_overlay()
        context = GLib.MainContext.default()
        while context.iteration(False):
            pass
        toolbar_y = window._toolbar.get_margin_top()
        self.assertGreater(toolbar_y, 0)
        self.assertLess(toolbar_y, 300)

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
