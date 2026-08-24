"""Unit tests for the annotation shape model (GTK-free).

Run:  python3 tests/test_editor_shapes.py
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.editor import shapes as S  # noqa: E402
from wayland_feather_shot.editor.geometry import Box  # noqa: E402

STYLE = S.Style(width=4.0, font_size=20.0)


class ConstructorTests(unittest.TestCase):
    def test_rect_lands_where_it_was_dragged(self):
        shape = S.RectShape((10, 20, 100, 50), STYLE)
        self.assertEqual(shape.origin, (10, 20))
        self.assertEqual(shape.page_bounds, Box(10, 20, 100, 50))

    def test_pen_points_are_local_and_start_at_the_origin(self):
        shape = S.Pen([(50, 60), (60, 70)], STYLE)
        self.assertEqual(shape.origin, (50, 60))
        self.assertEqual(shape.props.points[0], (0.0, 0.0))
        self.assertEqual(shape.props.points[1], (10.0, 10.0))

    def test_arrow_stores_its_head_as_a_local_offset(self):
        shape = S.Arrow((10, 10), (110, 60), STYLE)
        self.assertEqual(shape.origin, (10, 10))
        self.assertEqual(shape.props.end, (100, 50))

    def test_line_is_an_arrow_with_no_heads(self):
        self.assertEqual(S.Line((0, 0), (10, 0), STYLE).props.head_end, "none")
        self.assertEqual(S.Arrow((0, 0), (10, 0), STYLE).props.head_end, "arrow")

    def test_marker_is_centred_on_the_click(self):
        shape = S.Marker((100, 100), 1, STYLE, diameter=40)
        self.assertEqual(shape.origin, (80, 80))
        self.assertEqual(shape.page_bounds, Box(80, 80, 40, 40))

    def test_shapes_get_distinct_ids(self):
        a = S.RectShape((0, 0, 1, 1), STYLE)
        b = S.RectShape((0, 0, 1, 1), STYLE)
        self.assertNotEqual(a.sid, b.sid)


class TransformTests(unittest.TestCase):
    def test_translate_returns_a_copy(self):
        shape = S.RectShape((0, 0, 10, 10), STYLE)
        moved = shape.translate(5, 5)
        self.assertEqual(shape.origin, (0, 0))
        self.assertEqual(moved.origin, (5, 5))

    def test_local_and_page_round_trip(self):
        shape = S.RectShape((10, 10, 100, 50), STYLE).rotated(0.7, (60, 35))
        page = (42.0, 17.0)
        back = shape.to_page(shape.to_local(page))
        self.assertAlmostEqual(back[0], page[0])
        self.assertAlmostEqual(back[1], page[1])

    def test_rotation_keeps_the_shape_the_same_size(self):
        shape = S.RectShape((0, 0, 100, 50), STYLE)
        turned = shape.rotated(math.pi / 2, (50, 25))
        self.assertAlmostEqual(turned.props.w, 100)
        self.assertAlmostEqual(turned.props.h, 50)
        # ...but its page-space footprint is now portrait.
        self.assertAlmostEqual(turned.page_bounds.w, 50, places=5)
        self.assertAlmostEqual(turned.page_bounds.h, 100, places=5)

    def test_scaling_a_rect_leaves_its_stroke_weight_alone(self):
        shape = S.RectShape((0, 0, 100, 50), STYLE).scaled(2, 3)
        self.assertEqual(shape.props.w, 200)
        self.assertEqual(shape.props.h, 150)
        self.assertEqual(shape.props.style.width, STYLE.width)

    def test_scaling_a_pen_stroke_scales_its_points(self):
        shape = S.Pen([(0, 0), (10, 20)], STYLE).scaled(2, 0.5)
        self.assertEqual(shape.props.points[1], (20.0, 10.0))

    def test_a_badge_stays_circular_under_a_lopsided_scale(self):
        shape = S.Marker((0, 0), 1, STYLE, diameter=40).scaled(2, 4)
        self.assertEqual(shape.props.diameter, 120)  # mean of the two scales

    def test_scaling_never_collapses_a_shape(self):
        shape = S.RectShape((0, 0, 100, 50), STYLE).scaled(0.0, 0.0)
        self.assertGreaterEqual(shape.props.w, 1)
        self.assertGreaterEqual(shape.props.h, 1)

    def test_text_scales_its_type_rather_than_stretching(self):
        shape = S.Text((0, 0), "hi", STYLE).scaled(2, 2)
        self.assertAlmostEqual(shape.props.style.font_size, 40)


class HitTestTests(unittest.TestCase):
    def test_arrow_ignores_the_empty_corner_of_its_bounding_box(self):
        arrow = S.Arrow((0, 0), (100, 100), STYLE)
        self.assertTrue(arrow.hit_test((50, 50), margin=4))
        self.assertFalse(arrow.hit_test((95, 5), margin=4))

    def test_hollow_rectangle_lets_a_click_through_its_middle(self):
        rect = S.RectShape((0, 0, 200, 200), STYLE)
        self.assertFalse(rect.hit_test((100, 100), margin=4))
        self.assertTrue(rect.hit_test((0, 100), margin=4))

    def test_filled_rectangle_catches_the_middle(self):
        rect = S.RectShape((0, 0, 200, 200), STYLE, filled=True)
        self.assertTrue(rect.hit_test((100, 100), margin=4))

    def test_hit_test_follows_a_rotated_shape(self):
        rect = S.RectShape((0, 0, 100, 20), STYLE, filled=True)
        turned = rect.rotated(math.pi / 2, (50, 10))
        self.assertTrue(turned.hit_test((50, 50), margin=2))
        self.assertFalse(turned.hit_test((95, 10), margin=2))

    def test_topmost_shape_wins(self):
        under = S.RectShape((0, 0, 100, 100), STYLE, filled=True)
        over = S.RectShape((0, 0, 100, 100), STYLE, filled=True)
        self.assertEqual(S.hit_shape([under, over], (50, 50)), 1)

    def test_hit_shape_returns_none_on_empty_canvas(self):
        self.assertIsNone(S.hit_shape([], (5, 5)))

    def test_marquee_selects_only_what_it_touches(self):
        shapes = [S.RectShape((0, 0, 20, 20), STYLE),
                  S.RectShape((500, 500, 20, 20), STYLE)]
        self.assertEqual(S.shapes_in(shapes, Box(-5, -5, 40, 40)), [0])


class SpotlightTests(unittest.TestCase):
    """#34: a spotlight keeps a region bright; several leave one union."""

    def test_a_spotlight_is_a_solid_region(self):
        spot = S.Spotlight((10, 10, 100, 60))
        self.assertEqual(spot.kind, "spotlight")
        self.assertEqual(spot.page_bounds, Box(10, 10, 100, 60))
        self.assertTrue(spot.is_filled)

    def test_it_carries_its_own_scrim(self):
        self.assertAlmostEqual(S.Spotlight((0, 0, 5, 5), scrim=0.8).props.scrim,
                               0.8)

    def test_it_resizes_like_any_other_box(self):
        spot = S.Spotlight((0, 0, 100, 50)).scaled(2, 3)
        self.assertEqual((spot.props.w, spot.props.h), (200, 150))

    def test_it_has_no_style_to_restyle(self):
        self.assertIsNone(S.Spotlight((0, 0, 5, 5)).style)

    def test_it_can_be_grabbed_anywhere_inside(self):
        spot = S.Spotlight((0, 0, 100, 100))
        self.assertTrue(spot.hit_test((50, 50), margin=2))


class NumberingTests(unittest.TestCase):
    """#21: counting badges hands out a duplicate after a delete."""

    def _markers(self, *numbers):
        return [S.Marker((0, 0), n, STYLE) for n in numbers]

    def test_first_badge_is_one(self):
        self.assertEqual(S.next_number([]), 1)

    def test_next_number_after_a_delete_does_not_repeat(self):
        shapes = self._markers(1, 2, 3)
        del shapes[0]
        self.assertEqual(S.next_number(shapes), 4)

    def test_next_number_after_deleting_the_last_reuses_it(self):
        shapes = self._markers(1, 2, 3)
        del shapes[-1]
        self.assertEqual(S.next_number(shapes), 3)

    def test_markers_and_step_arrows_share_one_sequence(self):
        shapes = [S.Marker((0, 0), 1, STYLE),
                  S.StepArrow((0, 0), (10, 10), 2, STYLE)]
        self.assertEqual(S.next_number(shapes), 3)

    def test_plain_arrows_do_not_take_a_number(self):
        self.assertEqual(S.next_number([S.Arrow((0, 0), (10, 10), STYLE)]), 1)


class StrokeWidthTests(unittest.TestCase):
    """#29: the same setting has to look the same at any capture resolution."""

    def test_reference_sized_image_uses_the_authored_value(self):
        self.assertAlmostEqual(
            S.page_stroke_width(4, S.REFERENCE_EDGE), 4.0)

    def test_a_4k_capture_scales_the_stroke_up(self):
        self.assertAlmostEqual(
            S.page_stroke_width(4, 3840), 4 * 3840 / S.REFERENCE_EDGE)

    def test_round_trip(self):
        page = S.page_stroke_width(6, 2560)
        self.assertAlmostEqual(S.slider_stroke_width(page, 2560), 6.0)

    def test_never_thinner_than_a_pixel(self):
        self.assertGreaterEqual(S.page_stroke_width(0.1, 100), 1.0)

    def test_blur_factor_maps_onto_the_density_range(self):
        self.assertAlmostEqual(S.density_from_factor(2), 0.0)
        self.assertAlmostEqual(S.density_from_factor(24), 1.0)
        self.assertAlmostEqual(S.density_from_factor(1000), 1.0)


if __name__ == "__main__":
    unittest.main()
