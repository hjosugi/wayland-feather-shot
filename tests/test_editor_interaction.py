"""The frame around picked shapes: its handles, and resizing, rotating and
bending from them (editor/interaction.py, GTK-free).

Run:  python3 tests/test_editor_interaction.py
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.editor import shapes as S  # noqa: E402
from wayland_feather_shot.editor.geometry import Box  # noqa: E402
from wayland_feather_shot.editor.interaction import (  # noqa: E402
    PointerInfo, Reshaper, Viewport)

STYLE = S.Style(width=4.0, font_size=20.0)


def pointer(x, y, **flags):
    """A pointer at (x, y) with the view at 1:1 and no pan."""
    return PointerInfo(widget=(x, y), page=(x, y), **flags)


def rect(x, y, w, h):
    return S.RectShape((x, y, w, h), STYLE)


class ReshaperTestCase(unittest.TestCase):
    def reshaper(self, *shapes):
        return Reshaper(shapes, Viewport(scale=1.0, offset=(0.0, 0.0)))

    def drag(self, reshaper, x0, y0, x1, y1, **flags):
        started = reshaper.press(pointer(x0, y0, **flags))
        reshaper.drag(pointer(x1, y1, **flags))
        return started


class FrameTests(ReshaperTestCase):
    def test_a_lone_shape_keeps_its_own_rotated_frame(self):
        turned = rect(0, 0, 100, 50).rotated(0.5, (50, 25))
        self.assertAlmostEqual(self.reshaper(turned).selection_frame.rotation,
                               0.5)

    def test_several_shapes_share_an_axis_aligned_frame(self):
        frame = self.reshaper(rect(0, 0, 50, 50),
                              rect(100, 100, 50, 50)).selection_frame
        self.assertEqual(frame.rotation, 0.0)
        self.assertEqual(frame.box, Box(0, 0, 150, 150))


class HandleTests(ReshaperTestCase):
    def test_every_handle_is_reachable(self):
        reshaper = self.reshaper(rect(0, 0, 100, 100))
        frame = reshaper.selection_frame
        for name, (u, v) in [("nw", (0, 0)), ("ne", (1, 0)), ("se", (1, 1)),
                             ("sw", (0, 1)), ("n", (0.5, 0)), ("e", (1, 0.5)),
                             ("s", (0.5, 1)), ("w", (0, 0.5))]:
            widget = reshaper.viewport.to_widget(frame.unit_point(u, v))
            self.assertEqual(reshaper.handle_at(widget), name)

    def test_rotate_handles_sit_outside_the_corners(self):
        reshaper = self.reshaper(rect(0, 0, 100, 100))
        self.assertEqual(reshaper.handle_at((-11, -11)), "rot-nw")

    def test_nothing_is_grabbed_far_from_the_frame(self):
        reshaper = self.reshaper(rect(0, 0, 100, 100))
        self.assertIsNone(reshaper.handle_at((500, 500)))
        self.assertFalse(reshaper.press(pointer(500, 500)))

    def test_a_lone_arrow_has_its_own_three_handles(self):
        arrow = S.Arrow((0, 0), (100, 0), STYLE)
        reshaper = self.reshaper(arrow)
        self.assertEqual(reshaper.handle_at((0, 0)), "arrow-start")
        self.assertEqual(reshaper.handle_at((100, 0)), "arrow-end")
        self.assertEqual(reshaper.handle_at((50, 0)), "arrow-middle")
        self.assertEqual(reshaper.rotate_handle_points(), {})


class ResizeTests(ReshaperTestCase):
    def test_a_corner_handle_scales_about_the_opposite_corner(self):
        reshaper = self.reshaper(rect(10, 10, 100, 50))
        self.assertTrue(self.drag(reshaper, 110, 60, 210, 110))   # SE
        (resized,) = reshaper.shapes
        self.assertEqual(resized.origin, (10, 10))
        self.assertAlmostEqual(resized.props.w, 200)
        self.assertAlmostEqual(resized.props.h, 100)

    def test_dragging_the_north_west_handle_moves_the_origin(self):
        reshaper = self.reshaper(rect(100, 100, 100, 100))
        self.drag(reshaper, 100, 100, 150, 150)                 # NW inward
        (resized,) = reshaper.shapes
        self.assertAlmostEqual(resized.x, 150)
        self.assertAlmostEqual(resized.props.w, 50)

    def test_an_edge_handle_scales_one_axis_only(self):
        reshaper = self.reshaper(rect(0, 0, 100, 100))
        self.drag(reshaper, 100, 50, 200, 50)                   # E
        (resized,) = reshaper.shapes
        self.assertAlmostEqual(resized.props.w, 200)
        self.assertAlmostEqual(resized.props.h, 100)

    def test_shift_on_a_corner_keeps_the_aspect_ratio(self):
        reshaper = self.reshaper(rect(0, 0, 100, 100))
        self.drag(reshaper, 100, 100, 200, 130, shift=True)
        (resized,) = reshaper.shapes
        self.assertAlmostEqual(resized.props.w, resized.props.h)

    def test_resizing_is_re_applied_from_the_start_not_accumulated(self):
        reshaper = self.reshaper(rect(0, 0, 100, 100))
        reshaper.press(pointer(100, 100))
        reshaper.drag(pointer(300, 300))
        reshaper.drag(pointer(200, 200))                        # back off
        self.assertAlmostEqual(reshaper.shapes[0].props.w, 200)

    def test_several_shapes_scale_together(self):
        reshaper = self.reshaper(rect(0, 0, 50, 50), rect(100, 100, 50, 50))
        self.drag(reshaper, 150, 150, 300, 300)                 # SE, x2
        first, second = reshaper.shapes
        self.assertAlmostEqual(first.props.w, 100)
        self.assertEqual(second.origin, (200, 200))


class RotateTests(ReshaperTestCase):
    def test_dragging_a_rotate_handle_turns_the_shape(self):
        reshaper = self.reshaper(rect(0, 0, 100, 100))
        x, y = reshaper.rotate_handle_points()["rot-se"]
        reshaper.press(PointerInfo((x, y), (x, y)))
        # The handle starts at 45° from the centre; (-50, 150) is at 135°,
        # so the shape turns a quarter.
        reshaper.drag(pointer(-50, 150))
        self.assertAlmostEqual(abs(reshaper.shapes[0].rotation), math.pi / 2,
                               places=5)

    def test_shift_snaps_rotation_to_15_degrees(self):
        reshaper = self.reshaper(rect(0, 0, 100, 100))
        x, y = reshaper.rotate_handle_points()["rot-se"]
        reshaper.press(PointerInfo((x, y), (x, y), shift=True))
        reshaper.drag(pointer(60, -20, shift=True))
        degrees = math.degrees(reshaper.shapes[0].rotation)
        self.assertAlmostEqual(degrees % 15.0, 0.0, places=4)


class ArrowTests(ReshaperTestCase):
    def test_the_end_follows_and_the_start_stays(self):
        reshaper = self.reshaper(S.Arrow((0, 0), (100, 0), STYLE))
        self.drag(reshaper, 100, 0, 120, 40)
        (arrow,) = reshaper.shapes
        self.assertEqual(arrow.origin, (0, 0))
        end = arrow.to_page(arrow.props.end)
        self.assertEqual((round(end[0]), round(end[1])), (120, 40))

    def test_moving_the_start_keeps_the_tip_in_place(self):
        reshaper = self.reshaper(S.Arrow((0, 0), (100, 0), STYLE))
        self.drag(reshaper, 0, 0, 10, 30)
        (arrow,) = reshaper.shapes
        end = arrow.to_page(arrow.props.end)
        self.assertEqual((round(end[0]), round(end[1])), (100, 0))

    def test_the_middle_bends_it(self):
        reshaper = self.reshaper(S.Arrow((0, 0), (100, 0), STYLE))
        self.drag(reshaper, 50, 0, 50, 30)
        self.assertNotEqual(reshaper.shapes[0].props.bend, 0.0)


if __name__ == "__main__":
    unittest.main()
