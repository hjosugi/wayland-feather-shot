"""Unit tests for the editor's pointer state machine (GTK-free).

Run:  python3 tests/test_editor_interaction.py
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.editor import shapes as S  # noqa: E402
from wayland_feather_shot.editor.document import Document  # noqa: E402
from wayland_feather_shot.editor.geometry import Box  # noqa: E402
from wayland_feather_shot.editor.interaction import (  # noqa: E402
    Editor, Idle, PointerInfo, SelectionFrame, Viewport)


def pointer(x, y, **flags):
    """A pointer at (x, y) with the canvas at 1:1 and no pan."""
    return PointerInfo(widget=(x, y), page=(x, y), **flags)


class EditorTestCase(unittest.TestCase):
    def setUp(self):
        self.editor = Editor(Document(), S.Style(width=4.0, font_size=20.0))
        self.editor.viewport = Viewport(image_size=(1000.0, 800.0), scale=1.0,
                                        offset=(0.0, 0.0))

    def drag(self, x0, y0, x1, y1, **flags):
        self.editor.pointer_down(pointer(x0, y0, **flags))
        self.editor.pointer_move(pointer(x1, y1, **flags))
        self.editor.pointer_up(pointer(x1, y1, **flags))

    def draw_rect(self, rect=(10, 10, 100, 50)):
        x, y, w, h = rect
        self.editor.tool = "rect"
        self.drag(x, y, x + w, y + h)
        self.editor.tool = "select"
        return self.editor.doc.shapes[-1]


class CreationTests(EditorTestCase):
    def test_dragging_a_rectangle_creates_and_selects_it(self):
        self.editor.tool = "rect"
        self.drag(10, 10, 110, 60)
        self.assertEqual(len(self.editor.doc.shapes), 1)
        self.assertEqual(self.editor.doc.shapes[0].page_bounds,
                         Box(10, 10, 100, 50))
        self.assertEqual(len(self.editor.doc.selected), 1)

    def test_shift_constrains_a_box_to_a_square(self):
        self.editor.tool = "rect"
        self.drag(0, 0, 100, 30, shift=True)
        props = self.editor.doc.shapes[0].props
        self.assertEqual((props.w, props.h), (100, 100))

    def test_a_click_without_a_drag_leaves_no_speck_behind(self):
        self.editor.tool = "rect"
        self.drag(50, 50, 50, 50)
        self.assertEqual(self.editor.doc.shapes, [])
        # ...and no undo step for the non-edit.
        self.assertFalse(self.editor.doc.can_undo)

    def test_a_too_short_arrow_is_discarded(self):
        self.editor.tool = "arrow"
        self.drag(50, 50, 52, 51)
        self.assertEqual(self.editor.doc.shapes, [])

    def test_shift_snaps_an_arrow_to_15_degrees(self):
        self.editor.tool = "arrow"
        self.drag(0, 0, 100, 10, shift=True)
        end = self.editor.doc.shapes[0].props.end
        angle = math.degrees(math.atan2(end[1], end[0]))
        self.assertAlmostEqual(angle % 15.0, 0.0, places=6)

    def test_pen_collects_points_and_normalizes_its_origin(self):
        self.editor.tool = "pen"
        self.editor.pointer_down(pointer(20, 20))
        for i in range(1, 6):
            self.editor.pointer_move(pointer(20 + i * 10, 20))
        self.editor.pointer_up(pointer(70, 20))
        shape = self.editor.doc.shapes[0]
        self.assertEqual(shape.origin, (20, 20))
        self.assertEqual(shape.props.points[0], (0.0, 0.0))
        self.assertGreater(len(shape.props.points), 2)

    def test_a_pen_stroke_that_returns_to_its_start_closes(self):
        self.editor.tool = "pen"
        self.editor.pointer_down(pointer(0, 0))
        for p in [(50, 0), (50, 50), (0, 50), (0, 2)]:
            self.editor.pointer_move(pointer(*p))
        self.editor.pointer_up(pointer(0, 2))
        self.assertTrue(self.editor.doc.shapes[0].props.closed)

    def test_a_single_point_stroke_is_dropped(self):
        self.editor.tool = "pen"
        self.editor.pointer_down(pointer(5, 5))
        self.editor.pointer_up(pointer(5, 5))
        self.assertEqual(self.editor.doc.shapes, [])

    def test_step_arrows_number_themselves(self):
        self.editor.tool = "steparrow"
        self.drag(0, 0, 100, 100)
        self.drag(0, 100, 100, 200)
        numbers = [s.props.number for s in self.editor.doc.shapes]
        self.assertEqual(numbers, [1, 2])

    def test_the_marker_tool_places_a_numbered_badge_on_click(self):
        self.editor.tool = "marker"
        self.assertIsNone(self.editor.click(pointer(40, 40)))
        self.assertEqual(self.editor.doc.shapes[0].props.number, 1)

    def test_click_tools_that_need_content_ask_the_window(self):
        # Bubbles and stickers still need a dialog; text does not any more.
        for tool in ("bubble", "emoji"):
            self.editor.tool = tool
            self.assertEqual(self.editor.click(pointer(10, 10)), tool)
        self.assertEqual(self.editor.doc.shapes, [])


class TextEditingTests(EditorTestCase):
    """#31: text is typed on the canvas, not into a dialog."""

    def _new_text(self, at=(50, 50), text="hello"):
        self.editor.tool = "text"
        self.editor.click(pointer(*at))
        sid = self.editor.editing_sid
        self.editor.update_text(sid, text)
        return sid

    def test_clicking_with_the_text_tool_starts_typing_immediately(self):
        self.editor.tool = "text"
        self.assertIsNone(self.editor.click(pointer(30, 30)))
        self.assertIsNotNone(self.editor.editing_sid)
        self.assertEqual(len(self.editor.doc.shapes), 1)

    def test_typing_updates_the_shape(self):
        sid = self._new_text(text="annotated")
        self.assertEqual(self.editor.doc.shape(sid).props.text, "annotated")
        self.assertGreater(self.editor.doc.shape(sid).props.w, 0)

    def test_committing_keeps_the_text(self):
        sid = self._new_text()
        self.editor.stop_editing()
        self.assertIsNone(self.editor.editing_sid)
        self.assertIsNotNone(self.editor.doc.shape(sid))

    def test_an_empty_text_shape_is_discarded(self):
        self.editor.tool = "text"
        self.editor.click(pointer(10, 10))
        self.editor.stop_editing()
        self.assertEqual(self.editor.doc.shapes, [])

    def test_whitespace_only_counts_as_empty(self):
        self._new_text(text="   \n  ")
        self.editor.stop_editing()
        self.assertEqual(self.editor.doc.shapes, [])

    def test_clicking_existing_text_reopens_it(self):
        sid = self._new_text(at=(50, 50), text="first")
        self.editor.stop_editing()
        self.editor.tool = "text"
        self.editor.click(pointer(52, 52))
        self.assertEqual(self.editor.editing_sid, sid)

    def test_clicking_elsewhere_commits_what_was_typed(self):
        sid = self._new_text(text="kept")
        self.editor.tool = "select"
        self.editor.pointer_down(pointer(400, 400))
        self.editor.pointer_up(pointer(400, 400))
        self.assertIsNone(self.editor.editing_sid)
        self.assertEqual(self.editor.doc.shape(sid).props.text, "kept")

    def test_left_aligned_text_grows_rightwards(self):
        sid = self._new_text(at=(100, 100), text="a")
        origin = self.editor.doc.shape(sid).origin
        self.editor.update_text(sid, "a much longer line")
        self.assertEqual(self.editor.doc.shape(sid).origin, origin)

    def test_centred_text_grows_evenly_to_both_sides(self):
        self.editor.text_align = "center"
        sid = self._new_text(at=(100, 100), text="a")
        before = self.editor.doc.shape(sid)
        self.editor.update_text(sid, "a much longer line")
        after = self.editor.doc.shape(sid)
        grew = after.props.w - before.props.w
        self.assertAlmostEqual(before.x - after.x, grew / 2, places=6)

    def test_right_aligned_text_grows_leftwards(self):
        self.editor.text_align = "right"
        sid = self._new_text(at=(100, 100), text="a")
        before = self.editor.doc.shape(sid)
        self.editor.update_text(sid, "a much longer line")
        after = self.editor.doc.shape(sid)
        self.assertAlmostEqual(before.x - after.x,
                               after.props.w - before.props.w, places=6)

    def test_alignment_applies_to_the_selection(self):
        sid = self._new_text(text="x")
        self.editor.stop_editing()
        self.editor.doc.select([sid])
        self.editor.set_text_align("center")
        self.assertEqual(self.editor.doc.shape(sid).props.align, "center")

    def test_a_side_handle_switches_text_from_growing_to_wrapping(self):
        sid = self._new_text(text="a fairly long line of text")
        self.editor.stop_editing()
        shape = self.editor.doc.shape(sid)
        self.assertTrue(shape.props.auto_size)
        narrowed = shape.scaled(0.5, 1.0, width_only=True)
        self.assertFalse(narrowed.props.auto_size)
        self.assertGreater(narrowed.props.wrap_width, 0)
        self.assertLess(narrowed.props.wrap_width, shape.props.w)

    def test_a_corner_handle_scales_the_type_instead(self):
        sid = self._new_text(text="scale me")
        self.editor.stop_editing()
        shape = self.editor.doc.shape(sid)
        bigger = shape.scaled(2.0, 2.0)
        self.assertTrue(bigger.props.auto_size)
        self.assertAlmostEqual(bigger.props.style.font_size,
                               shape.props.style.font_size * 2)


class SelectionTests(EditorTestCase):
    def test_clicking_a_shape_selects_it(self):
        shape = self.draw_rect()
        self.editor.doc.clear_selection()
        self.drag(10, 10, 10, 10)
        self.assertEqual(self.editor.doc.selected, {shape.sid})

    def test_clicking_the_hollow_middle_selects_nothing(self):
        self.draw_rect((0, 0, 400, 400))
        self.editor.doc.clear_selection()
        self.drag(200, 200, 200, 200)
        self.assertEqual(self.editor.doc.selected, set())

    def test_shift_click_extends_the_selection(self):
        first = self.draw_rect((0, 0, 100, 50))
        second = self.draw_rect((200, 0, 100, 50))
        self.editor.doc.select([first.sid])
        self.drag(230, 0, 230, 0, shift=True)
        self.assertEqual(self.editor.doc.selected, {first.sid, second.sid})

    def test_shift_click_on_a_selected_shape_deselects_it(self):
        shape = self.draw_rect()
        # On the top edge, away from the corner and midpoint handles.
        self.drag(40, 10, 40, 10, shift=True)
        self.assertNotIn(shape.sid, self.editor.doc.selected)

    def test_marquee_selects_what_it_touches(self):
        near = self.draw_rect((0, 0, 50, 50))
        self.draw_rect((600, 600, 50, 50))
        self.editor.doc.clear_selection()
        self.drag(500, 0, 520, 20)          # empty space: clears
        self.drag(-10, -10, 100, 100)       # over the first rect
        self.assertEqual(self.editor.doc.selected, {near.sid})

    def test_dragging_moves_the_selection(self):
        shape = self.draw_rect((10, 10, 100, 50))
        self.drag(40, 10, 90, 40)
        self.assertEqual(self.editor.doc.shape(shape.sid).origin, (60, 40))

    def test_shift_drag_locks_movement_to_one_axis(self):
        # Shift is read per motion event: pressing with shift *toggles* the
        # selection, so an axis lock is something you reach for mid-drag.
        shape = self.draw_rect((10, 10, 100, 50))
        self.editor.pointer_down(pointer(40, 10))
        self.editor.pointer_move(pointer(140, 30, shift=True))
        self.editor.pointer_up(pointer(140, 30, shift=True))
        self.assertEqual(self.editor.doc.shape(shape.sid).origin, (110, 10))

    def test_the_selection_frame_can_be_dragged_from_its_empty_middle(self):
        shape = self.draw_rect((0, 0, 400, 400))
        self.drag(200, 200, 250, 250)
        self.assertEqual(self.editor.doc.shape(shape.sid).origin, (50, 50))

    def test_a_lone_shape_keeps_its_own_rotated_frame(self):
        self.draw_rect((0, 0, 100, 50))
        self.editor.doc.shapes = [self.editor.doc.shapes[0].rotated(0.5, (50, 25))]
        frame = self.editor.selection_frame
        self.assertAlmostEqual(frame.rotation, 0.5)

    def test_several_shapes_share_an_axis_aligned_frame(self):
        a = self.draw_rect((0, 0, 50, 50))
        b = self.draw_rect((100, 100, 50, 50))
        self.editor.doc.select([a.sid, b.sid])
        frame = self.editor.selection_frame
        self.assertEqual(frame.rotation, 0.0)
        self.assertEqual(frame.box, Box(0, 0, 150, 150))


class HandleTests(EditorTestCase):
    def test_every_handle_is_reachable(self):
        self.draw_rect((0, 0, 100, 100))
        frame = self.editor.selection_frame
        for name, (u, v) in [("nw", (0, 0)), ("ne", (1, 0)), ("se", (1, 1)),
                             ("sw", (0, 1)), ("n", (0.5, 0)), ("e", (1, 0.5)),
                             ("s", (0.5, 1)), ("w", (0, 0.5))]:
            widget = self.editor.viewport.to_widget(frame.unit_point(u, v))
            self.assertEqual(self.editor.handle_at(widget), name)

    def test_rotate_handles_sit_outside_the_corners(self):
        self.draw_rect((0, 0, 100, 100))
        frame = self.editor.selection_frame
        corner = self.editor.viewport.to_widget(frame.unit_point(0, 0))
        outside = (corner[0] - 11, corner[1] - 11)
        self.assertEqual(self.editor.handle_at(outside), "rot-nw")

    def test_nothing_is_grabbed_far_from_the_frame(self):
        self.draw_rect((0, 0, 100, 100))
        self.assertIsNone(self.editor.handle_at((500, 500)))

    def test_no_handles_without_a_selection(self):
        self.assertIsNone(self.editor.handle_at((0, 0)))


class ResizeTests(EditorTestCase):
    def test_a_corner_handle_scales_about_the_opposite_corner(self):
        shape = self.draw_rect((10, 10, 100, 50))
        self.drag(110, 60, 210, 110)        # drag SE
        resized = self.editor.doc.shape(shape.sid)
        self.assertEqual(resized.origin, (10, 10))
        self.assertAlmostEqual(resized.props.w, 200)
        self.assertAlmostEqual(resized.props.h, 100)

    def test_dragging_the_north_west_handle_moves_the_origin(self):
        shape = self.draw_rect((100, 100, 100, 100))
        self.drag(100, 100, 150, 150)       # drag NW inward
        resized = self.editor.doc.shape(shape.sid)
        self.assertAlmostEqual(resized.x, 150)
        self.assertAlmostEqual(resized.props.w, 50)

    def test_an_edge_handle_scales_one_axis_only(self):
        shape = self.draw_rect((0, 0, 100, 100))
        self.drag(100, 50, 200, 50)         # drag E
        resized = self.editor.doc.shape(shape.sid)
        self.assertAlmostEqual(resized.props.w, 200)
        self.assertAlmostEqual(resized.props.h, 100)

    def test_shift_on_a_corner_keeps_the_aspect_ratio(self):
        shape = self.draw_rect((0, 0, 100, 100))
        self.drag(100, 100, 200, 130, shift=True)
        resized = self.editor.doc.shape(shape.sid)
        self.assertAlmostEqual(resized.props.w, resized.props.h)

    def test_resizing_is_re_applied_from_the_snapshot_not_accumulated(self):
        shape = self.draw_rect((0, 0, 100, 100))
        self.editor.pointer_down(pointer(100, 100))
        self.editor.pointer_move(pointer(300, 300))
        self.editor.pointer_move(pointer(200, 200))   # back off
        self.editor.pointer_up(pointer(200, 200))
        resized = self.editor.doc.shape(shape.sid)
        self.assertAlmostEqual(resized.props.w, 200)

    def test_a_resize_is_undoable_as_one_step(self):
        shape = self.draw_rect((0, 0, 100, 100))
        self.drag(100, 100, 300, 300)
        self.editor.doc.undo()
        self.assertAlmostEqual(self.editor.doc.shape(shape.sid).props.w, 100)


class RotateTests(EditorTestCase):
    def _rotate_handle(self):
        frame = self.editor.selection_frame
        corner = self.editor.viewport.to_widget(frame.unit_point(1, 1))
        return (corner[0] + 11, corner[1] + 11)

    def test_dragging_a_rotate_handle_turns_the_shape(self):
        shape = self.draw_rect((0, 0, 100, 100))
        handle = self._rotate_handle()
        self.editor.pointer_down(PointerInfo(handle, handle))
        # The handle starts at 45° from the centre; (-50, 150) is at 135°, so
        # the shape turns a quarter.
        self.editor.pointer_move(pointer(-50, 150))
        self.editor.pointer_up(pointer(-50, 150))
        turned = self.editor.doc.shape(shape.sid)
        self.assertAlmostEqual(abs(turned.rotation), math.pi / 2, places=5)

    def test_shift_snaps_rotation_to_15_degrees(self):
        shape = self.draw_rect((0, 0, 100, 100))
        handle = self._rotate_handle()
        self.editor.pointer_down(PointerInfo(handle, handle, shift=True))
        self.editor.pointer_move(pointer(60, -20, shift=True))
        self.editor.pointer_up(pointer(60, -20, shift=True))
        degrees = math.degrees(self.editor.doc.shape(shape.sid).rotation)
        self.assertAlmostEqual(degrees % 15.0, 0.0, places=4)


class StateMachineTests(EditorTestCase):
    def test_the_editor_returns_to_idle_after_every_gesture(self):
        for tool in ("rect", "pen", "arrow", "select"):
            self.editor.tool = tool
            self.drag(0, 0, 40, 40)
            self.assertIsInstance(self.editor.state, Idle)

    def test_moves_before_a_press_are_ignored(self):
        self.editor.pointer_move(pointer(10, 10))
        self.assertEqual(self.editor.doc.shapes, [])

    def test_stroke_width_is_converted_into_page_units(self):
        self.editor.viewport = Viewport(image_size=(3840.0, 2160.0), scale=1.0)
        expected = S.page_stroke_width(4.0, 3840.0)
        self.assertAlmostEqual(self.editor.page_style.width, expected)


class DocumentTests(EditorTestCase):
    def test_undo_and_redo_walk_the_history(self):
        self.draw_rect((0, 0, 10, 10))
        self.draw_rect((50, 50, 10, 10))
        self.assertEqual(len(self.editor.doc.shapes), 2)
        self.editor.doc.undo()
        self.assertEqual(len(self.editor.doc.shapes), 1)
        self.editor.doc.redo()
        self.assertEqual(len(self.editor.doc.shapes), 2)

    def test_undo_drops_a_selection_of_shapes_that_no_longer_exist(self):
        self.draw_rect((0, 0, 10, 10))
        self.editor.doc.undo()
        self.assertEqual(self.editor.doc.selected, set())

    def test_z_order_moves(self):
        first = self.draw_rect((0, 0, 10, 10))
        self.draw_rect((50, 50, 10, 10))
        self.editor.doc.select([first.sid])
        self.editor.doc.bring_to_front()
        self.assertEqual(self.editor.doc.shapes[-1].sid, first.sid)
        self.editor.doc.send_to_back()
        self.assertEqual(self.editor.doc.shapes[0].sid, first.sid)

    def test_nudging_moves_only_the_selection(self):
        first = self.draw_rect((0, 0, 10, 10))
        second = self.draw_rect((50, 50, 10, 10))
        self.editor.doc.select([first.sid])
        self.editor.doc.nudge_selected(3, -2)
        self.assertEqual(self.editor.doc.shape(first.sid).origin, (3, -2))
        self.assertEqual(self.editor.doc.shape(second.sid).origin, (50, 50))

    def test_restyling_skips_shapes_that_have_no_style(self):
        rect = self.draw_rect((0, 0, 10, 10))
        blur = S.Obscure((0, 0, 10, 10))
        self.editor.doc.add(blur)
        self.editor.doc.select([rect.sid, blur.sid])
        self.assertTrue(self.editor.doc.restyle_selected(S.Style(width=9.0)))
        self.assertEqual(self.editor.doc.shape(rect.sid).style.width, 9.0)
        self.assertIsNone(self.editor.doc.shape(blur.sid).style)

    def test_a_snapshot_carries_the_base_image(self):
        # A composite redaction and a crop change the pixels as well as the
        # shapes, so undo has to restore both together.
        self.editor.base_provider = lambda: "before"
        self.draw_rect((0, 0, 10, 10))
        self.assertEqual(self.editor.doc.undo("after"), "before")

    def test_redo_hands_the_later_base_back(self):
        self.editor.base_provider = lambda: "before"
        self.draw_rect((0, 0, 10, 10))
        self.editor.doc.undo("after")
        self.assertEqual(self.editor.doc.redo("before"), "after")

    def test_history_is_bounded(self):
        from wayland_feather_shot.editor.document import HISTORY_LIMIT
        for _ in range(HISTORY_LIMIT + 20):
            self.editor.doc.mark_undo()
        self.assertLessEqual(len(self.editor.doc._undo), HISTORY_LIMIT)


if __name__ == "__main__":
    unittest.main()
