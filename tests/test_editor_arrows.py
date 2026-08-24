"""Unit tests for arrow geometry — heads, curvature, shaft (GTK-free).

Run:  python3 tests/test_editor_arrows.py
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.editor import arrows as A  # noqa: E402

WIDTH = 5.0
START = (0.0, 0.0)
END = (100.0, 0.0)


def path_length(points):
    return sum(math.dist(points[i], points[i + 1])
               for i in range(len(points) - 1))


class HeadTests(unittest.TestCase):
    def test_every_style_has_a_title(self):
        for name in A.HEADS:
            self.assertIn(name, A.HEAD_TITLES)

    def test_none_takes_no_room(self):
        self.assertEqual(A.head_size("none", WIDTH), 0.0)
        self.assertEqual(A.head_length("none", WIDTH), 0.0)
        self.assertEqual(A.head_path("none", END, 0.0, WIDTH)[1], [])

    def test_every_other_style_draws_something(self):
        for name in A.HEADS:
            if name == "none":
                continue
            kind, points = A.head_path(name, END, 0.0, WIDTH)
            self.assertIn(kind, ("fill", "outline", "stroke"), name)
            self.assertGreaterEqual(len(points), 2, name)
            self.assertGreater(A.head_length(name, WIDTH), 0, name)

    def test_heads_grow_with_the_stroke(self):
        for name in A.HEADS:
            if name == "none":
                continue
            self.assertGreater(A.head_size(name, 20.0),
                               A.head_size(name, 4.0), name)

    def test_a_head_sits_behind_its_tip(self):
        # Travelling along +x, every point of the head is at or behind the tip.
        for name in A.HEADS:
            if name in ("none", "bar"):
                continue
            _kind, points = A.head_path(name, END, 0.0, WIDTH)
            for x, _y in points:
                self.assertLessEqual(x, END[0] + 0.001, name)

    def test_a_head_follows_the_angle_it_is_given(self):
        _kind, along_x = A.head_path("arrow", (0.0, 0.0), 0.0, WIDTH)
        _kind, along_y = A.head_path("arrow", (0.0, 0.0), math.pi / 2, WIDTH)
        self.assertLess(min(p[0] for p in along_x), -1)
        self.assertLess(min(p[1] for p in along_y), -1)

    def test_head_points_are_finite(self):
        for name in A.HEADS:
            for x, y in A.head_path(name, END, 1.234, WIDTH)[1]:
                self.assertTrue(math.isfinite(x) and math.isfinite(y))


class BendTests(unittest.TestCase):
    def test_a_straight_arrow_has_its_middle_on_the_chord(self):
        self.assertEqual(A.middle_point(START, END, 0.0), (50.0, 0.0))

    def test_bend_and_middle_round_trip(self):
        for bend in (-80.0, -12.5, 5.0, 37.0):
            middle = A.middle_point(START, END, bend)
            self.assertAlmostEqual(A.bend_from_point(START, END, middle), bend)

    def test_bend_mirrors(self):
        up = A.middle_point(START, END, 30.0)
        down = A.middle_point(START, END, -30.0)
        self.assertAlmostEqual(up[0], down[0])
        self.assertAlmostEqual(up[1], -down[1])

    def test_a_degenerate_arrow_has_no_bend(self):
        self.assertEqual(A.bend_from_point(START, START, (5.0, 5.0)), 0.0)
        self.assertEqual(A.middle_point(START, START, 10.0), START)

    def test_small_bends_snap_back_to_straight(self):
        self.assertEqual(A.snap_bend(1.0, WIDTH), 0.0)
        self.assertEqual(A.snap_bend(-3.0, WIDTH), 0.0)
        self.assertEqual(A.snap_bend(40.0, WIDTH), 40.0)

    def test_a_wider_stroke_snaps_over_a_wider_range(self):
        self.assertEqual(A.snap_bend(10.0, 20.0), 0.0)
        self.assertEqual(A.snap_bend(10.0, 2.0), 10.0)


class ArcTests(unittest.TestCase):
    def test_a_straight_arrow_is_not_an_arc(self):
        self.assertIsNone(A.arc(START, END, 0.0))
        self.assertIsNone(A.arc(START, START, 20.0))

    def test_the_arc_passes_through_all_three_points(self):
        for bend in (-60.0, -20.0, 15.0, 90.0):
            centre, radius, _a0, _sweep = A.arc(START, END, bend)
            for point in (START, END, A.middle_point(START, END, bend)):
                self.assertAlmostEqual(math.dist(centre, point), radius,
                                       places=6, msg=f"bend={bend}")

    def test_the_path_starts_and_ends_at_the_terminals(self):
        points = A.path_points(START, END, 40.0)
        self.assertAlmostEqual(points[0][0], START[0], places=6)
        self.assertAlmostEqual(points[0][1], START[1], places=6)
        self.assertAlmostEqual(points[-1][0], END[0], places=6)
        self.assertAlmostEqual(points[-1][1], END[1], places=6)

    def test_the_path_bulges_the_way_the_bend_says(self):
        up = A.path_points(START, END, 40.0)
        down = A.path_points(START, END, -40.0)
        self.assertLess(min(p[1] for p in up), -30)
        self.assertGreater(max(p[1] for p in down), 30)

    def test_a_straight_path_is_two_points(self):
        self.assertEqual(A.path_points(START, END, 0.0), [START, END])

    def test_a_bent_arrow_is_longer_than_its_chord(self):
        self.assertGreater(path_length(A.path_points(START, END, 40.0)),
                           math.dist(START, END))

    def test_a_bigger_bend_is_longer(self):
        self.assertGreater(path_length(A.path_points(START, END, 60.0)),
                           path_length(A.path_points(START, END, 20.0)))


class DirectionTests(unittest.TestCase):
    def test_a_straight_arrow_points_along_its_chord(self):
        self.assertAlmostEqual(A.direction_at(START, END, 0.0), 0.0)
        self.assertAlmostEqual(abs(A.direction_at(START, END, 0.0,
                                                 at_end=False)), math.pi)

    def test_a_bent_arrow_points_along_its_tangent(self):
        # The head has to follow the curve, not the chord it was drawn across.
        angle = A.direction_at(START, END, 40.0)
        self.assertNotAlmostEqual(angle, 0.0, places=2)
        self.assertGreater(angle, 0)  # coming back down towards the end

    def test_the_tangent_is_perpendicular_to_the_radius(self):
        bend = 35.0
        centre, _radius, _a0, _sweep = A.arc(START, END, bend)
        angle = A.direction_at(START, END, bend)
        radial = (END[0] - centre[0], END[1] - centre[1])
        tangent = (math.cos(angle), math.sin(angle))
        self.assertAlmostEqual(radial[0] * tangent[0] + radial[1] * tangent[1],
                               0.0, places=6)

    def test_the_two_ends_point_opposite_ways_on_a_straight_arrow(self):
        forward = A.direction_at(START, END, 0.0)
        backward = A.direction_at(START, END, 0.0, at_end=False)
        self.assertAlmostEqual(abs(forward - backward), math.pi, places=6)


class TrimTests(unittest.TestCase):
    def test_trimming_shortens_by_the_right_amount(self):
        full = path_length(A.path_points(START, END, 0.0))
        trimmed = path_length(A.trimmed(START, END, 0.0, end_trim=20.0))
        self.assertAlmostEqual(trimmed, full - 20.0, places=6)

    def test_trimming_both_ends(self):
        trimmed = A.trimmed(START, END, 0.0, start_trim=10.0, end_trim=20.0)
        self.assertAlmostEqual(trimmed[0][0], 10.0, places=6)
        self.assertAlmostEqual(trimmed[-1][0], 80.0, places=6)

    def test_trimming_nothing_changes_nothing(self):
        self.assertEqual(A.trimmed(START, END, 0.0), [START, END])

    def test_an_over_trimmed_arrow_does_not_vanish(self):
        trimmed = A.trimmed(START, END, 0.0, end_trim=500.0)
        self.assertGreaterEqual(len(trimmed), 2)

    def test_a_bent_shaft_still_follows_the_arc(self):
        # The shaft is a flattened polyline, so a trimmed endpoint sits on a
        # chord and lands marginally inside the circle.  The segment count
        # adapts to the arc's length to keep that under a pixel.
        bend = 40.0
        centre, radius, _a0, _sweep = A.arc(START, END, bend)
        for point in A.trimmed(START, END, bend, start_trim=8.0, end_trim=8.0):
            self.assertAlmostEqual(math.dist(centre, point), radius, delta=0.5)

    def test_flattening_stays_sub_pixel_on_a_big_arc(self):
        start, end = (0.0, 0.0), (4000.0, 0.0)
        bend = 900.0
        centre, radius, _a0, sweep = A.arc(start, end, bend)
        points = A.path_points(start, end, bend)
        # Worst deviation is at a segment's midpoint: the sagitta.
        sagitta = radius * (1 - math.cos(abs(sweep) / len(points) / 2))
        self.assertLess(sagitta, 1.0)
        for point in points:
            self.assertAlmostEqual(math.dist(centre, point), radius, delta=0.01)

    def test_a_small_arc_does_not_pay_for_many_segments(self):
        self.assertLessEqual(len(A.path_points((0.0, 0.0), (20.0, 0.0), 5.0)),
                             A.MIN_ARC_SEGMENTS + 1)


if __name__ == "__main__":
    unittest.main()
