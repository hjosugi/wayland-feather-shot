"""The hand tool grabs placed shapes and moves them; the move is undoable.
Shift or Ctrl+click picks several, and they move together.

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
    from wayland_feather_shot.util.settings import Settings  # noqa: E402


SHIFT, CTRL = 1 << 0, 1 << 2


class FakeDrag:
    def __init__(self, x, y, state=0):
        self.start = (x, y)
        self.state = state

    def get_start_point(self):
        return (True, *self.start)

    def get_current_event_state(self):
        return self.state


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

    def drag(self, x0, y0, x1, y1, state=0):
        gesture = FakeDrag(x0, y0, state)
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
        (live,) = self.window._live_shapes()
        self.assertEqual(live.x - self.rect.x, 20)
        self.window._on_drag_end(gesture, 20, 0)
        self.assertEqual(len(self.window.shapes), 1)
        self.assertEqual(self.window._live_shapes(), [])

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

    def add_second_rect(self):
        self.window.select_tool("rect")
        self.drag(200, 150, 260, 200)
        self.window.select_tool("hand")
        return self.window.shapes[1]

    def picked(self):
        return {s.sid for s in self.window._picked_shapes()}

    def test_shift_or_ctrl_click_picks_several_and_they_move_together(self):
        for modifier in (SHIFT, CTRL):
            with self.subTest(modifier=modifier):
                self.setUp()
                second = self.add_second_rect()
                self.drag(100, 100, 100, 100)                 # pick the first
                self.drag(230, 175, 230, 175, modifier)       # add the second
                self.assertEqual(self.picked(), {self.rect.sid, second.sid})
                history_before = len(self.window._undo)
                self.drag(100, 100, 120, 130)                 # move both
                first, other = self.window.shapes
                self.assertEqual(
                    (first.x - self.rect.x, first.y - self.rect.y), (20, 30))
                self.assertEqual((other.x - second.x, other.y - second.y),
                                 (20, 30))
                self.assertEqual(len(self.window._undo), history_before + 1)
                self.window.undo()
                self.assertEqual(self.window.shapes, [self.rect, second])

    def test_a_modified_drag_on_an_unpicked_shape_takes_the_others_along(self):
        second = self.add_second_rect()
        self.drag(100, 100, 100, 100)
        self.drag(230, 175, 240, 185, SHIFT)
        first, other = self.window.shapes
        self.assertEqual(first.x - self.rect.x, 10)
        self.assertEqual(other.x - second.x, 10)

    def test_a_plain_press_on_another_shape_picks_only_that_one(self):
        second = self.add_second_rect()
        self.drag(100, 100, 100, 100)
        self.drag(230, 175, 230, 175)
        self.assertEqual(self.picked(), {second.sid})
        self.drag(230, 175, 250, 175)
        self.assertEqual(self.window.shapes[0], self.rect)  # left behind

    def test_a_click_on_a_picked_shape_keeps_just_it_or_drops_it(self):
        second = self.add_second_rect()
        self.drag(100, 100, 100, 100)
        self.drag(230, 175, 230, 175, CTRL)
        self.drag(230, 175, 230, 175)                       # just this one
        self.assertEqual(self.picked(), {second.sid})
        self.drag(100, 100, 100, 100, CTRL)
        self.drag(100, 100, 100, 100, CTRL)                 # and drop it again
        self.assertEqual(self.picked(), {second.sid})

    def test_a_press_on_empty_space_clears_the_pick_unless_modified(self):
        self.add_second_rect()
        self.drag(100, 100, 100, 100)
        self.drag(300, 230, 300, 230, SHIFT)
        self.assertEqual(self.picked(), {self.rect.sid})
        self.drag(300, 230, 300, 230)
        self.assertEqual(self.picked(), set())

    def test_picked_shapes_are_framed_and_the_pick_ends_with_the_tool(self):
        self.drag(100, 100, 100, 100)
        self.window._snapshot(self.window.area, Gtk.Snapshot.new(), 400, 300)
        self.assertEqual(self.picked(), {self.rect.sid})
        self.window.select_tool("pen")
        self.window.select_tool("hand")
        self.assertEqual(self.picked(), set())

    # -- reshaping a picked shape by its handles --

    def test_a_corner_handle_resizes_the_picked_shape(self):
        self.drag(100, 100, 100, 100)                   # pick the rectangle
        self.assertEqual(self.window._pick_handle_at(140, 120), "se")
        history_before = len(self.window._undo)
        self.drag(140, 120, 170, 140)
        (resized,) = self.window.shapes
        self.assertEqual((resized.x, resized.y), (self.rect.x, self.rect.y))
        self.assertAlmostEqual(resized.props.w, self.rect.props.w + 30)
        self.assertAlmostEqual(resized.props.h, self.rect.props.h + 20)
        self.assertEqual(len(self.window._undo), history_before + 1)
        self.window.undo()
        self.assertEqual(self.window.shapes, [self.rect])

    def test_shift_keeps_the_proportions(self):
        self.drag(100, 100, 100, 100)
        self.drag(140, 120, 200, 125, SHIFT)
        (resized,) = self.window.shapes
        self.assertAlmostEqual(resized.props.w / resized.props.h,
                               self.rect.props.w / self.rect.props.h)

    def test_the_handle_beyond_a_corner_rotates(self):
        self.drag(100, 100, 100, 100)
        engine = self.window._pick_engine()
        x, y = engine.rotate_handle_points()["rot-se"]
        self.drag(x, y, x - 30, y + 30)
        self.assertNotEqual(self.window.shapes[0].rotation, 0)

    def test_a_lone_arrows_end_follows_its_handle(self):
        self.window.shapes.clear()
        self.window.select_tool("arrow")
        self.drag(100, 200, 200, 200)
        arrow = self.window.shapes[0]
        self.window.select_tool("hand")
        self.drag(150, 200, 150, 200)                   # pick it
        self.assertEqual(self.window._pick_handle_at(200, 200), "arrow-end")
        self.drag(200, 200, 220, 160)
        moved = self.window.shapes[0]
        end = moved.to_page(moved.props.end)
        self.assertEqual((round(end[0]), round(end[1])), (220, 160))
        self.assertEqual((moved.x, moved.y), (arrow.x, arrow.y))

    def test_inside_the_frame_of_a_picked_ellipse_moves_it(self):
        self.window.shapes.clear()
        self.window.select_tool("ellipse")
        self.drag(70, 70, 330, 230)
        ellipse = self.window.shapes[0]
        self.window.select_tool("hand")
        self.drag(200, 70, 200, 70)                     # on its outline
        # Near the frame's corner: inside the frame, outside the ellipse,
        # clear of the handles.
        self.assertIsNone(self.window._shape_at(88, 84))
        self.assertIsNone(self.window._pick_handle_at(88, 84))
        self.drag(88, 84, 108, 94)
        moved = self.window.shapes[0]
        self.assertEqual((moved.x - ellipse.x, moved.y - ellipse.y), (20, 10))

    def test_handles_show_their_cursor_and_the_frame_is_drawn(self):
        self.drag(100, 100, 100, 100)
        self.window._on_motion(None, 140, 120)
        self.assertEqual(self.window.area.get_cursor().get_name(),
                         "nwse-resize")
        self.window._snapshot(self.window.area, Gtk.Snapshot.new(), 400, 300)
        gesture = FakeDrag(140, 120)
        self.window._on_drag_begin(gesture, 140, 120)
        self.window._on_drag_update(gesture, 10, 10)
        self.window._snapshot(self.window.area, Gtk.Snapshot.new(), 400, 300)
        self.assertEqual(self.window.shapes, [])        # lifted, drawn live
        self.window._on_drag_end(gesture, 10, 10)
        self.assertEqual(len(self.window.shapes), 1)

    # -- keys for the picked shapes --

    def key(self, keyval, state=0):
        return self.window._on_key(None, keyval, 0, state)

    def test_delete_removes_the_picked_shapes(self):
        second = self.add_second_rect()
        self.drag(100, 100, 100, 100)
        self.assertTrue(self.key(Gdk.KEY_Delete))
        self.assertEqual(self.window.shapes, [second])
        self.assertEqual(self.picked(), set())
        self.window.undo()
        self.assertEqual(self.window.shapes, [self.rect, second])

    def test_arrows_nudge_and_a_held_key_undoes_in_one_go(self):
        self.drag(100, 100, 100, 100)
        history_before = len(self.window._undo)
        for _ in range(3):
            self.key(Gdk.KEY_Right)
        self.key(Gdk.KEY_Down, SHIFT)
        moved = self.window.shapes[0]
        self.assertEqual((moved.x - self.rect.x, moved.y - self.rect.y),
                         (3, 10))
        self.assertEqual(len(self.window._undo), history_before + 1)
        self.window.undo()
        self.assertEqual(self.window.shapes, [self.rect])

    def test_a_nudge_after_another_change_is_a_step_of_its_own(self):
        self.drag(100, 100, 100, 100)
        self.key(Gdk.KEY_Right)
        self.drag(100, 100, 110, 100)                   # a move between
        self.key(Gdk.KEY_Right)
        self.window.undo()
        self.assertEqual(self.window.shapes[0].x - self.rect.x, 11)

    def test_ctrl_a_picks_every_shape_with_the_hand(self):
        second = self.add_second_rect()
        self.window.select_tool("pen")
        self.assertTrue(self.key(Gdk.KEY_a, CTRL))
        self.assertEqual(self.window.tool, "hand")
        self.assertEqual(self.picked(), {self.rect.sid, second.sid})

    def test_ctrl_up_and_down_restack_the_picked_shapes(self):
        second = self.add_second_rect()
        self.drag(100, 100, 100, 100)                   # the lower one
        self.key(Gdk.KEY_Up, CTRL)
        self.assertEqual([s.sid for s in self.window.shapes],
                         [second.sid, self.rect.sid])
        self.key(Gdk.KEY_Up, CTRL)                      # already on top
        self.assertEqual(len(self.window.shapes), 2)
        self.key(Gdk.KEY_Down, CTRL)
        self.assertEqual([s.sid for s in self.window.shapes],
                         [self.rect.sid, second.sid])

    def test_the_keys_leave_other_tools_alone(self):
        self.drag(100, 100, 100, 100)
        self.window.select_tool("pen")                  # drops the pick
        self.assertFalse(self.key(Gdk.KEY_Delete))
        self.assertEqual(self.window.shapes, [self.rect])

    # -- the style controls on the picked shapes --

    def test_a_colour_goes_to_the_picked_shapes_one_step_each(self):
        second = self.add_second_rect()
        self.drag(100, 100, 100, 100)
        history_before = len(self.window._undo)
        self.window._set_colour((0.1, 0.2, 0.3, 1.0))
        self.window._set_colour((0.4, 0.5, 0.6, 1.0))
        first, other = self.window.shapes
        self.assertEqual(first.style.rgba, (0.4, 0.5, 0.6, 1.0))
        self.assertEqual(other, second)                 # not picked
        self.assertEqual(len(self.window._undo), history_before + 2)

    def test_a_slide_of_the_width_is_one_step(self):
        self.drag(100, 100, 100, 100)
        history_before = len(self.window._undo)
        for value in (5, 6, 7):
            self.window._size_spin.set_value(value)
        self.assertEqual(len(self.window._undo), history_before + 1)
        self.assertEqual(self.window.shapes[0].style.width,
                         self.window._page_width(7))
        self.window.undo()
        self.assertEqual(self.window.shapes, [self.rect])

    def test_the_menu_shows_what_the_picked_shapes_use(self):
        text = Text((200, 150), "hello", self.window.style)
        self.window.shapes.append(text)
        self.drag(202, 152, 202, 152)                   # pick the text
        self.window._refresh_style_menu()
        rows = {n for n, r in self.window._style_rows.items()
                if r.get_visible()}
        self.assertTrue({"align", "font", "text_style"} <= rows)
        self.assertEqual(self.window._size_kind, "text")
        self.window._align_buttons["center"].set_active(True)
        self.assertEqual(self.window.shapes[-1].props.align, "center")

    def test_heads_strength_and_dim_reach_their_kinds(self):
        from wayland_feather_shot.editor import arrows
        self.window.shapes.clear()
        for tool, a, b in (("arrow", (100, 200), (200, 200)),
                           ("blur", (220, 80), (300, 140)),
                           ("spotlight", (220, 160), (330, 240))):
            self.window.select_tool(tool)
            self.drag(*a, *b)
        self.window._on_key(None, Gdk.KEY_a, 0, CTRL)  # pick them all
        self.window._head_choosers["head_start"].set_selected(
            arrows.HEADS.index("dot"))
        self.window._strength_scale.set_value(0.9)
        self.window._dim_scale.set_value(0.2)
        arrow, blur, spot = self.window.shapes
        self.assertEqual(arrow.props.head_start, "dot")
        self.assertAlmostEqual(blur.props.density, 0.9)
        self.assertAlmostEqual(spot.props.scrim, 0.2)

    def test_without_a_pick_the_controls_leave_placed_shapes_alone(self):
        self.window._set_colour((0.1, 0.2, 0.3, 1.0))
        self.assertEqual(self.window.shapes, [self.rect])

    def test_typing_into_a_picked_text_leaves_the_other_picks_as_they_are(
            self):
        boxed = Text((200, 150), "boxed", self.window.style,
                     outline=False, background=True)
        plain = Text((200, 200), "plain", self.window.style, outline=False)
        self.window.shapes = [boxed, plain]
        self.window._on_key(None, Gdk.KEY_a, 0, CTRL)
        self.window._edit_placed_text(0)                # takes "box"
        self.assertEqual(self.window.text_style, "box")
        self.assertFalse(self.window.shapes[0].props.background)

    def test_s_selects_the_hand_tool(self):
        self.window.select_tool("pen")
        self.window._on_key(None, Gdk.KEY_s, 0, 0)
        self.assertEqual(self.window.tool, "hand")


if __name__ == "__main__":
    unittest.main()
