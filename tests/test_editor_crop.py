"""Unit tests for the crop rect editor (GTK-free).

Run:  python3 tests/test_editor_crop.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.editor import crop  # noqa: E402

SQUARE = (1000.0, 1000.0)
WIDE = (1600.0, 900.0)


def inside_unit(rect, tolerance=1e-9):
    x, y, w, h = rect
    return (x >= -tolerance and y >= -tolerance
            and x + w <= 1 + tolerance and y + h <= 1 + tolerance)


class AspectTests(unittest.TestCase):
    def test_freeform_has_no_ratio(self):
        self.assertIsNone(crop.normalized_ratio("free", SQUARE))
        self.assertFalse(crop.locks_aspect("free"))

    def test_original_matches_the_image(self):
        self.assertAlmostEqual(crop.pixel_ratio("original", WIDE), 1600 / 900)
        # In normalized space "original" is always 1:1, since the unit rect
        # already carries the image's shape.
        self.assertAlmostEqual(crop.normalized_ratio("original", WIDE), 1.0)

    def test_a_square_crop_of_a_wide_image_is_not_a_normalized_square(self):
        ratio = crop.normalized_ratio("1:1", WIDE)
        self.assertAlmostEqual(ratio, 900 / 1600)

    def test_every_preset_resolves(self):
        for name in crop.ASPECTS:
            crop.normalized_ratio(name, WIDE)
            self.assertIn(name, crop.ASPECT_TITLES)

    def test_an_unknown_preset_is_freeform_rather_than_a_crash(self):
        self.assertIsNone(crop.normalized_ratio("21:9", WIDE))


class ApplyAspectTests(unittest.TestCase):
    def test_fitting_16_9_into_a_square_uses_the_full_width(self):
        result = crop.apply_aspect(crop.UNIT, crop.normalized_ratio("16:9", SQUARE))
        self.assertAlmostEqual(result[2], 1.0)
        self.assertAlmostEqual(result[3], 9 / 16)
        self.assertTrue(inside_unit(result))

    def test_the_fitted_rect_keeps_the_original_centre(self):
        source = (0.2, 0.2, 0.4, 0.4)
        result = crop.apply_aspect(source, crop.normalized_ratio("16:9", SQUARE))
        self.assertAlmostEqual(result[0] + result[2] / 2, 0.4)
        self.assertAlmostEqual(result[1] + result[3] / 2, 0.4)

    def test_a_fitted_rect_near_the_edge_is_pushed_back_inside(self):
        result = crop.apply_aspect((0.0, 0.0, 1.0, 0.2),
                                   crop.normalized_ratio("1:1", SQUARE))
        self.assertTrue(inside_unit(result))

    def test_freeform_leaves_the_rect_alone(self):
        rect = (0.1, 0.2, 0.3, 0.4)
        self.assertEqual(crop.apply_aspect(rect, None), rect)


class ResizeTests(unittest.TestCase):
    RECT = (0.2, 0.2, 0.4, 0.4)

    def test_a_corner_drag_moves_only_that_corner(self):
        result = crop.resize(self.RECT, "se", (0.9, 0.8))
        self.assertAlmostEqual(result[0], 0.2)
        self.assertAlmostEqual(result[1], 0.2)
        self.assertAlmostEqual(result[0] + result[2], 0.9)
        self.assertAlmostEqual(result[1] + result[3], 0.8)

    def test_dragging_the_north_west_corner_moves_the_origin(self):
        result = crop.resize(self.RECT, "nw", (0.05, 0.1))
        self.assertAlmostEqual(result[0], 0.05)
        self.assertAlmostEqual(result[1], 0.1)
        self.assertAlmostEqual(result[0] + result[2], 0.6)

    def test_an_edge_drag_touches_one_axis(self):
        result = crop.resize(self.RECT, "e", (0.9, 0.9))
        self.assertAlmostEqual(result[1], self.RECT[1])
        self.assertAlmostEqual(result[3], self.RECT[3])
        self.assertAlmostEqual(result[0] + result[2], 0.9)

    def test_an_edge_drag_ignores_the_aspect_lock(self):
        ratio = crop.normalized_ratio("1:1", SQUARE)
        result = crop.resize(self.RECT, "e", (0.9, 0.9), ratio=ratio)
        self.assertAlmostEqual(result[3], self.RECT[3])

    def test_a_corner_drag_respects_the_aspect_lock(self):
        ratio = crop.normalized_ratio("1:1", SQUARE)
        result = crop.resize(self.RECT, "se", (0.9, 0.7), ratio=ratio)
        self.assertAlmostEqual(result[2], result[3], places=6)

    def test_an_aspect_locked_drag_stays_inside_the_image(self):
        ratio = crop.normalized_ratio("16:9", SQUARE)
        for handle in crop.CORNERS:
            for point in ((0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0)):
                result = crop.resize(self.RECT, handle, point, ratio=ratio)
                self.assertTrue(inside_unit(result),
                                f"{handle} -> {point} gave {result}")

    def test_a_drag_past_the_opposite_edge_stops_at_the_minimum(self):
        result = crop.resize(self.RECT, "e", (0.0, 0.5), min_size=0.05)
        self.assertAlmostEqual(result[2], 0.05)
        self.assertGreater(result[2], 0)

    def test_a_pointer_outside_the_image_is_clamped(self):
        result = crop.resize(self.RECT, "se", (5.0, -5.0))
        self.assertTrue(inside_unit(result))

    def test_dragging_never_produces_a_negative_size(self):
        for handle in crop.HANDLES:
            for point in ((0.0, 0.0), (1.0, 1.0), (0.5, 0.5)):
                result = crop.resize(self.RECT, handle, point)
                self.assertGreaterEqual(result[2], 0)
                self.assertGreaterEqual(result[3], 0)


class FromCentreTests(unittest.TestCase):
    RECT = (0.3, 0.3, 0.2, 0.2)

    def _centre(self, rect):
        return (rect[0] + rect[2] / 2, rect[1] + rect[3] / 2)

    def test_the_centre_stays_put(self):
        before = self._centre(self.RECT)
        result = crop.resize(self.RECT, "se", (0.7, 0.65), from_center=True)
        after = self._centre(result)
        self.assertAlmostEqual(before[0], after[0], places=6)
        self.assertAlmostEqual(before[1], after[1], places=6)

    def test_growing_from_the_centre_grows_both_sides(self):
        result = crop.resize(self.RECT, "se", (0.6, 0.6), from_center=True)
        self.assertGreater(result[2], self.RECT[2])
        self.assertLess(result[0], self.RECT[0])

    def test_it_stays_inside_the_image(self):
        result = crop.resize(self.RECT, "se", (1.0, 1.0), from_center=True)
        self.assertTrue(inside_unit(result))

    def test_an_edge_handle_from_the_centre_touches_one_axis(self):
        result = crop.resize(self.RECT, "e", (0.6, 0.9), from_center=True)
        self.assertAlmostEqual(result[3], self.RECT[3])


class MoveTests(unittest.TestCase):
    def test_moving_keeps_the_size(self):
        result = crop.move((0.1, 0.1, 0.3, 0.4), 0.2, 0.1)
        self.assertAlmostEqual(result[2], 0.3)
        self.assertAlmostEqual(result[3], 0.4)
        self.assertAlmostEqual(result[0], 0.3)

    def test_moving_stops_at_the_edge(self):
        result = crop.move((0.5, 0.5, 0.5, 0.5), 1.0, 1.0)
        self.assertAlmostEqual(result[0], 0.5)
        self.assertTrue(inside_unit(result))

    def test_moving_a_full_width_rect_is_a_no_op_horizontally(self):
        result = crop.move((0.0, 0.2, 1.0, 0.5), 0.3, 0.0)
        self.assertAlmostEqual(result[0], 0.0)


class PixelTests(unittest.TestCase):
    def test_to_pixels(self):
        self.assertEqual(crop.to_pixels((0.25, 0.25, 0.5, 0.5), (800, 600)),
                         (200, 150, 400, 300))

    def test_a_full_rect_covers_the_whole_image(self):
        self.assertEqual(crop.to_pixels(crop.UNIT, (640, 480)), (0, 0, 640, 480))

    def test_pixels_never_leave_the_image(self):
        x, y, w, h = crop.to_pixels((0.9, 0.9, 0.5, 0.5), (100, 100))
        self.assertLessEqual(x + w, 100)
        self.assertLessEqual(y + h, 100)

    def test_a_vanishing_rect_still_has_a_pixel(self):
        _x, _y, w, h = crop.to_pixels((0.5, 0.5, 0.0, 0.0), (100, 100))
        self.assertEqual((w, h), (1, 1))

    def test_pixel_round_trip(self):
        rect = crop.from_pixels((100, 50, 200, 150), (400, 300))
        self.assertEqual(crop.to_pixels(rect, (400, 300)), (100, 50, 200, 150))


class ComposeTests(unittest.TestCase):
    """Crops stack, so the stored rect stays anchored to the pristine image."""

    def test_cropping_a_crop(self):
        result = crop.compose((0.1, 0.1, 0.5, 0.5), (0.0, 0.0, 0.5, 0.5))
        self.assertEqual(result, (0.1, 0.1, 0.25, 0.25))

    def test_composing_with_the_whole_image_changes_nothing(self):
        rect = (0.2, 0.3, 0.4, 0.5)
        self.assertEqual(crop.compose(crop.UNIT, rect), rect)
        self.assertEqual(crop.compose(rect, crop.UNIT), rect)

    def test_a_composed_crop_stays_inside(self):
        result = crop.compose((0.5, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5))
        self.assertTrue(inside_unit(result))


class HandleTests(unittest.TestCase):
    def test_handle_positions(self):
        rect = (0.0, 0.0, 1.0, 1.0)
        self.assertEqual(crop.handle_point(rect, "nw"), (0.0, 0.0))
        self.assertEqual(crop.handle_point(rect, "se"), (1.0, 1.0))
        self.assertEqual(crop.handle_point(rect, "n"), (0.5, 0.0))

    def test_corners_are_corners(self):
        self.assertTrue(all(crop.is_corner(c) for c in crop.CORNERS))
        self.assertFalse(any(crop.is_corner(e) for e in ("n", "e", "s", "w")))

    def test_contains(self):
        rect = (0.2, 0.2, 0.4, 0.4)
        self.assertTrue(crop.contains(rect, (0.4, 0.4)))
        self.assertFalse(crop.contains(rect, (0.1, 0.4)))


if __name__ == "__main__":
    unittest.main()
