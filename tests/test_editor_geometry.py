"""Unit tests for the editor's geometry primitives (GTK-free).

Run:  python3 tests/test_editor_geometry.py
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.editor.geometry import (  # noqa: E402
    Box, Circle2d, Ellipse2d, Group2d, Polygon2d, Polyline2d, Rect2d,
    dist_to_segment, norm_rect, point_in_polygon, rotate, segments_intersect)


class RotateTests(unittest.TestCase):
    def test_quarter_turn_about_the_origin(self):
        x, y = rotate((10, 0), math.pi / 2)
        self.assertAlmostEqual(x, 0)
        self.assertAlmostEqual(y, 10)

    def test_rotation_about_a_center_keeps_the_center_fixed(self):
        self.assertEqual(rotate((5, 5), 1.234, (5, 5)), (5, 5))

    def test_zero_rotation_is_identity(self):
        self.assertEqual(rotate((3, 4), 0.0), (3, 4))


class SegmentTests(unittest.TestCase):
    def test_distance_to_segment_clamps_to_the_endpoints(self):
        self.assertAlmostEqual(dist_to_segment((-5, 0), (0, 0), (10, 0)), 5)
        self.assertAlmostEqual(dist_to_segment((5, 3), (0, 0), (10, 0)), 3)

    def test_crossing_segments(self):
        self.assertTrue(segments_intersect((0, 0), (10, 10), (0, 10), (10, 0)))
        self.assertFalse(segments_intersect((0, 0), (1, 1), (5, 5), (6, 6)))


class BoxTests(unittest.TestCase):
    def test_from_points(self):
        self.assertEqual(Box.from_points([(3, 9), (-1, 2)]), Box(-1, 2, 4, 7))

    def test_union(self):
        self.assertEqual(Box.union([Box(0, 0, 5, 5), Box(10, 10, 1, 1)]),
                         Box(0, 0, 11, 11))

    def test_norm_rect_orders_the_corners(self):
        self.assertEqual(norm_rect(10, 20, 0, 5), (0, 5, 10, 15))


class HitTestTests(unittest.TestCase):
    """The regression this layer exists for: a bounding box is not a shape."""

    def test_hollow_rectangle_is_only_grabbed_by_its_outline(self):
        rect = Rect2d(100, 50)
        self.assertTrue(rect.hit_test((0, 25), margin=3))
        self.assertFalse(rect.hit_test((50, 25), margin=3))

    def test_filled_rectangle_is_grabbed_anywhere_inside(self):
        rect = Rect2d(100, 50, filled=True)
        self.assertTrue(rect.hit_test((50, 25), margin=3, hit_inside=True))

    def test_diagonal_line_ignores_the_empty_corners_of_its_bbox(self):
        line = Polyline2d([(0, 0), (100, 100)])
        self.assertTrue(line.hit_test((50, 50), margin=4))
        # Inside the bounding box, nowhere near the line.
        self.assertFalse(line.hit_test((95, 5), margin=4))

    def test_ellipse_interior_is_not_its_outline(self):
        ellipse = Ellipse2d(100, 50)
        self.assertTrue(ellipse.hit_test((0, 25), margin=3))
        self.assertFalse(ellipse.hit_test((50, 25), margin=3))
        self.assertTrue(ellipse.hit_test((50, 25), margin=3, hit_inside=True))

    def test_ellipse_corner_of_the_bbox_is_outside(self):
        ellipse = Ellipse2d(100, 100, filled=True)
        self.assertFalse(ellipse.hit_test((2, 2), margin=2, hit_inside=True))

    def test_circle(self):
        circle = Circle2d(40, filled=True)
        self.assertTrue(circle.hit_test((20, 20), margin=1, hit_inside=True))
        self.assertFalse(circle.hit_test((-5, -5), margin=1, hit_inside=True))

    def test_group_hits_any_part(self):
        group = Group2d([Rect2d(10, 10), Polyline2d([(100, 0), (200, 0)])])
        self.assertTrue(group.hit_test((150, 0), margin=2))
        self.assertTrue(group.hit_test((0, 5), margin=2))
        self.assertFalse(group.hit_test((60, 60), margin=2))


class MarqueeTests(unittest.TestCase):
    def test_overlap_requires_actual_contact(self):
        line = Polyline2d([(0, 0), (100, 100)])
        self.assertTrue(line.overlaps_polygon(Box(40, 40, 20, 20).corners))
        # Inside the line's bbox but away from the line itself.
        self.assertFalse(line.overlaps_polygon(Box(80, 5, 10, 10).corners))
        self.assertFalse(line.overlaps_polygon(Box(200, 200, 10, 10).corners))

    def test_a_marquee_that_swallows_the_shape_selects_it(self):
        rect = Rect2d(50, 50)
        self.assertTrue(rect.overlaps_polygon(Box(-10, -10, 100, 100).corners))

    def test_a_marquee_inside_a_hollow_shape_still_selects_it(self):
        rect = Rect2d(200, 200)
        self.assertTrue(rect.overlaps_polygon(Box(50, 50, 20, 20).corners))


class PolygonTests(unittest.TestCase):
    def test_point_in_polygon(self):
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]
        self.assertTrue(point_in_polygon((5, 5), square))
        self.assertFalse(point_in_polygon((15, 5), square))

    def test_degenerate_polygon_contains_nothing(self):
        self.assertFalse(point_in_polygon((0, 0), [(0, 0), (1, 1)]))

    def test_polygon_bounds(self):
        poly = Polygon2d([(0, 0), (10, 0), (5, 8)])
        self.assertEqual(poly.bounds, Box(0, 0, 10, 8))


if __name__ == "__main__":
    unittest.main()
