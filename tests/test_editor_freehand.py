"""Unit tests for the freehand stroke pipeline (GTK-free).

Run:  python3 tests/test_editor_freehand.py
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.editor import freehand as F  # noqa: E402

SIZE = 12.0


def horizontal(step: float, count: int = 40, y: float = 0.0):
    """A straight run sampled every *step* units — a stand-in for speed."""
    return [(i * step, y) for i in range(count)]


def bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


class StrokePointTests(unittest.TestCase):
    def test_no_input_makes_no_points(self):
        self.assertEqual(F.get_stroke_points([], F.StrokeOptions()), [])

    def test_running_length_only_grows(self):
        points = F.get_stroke_points(horizontal(5), F.StrokeOptions(size=SIZE))
        lengths = [p.running_length for p in points]
        self.assertEqual(lengths, sorted(lengths))
        self.assertEqual(lengths[0], 0.0)

    def test_vectors_are_unit_length(self):
        points = F.get_stroke_points(horizontal(5), F.StrokeOptions(size=SIZE))
        for p in points[1:]:
            self.assertAlmostEqual(math.hypot(*p.vector), 1.0, places=6)

    def test_the_first_point_borrows_the_second_direction(self):
        points = F.get_stroke_points(horizontal(5), F.StrokeOptions(size=SIZE))
        self.assertEqual(points[0].vector, points[1].vector)

    def test_a_finished_stroke_ends_where_the_pointer_did(self):
        raw = horizontal(9)
        points = F.get_stroke_points(raw, F.StrokeOptions(size=SIZE, last=True))
        self.assertAlmostEqual(points[-1].point[0], raw[-1][0])

    def test_repeated_samples_are_dropped(self):
        raw = [(0.0, 0.0)] * 5 + [(50.0, 0.0)]
        points = F.get_stroke_points(raw, F.StrokeOptions(size=SIZE))
        self.assertLess(len(points), len(raw))

    def test_a_single_sample_still_has_a_direction(self):
        points = F.get_stroke_points([(4.0, 4.0)], F.StrokeOptions(size=SIZE))
        self.assertTrue(points)
        self.assertAlmostEqual(math.hypot(*points[-1].vector), 1.0, places=6)


class StreamlineTests(unittest.TestCase):
    def _jittery(self):
        return [(i * 6.0, (5.0 if i % 2 else -5.0)) for i in range(30)]

    def _deviation(self, points):
        """Mean distance off the axis, over the interior points.

        The first and last points are deliberately left exactly where the
        pointer was — a finished stroke has to end where the user let go — so
        they say nothing about smoothing.  And heavy smoothing *lags*, which
        can leave a single early point further out; the mean is what actually
        describes how jittery the line is.
        """
        interior = points[1:-1] or points
        return sum(abs(p[1]) for p in interior) / len(interior)

    def test_streamlining_pulls_jitter_towards_the_line(self):
        raw = self._jittery()
        smoothed = F.centerline(raw, F.StrokeOptions(size=SIZE, streamline=0.9))
        self.assertLess(self._deviation(smoothed), self._deviation(raw))

    def test_more_streamline_smooths_more(self):
        raw = self._jittery()
        light = F.centerline(raw, F.StrokeOptions(size=SIZE, streamline=0.2))
        heavy = F.centerline(raw, F.StrokeOptions(size=SIZE, streamline=0.95))
        self.assertLess(self._deviation(heavy), self._deviation(light))

    def test_the_endpoints_are_left_exactly_where_the_pointer_was(self):
        raw = self._jittery()
        line = F.centerline(raw, F.StrokeOptions(size=SIZE, streamline=0.95))
        self.assertAlmostEqual(line[0][1], raw[0][1])
        self.assertAlmostEqual(line[-1][1], raw[-1][1])

    def test_zero_streamline_keeps_the_input(self):
        raw = horizontal(7)
        line = F.centerline(raw, F.StrokeOptions(size=SIZE, streamline=0.0))
        for a, b in zip(raw, line):
            self.assertAlmostEqual(a[0], b[0], places=6)


class RadiusTests(unittest.TestCase):
    """The point of the whole exercise: speed has to show up as width."""

    def test_a_fast_stroke_is_thinner_than_a_slow_one(self):
        options = F.StrokeOptions(size=SIZE)
        slow = F.stroke_radii(horizontal(2), options)
        fast = F.stroke_radii(horizontal(40), options)
        self.assertLess(sum(fast) / len(fast), sum(slow) / len(slow))

    def test_a_stroke_thins_as_it_speeds_up(self):
        # Slow for the first half, fast for the second.
        raw = [(i * 2.0, 0.0) for i in range(30)]
        raw += [(raw[-1][0] + i * 40.0, 0.0) for i in range(1, 30)]
        radii = F.stroke_radii(raw, F.StrokeOptions(size=SIZE))
        first_half = radii[:len(radii) // 2]
        second_half = radii[len(radii) // 2:]
        self.assertLess(sum(second_half) / len(second_half),
                        sum(first_half) / len(first_half))

    def test_no_thinning_gives_a_constant_width(self):
        radii = F.stroke_radii(horizontal(20),
                               F.StrokeOptions(size=SIZE, thinning=0.0))
        self.assertEqual(len(set(round(r, 9) for r in radii)), 1)
        self.assertAlmostEqual(radii[0], SIZE / 2)

    def test_radii_never_exceed_the_stroke_size(self):
        for step in (1, 5, 20, 100):
            for radius in F.stroke_radii(horizontal(step),
                                         F.StrokeOptions(size=SIZE)):
                self.assertLessEqual(radius, SIZE)
                self.assertGreater(radius, 0)

    def test_an_end_taper_thins_the_end(self):
        options = F.StrokeOptions(size=SIZE, taper_end=40.0)
        radii = F.stroke_radii(horizontal(5, count=60), options)
        self.assertLess(radii[-1], radii[len(radii) // 2])

    def test_a_short_stroke_keeps_one_width(self):
        radii = F.stroke_radii([(0.0, 0.0), (2.0, 0.0)],
                               F.StrokeOptions(size=SIZE))
        self.assertEqual(len(set(round(r, 9) for r in radii)), 1)


class OutlineTests(unittest.TestCase):
    def test_no_input_makes_no_outline(self):
        self.assertEqual(F.get_stroke([]), [])

    def test_an_outline_is_a_fillable_polygon(self):
        outline = F.get_stroke(horizontal(5), F.StrokeOptions(size=SIZE))
        self.assertGreater(len(outline), 3)

    def test_a_dot_comes_out_round(self):
        outline = F.get_stroke([(10.0, 10.0)], F.StrokeOptions(size=SIZE))
        _x, _y, w, h = bbox(outline)
        self.assertAlmostEqual(w, h, delta=w * 0.15)
        self.assertGreater(w, SIZE / 2)

    def test_identical_samples_still_draw_something(self):
        outline = F.get_stroke([(5.0, 5.0)] * 8, F.StrokeOptions(size=SIZE))
        self.assertGreater(len(outline), 3)

    def test_the_outline_covers_the_input(self):
        raw = horizontal(6, count=30)
        outline = F.get_stroke(raw, F.StrokeOptions(size=SIZE))
        ox, oy, ow, oh = bbox(outline)
        rx, ry, rw, rh = bbox(raw)
        self.assertLessEqual(ox, rx + 1)
        self.assertGreaterEqual(ox + ow, rx + rw - 1)
        # ...and is at least as thick as the stroke is wide, minus the taper.
        self.assertGreater(oh, SIZE / 2)

    def test_a_wider_stroke_makes_a_thicker_outline(self):
        raw = horizontal(4, count=30)
        thin = bbox(F.get_stroke(raw, F.StrokeOptions(size=6.0)))[3]
        thick = bbox(F.get_stroke(raw, F.StrokeOptions(size=24.0)))[3]
        self.assertGreater(thick, thin * 2)

    def test_a_hairpin_does_not_collapse(self):
        # Out and straight back: the outline has to travel around the turn.
        raw = [(i * 5.0, 0.0) for i in range(20)]
        raw += [(raw[-1][0] - i * 5.0, 1.0) for i in range(1, 20)]
        outline = F.get_stroke(raw, F.StrokeOptions(size=SIZE))
        self.assertGreater(len(outline), 20)
        self.assertGreater(bbox(outline)[3], SIZE / 2)

    def test_every_outline_point_is_finite(self):
        raw = [(math.sin(i / 3) * 40, math.cos(i / 5) * 40) for i in range(60)]
        for x, y in F.get_stroke(raw, F.StrokeOptions(size=SIZE)):
            self.assertTrue(math.isfinite(x) and math.isfinite(y))


class OptionsTests(unittest.TestCase):
    def test_streamline_rises_with_the_stroke_width(self):
        self.assertLess(F.options_for(2.0).streamline,
                        F.options_for(30.0).streamline)

    def test_streamline_stays_in_range(self):
        for width in (0.5, 4, 9, 16, 40, 400):
            self.assertTrue(0.6 <= F.options_for(width).streamline <= 0.75)

    def test_the_size_is_the_authored_width(self):
        self.assertEqual(F.options_for(7.5).size, 7.5)

    def test_an_unfinished_stroke_is_marked_as_such(self):
        self.assertFalse(F.options_for(4.0, complete=False).last)


if __name__ == "__main__":
    unittest.main()
