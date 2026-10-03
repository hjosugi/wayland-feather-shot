"""The hand tool grabs a placed shape and moves it; the move is undoable.

Needs a GTK display; skips otherwise.  Run:  python3 tests/test_overlay_hand.py
"""

import os
import sys
import unittest

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
    from wayland_feather_shot.editor.shapes import Text  # noqa: E402
    from wayland_feather_shot.overlay.window import OverlayWindow  # noqa: E402
    from wayland_feather_shot.settings import Settings  # noqa: E402


CTRL = 1 << 2


class FakeDrag:
    def __init__(self, x, y):
        self.start = (x, y)

    def get_start_point(self):
        return (True, *self.start)


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayHandToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.HandTest")
        cls.app.register(None)

    def setUp(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 400, 300)
        pixbuf.fill(0xffffffff)
        self.window = OverlayWindow(self.app, pixbuf, Settings())
        self.addCleanup(self.window.destroy)
        self.window.area.allocate(400, 300, -1, None)
        self.window.set_visible(True)
        self.window._mon_rects = [(0, 0, 400, 300)]
        self.drag(50, 50, 350, 250)             # the capture region
        self.window.select_tool("rect")
        self.drag(80, 80, 140, 120)             # one rectangle inside it
        self.rect = self.window.shapes[0]
        self.window.select_tool("hand")

    def drag(self, x0, y0, x1, y1):
        gesture = FakeDrag(x0, y0)
        self.window._on_drag_begin(gesture, x0, y0)
        self.window._on_drag_update(gesture, x1 - x0, y1 - y0)
        self.window._on_drag_end(gesture, x1 - x0, y1 - y0)

    def test_dragging_a_shape_moves_it_and_undo_puts_it_back(self):
        history_before = len(self.window._undo)
        self.drag(100, 100, 130, 110)
        moved = self.window.shapes[0]
        self.assertEqual(len(self.window.shapes), 1)
        self.assertEqual((moved.x - self.rect.x, moved.y - self.rect.y), (30, 10))
        self.assertEqual(len(self.window._undo), history_before + 1)
        self.window.undo()
        self.assertEqual(self.window.shapes[0], self.rect)
        self.window.redo()
        self.assertEqual(self.window.shapes[0], moved)

    def test_the_shape_is_drawn_live_while_it_moves_and_not_twice(self):
        gesture = FakeDrag(100, 100)
        self.window._on_drag_begin(gesture, 100, 100)
        self.assertEqual(self.window.shapes, [])
        self.window._on_drag_update(gesture, 20, 0)
        self.assertEqual(self.window._preview.x - self.rect.x, 20)
        self.window._on_drag_end(gesture, 20, 0)
        self.assertEqual(len(self.window.shapes), 1)
        self.assertIsNone(self.window._preview)

    def test_a_press_on_empty_space_does_nothing(self):
        history_before = len(self.window._undo)
        self.drag(250, 200, 280, 220)
        self.assertEqual(self.window.shapes, [self.rect])
        self.assertEqual(self.window.sel, (50, 50, 300, 200))
        self.assertEqual(len(self.window._undo), history_before)

    def test_a_click_without_movement_changes_nothing(self):
        history_before = len(self.window._undo)
        self.drag(100, 100, 100, 100)
        self.assertEqual(self.window.shapes, [self.rect])
        self.assertEqual(len(self.window._undo), history_before)

    def test_text_can_be_moved_too(self):
        text = Text((200, 150), "hello", self.window.style)
        self.window.shapes.append(text)
        self.drag(202, 152, 222, 162)
        moved = self.window.shapes[-1]
        self.assertEqual(moved.kind, "text")
        self.assertEqual((moved.x - text.x, moved.y - text.y), (20, 10))

    def test_cursor_says_grab_over_a_shape_and_default_elsewhere(self):
        self.window._on_motion(None, 100, 100)
        self.assertEqual(self.window.area.get_cursor().get_name(), "grab")
        self.window._on_motion(None, 250, 200)
        self.assertEqual(self.window.area.get_cursor().get_name(), "default")

    def test_a_blur_shows_its_footprint_instead_of_re_blurring_while_dragged(self):
        from unittest.mock import patch
        from wayland_feather_shot.editor import shapes as shape_model
        self.window.shapes.clear()
        self.window.select_tool("blur")
        self.drag(150, 150, 200, 190)
        self.assertEqual(self.window.shapes[0].kind, "obscure")
        self.window.select_tool("hand")
        gesture = FakeDrag(170, 170)
        self.window._on_drag_begin(gesture, 170, 170)
        self.window._on_drag_update(gesture, 10, 10)
        with patch.object(shape_model.Shape, "draw",
                          side_effect=AssertionError("blur rendered mid-drag")):
            self.window._snapshot(self.window.area, Gtk.Snapshot.new(), 400, 300)
        self.window._on_drag_end(gesture, 10, 10)
        self.assertEqual(self.window.shapes[0].kind, "obscure")

    def test_keys_wait_for_the_drag_to_finish(self):
        # The grabbed shape is out of self.shapes until release: Ctrl+Z here
        # used to leave it doubled, and a tool key broke the drag.
        self.window.select_tool("rect")
        self.drag(200, 200, 260, 240)
        second = self.window.shapes[1]
        self.window.select_tool("hand")
        gesture = FakeDrag(100, 100)
        self.window._on_drag_begin(gesture, 100, 100)
        self.window._on_drag_update(gesture, 20, 0)
        self.assertTrue(self.window._on_key(None, Gdk.KEY_z, 0, CTRL))
        self.assertTrue(self.window._on_key(None, Gdk.KEY_p, 0, 0))
        self.window._on_drag_end(gesture, 20, 0)
        self.assertEqual(self.window.tool, "hand")
        self.assertEqual(len(self.window.shapes), 2)
        self.assertEqual(self.window.shapes[0].x - self.rect.x, 20)
        self.assertEqual(self.window.shapes[1], second)

    def test_a_pixelate_being_dragged_out_leaves_the_blur_cache_alone(self):
        # Each frame's region is new; cached, the frames pushed the blurs of
        # finished shapes out and they were re-blurred on release.
        from wayland_feather_shot.editor import render
        self.window.select_tool("pixelate")
        before = set(render._obscure_cache.get(self.window.pixbuf, {}))
        gesture = FakeDrag(150, 150)
        self.window._on_drag_begin(gesture, 150, 150)
        for d in (10, 20, 30):
            self.window._on_drag_update(gesture, d, d)
            self.window._snapshot(self.window.area, Gtk.Snapshot.new(), 400, 300)
        self.assertEqual(set(render._obscure_cache.get(self.window.pixbuf, {})),
                         before)
        self.window._on_drag_end(gesture, 30, 30)

    def test_s_selects_the_hand_tool(self):
        self.window.select_tool("pen")
        self.window._on_key(None, Gdk.KEY_s, 0, 0)
        self.assertEqual(self.window.tool, "hand")


if __name__ == "__main__":
    unittest.main()
