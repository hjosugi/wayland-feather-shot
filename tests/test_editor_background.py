"""Unit tests for the background stage layout (GTK-free).

Run:  python3 tests/test_editor_background.py
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.editor import background as B  # noqa: E402

CONTENT = (800.0, 600.0)


def enabled(**kwargs):
    kwargs.setdefault("fill", "solid")
    return B.BackgroundSettings(**kwargs)


class DisabledTests(unittest.TestCase):
    """With no stage the canvas *is* the screenshot, so every drawing path can
    treat the two the same way instead of branching."""

    def test_the_canvas_is_the_screenshot(self):
        layout = B.layout(CONTENT, B.BackgroundSettings())
        self.assertEqual(layout.canvas, CONTENT)
        self.assertEqual(layout.card, (0.0, 0.0, 800.0, 600.0))

    def test_no_padding_no_radius_no_border(self):
        layout = B.layout(CONTENT, B.BackgroundSettings())
        self.assertEqual(layout.corner_radius, 0.0)
        self.assertEqual(layout.border_width, 0.0)

    def test_a_watermark_alone_still_makes_a_stage(self):
        settings = B.BackgroundSettings(
            watermark=B.Watermark(enabled=True, text="draft"))
        self.assertTrue(settings.enabled)

    def test_a_border_alone_still_makes_a_stage(self):
        self.assertTrue(
            B.BackgroundSettings(border=B.Border(enabled=True)).enabled)

    def test_an_empty_watermark_is_not_visible(self):
        self.assertFalse(B.Watermark(enabled=True, text="  ").visible)
        self.assertFalse(B.Watermark(enabled=False, text="x").visible)


class PaddingTests(unittest.TestCase):
    def test_padding_grows_the_canvas_evenly(self):
        layout = B.layout(CONTENT, enabled(padding=0.1))
        self.assertAlmostEqual(layout.canvas[0], 800 + 160)
        self.assertAlmostEqual(layout.canvas[1], 600 + 160)
        self.assertAlmostEqual(layout.card[0], 80)
        self.assertAlmostEqual(layout.card[1], 80)

    def test_padding_is_a_fraction_of_the_longer_edge(self):
        # The same setting has to look the same at any capture resolution.
        small = B.layout((800.0, 600.0), enabled(padding=0.1))
        large = B.layout((1600.0, 1200.0), enabled(padding=0.1))
        self.assertAlmostEqual(small.canvas[0] / 800, large.canvas[0] / 1600)

    def test_zero_padding_leaves_the_card_flush(self):
        layout = B.layout(CONTENT, enabled(padding=0.0))
        self.assertEqual(layout.canvas, CONTENT)

    def test_the_card_keeps_the_screenshot_size(self):
        layout = B.layout(CONTENT, enabled(padding=0.2))
        self.assertEqual((layout.card[2], layout.card[3]), CONTENT)


class RadiusTests(unittest.TestCase):
    def test_the_radius_follows_the_shorter_edge(self):
        layout = B.layout(CONTENT, enabled(corner_radius=0.05))
        self.assertAlmostEqual(layout.corner_radius, 30.0)

    def test_a_rounded_path_has_arcs(self):
        path = B.rounded_rect_path((0, 0, 100, 80), 10)
        self.assertTrue(any(command == "arc" for command, _ in path))

    def test_a_zero_radius_is_a_plain_rectangle(self):
        self.assertEqual(B.rounded_rect_path((0, 0, 100, 80), 0),
                         [("rect", (0, 0, 100, 80))])

    def test_the_radius_cannot_exceed_half_the_box(self):
        path = B.rounded_rect_path((0, 0, 20, 10), 500)
        radii = [args[2] for command, args in path if command == "arc"]
        self.assertTrue(all(r <= 5 for r in radii))


class AspectTests(unittest.TestCase):
    def test_auto_keeps_whatever_padding_produced(self):
        layout = B.layout(CONTENT, enabled(padding=0.1, aspect="auto"))
        self.assertAlmostEqual(layout.canvas[0] / layout.canvas[1],
                               960 / 760)

    def test_every_preset_produces_its_ratio(self):
        for name, ratio in B.ASPECT_RATIOS.items():
            layout = B.layout(CONTENT, enabled(padding=0.05, aspect=name))
            self.assertAlmostEqual(layout.canvas[0] / layout.canvas[1], ratio,
                                   places=6, msg=name)

    def test_the_aspect_never_crops_the_card(self):
        for name in B.ASPECT_RATIOS:
            layout = B.layout(CONTENT, enabled(padding=0.02, aspect=name))
            self.assertGreaterEqual(layout.canvas[0], layout.card[2], name)
            self.assertGreaterEqual(layout.canvas[1], layout.card[3], name)

    def test_an_unknown_aspect_is_treated_as_auto(self):
        known = B.layout(CONTENT, enabled(aspect="auto"))
        unknown = B.layout(CONTENT, enabled(aspect="21:9"))
        self.assertEqual(known.canvas, unknown.canvas)


class AlignmentTests(unittest.TestCase):
    def _card(self, alignment):
        return B.layout(CONTENT, enabled(padding=0.05, aspect="16:9",
                                         alignment=alignment)).card

    def test_centre_is_the_default(self):
        layout = B.layout(CONTENT, enabled(padding=0.05, aspect="16:9"))
        free = layout.canvas[0] - layout.card[2]
        self.assertAlmostEqual(layout.card[0], free / 2)

    def test_left_and_right_sit_at_the_edges(self):
        left = self._card("left")
        right = self._card("right")
        self.assertLess(left[0], right[0])
        self.assertAlmostEqual(left[0], 0.0)

    def test_top_and_bottom_sit_at_the_edges(self):
        self.assertLessEqual(self._card("top")[1], self._card("bottom")[1])

    def test_corners_move_both_axes(self):
        top_left = self._card("top-left")
        bottom_right = self._card("bottom-right")
        self.assertLess(top_left[0], bottom_right[0])
        self.assertLess(top_left[1], bottom_right[1])

    def test_every_alignment_keeps_the_card_inside(self):
        for alignment in B.ALIGNMENTS:
            x, y, w, h = self._card(alignment)
            layout = B.layout(CONTENT, enabled(padding=0.05, aspect="16:9",
                                               alignment=alignment))
            self.assertGreaterEqual(x, -0.001, alignment)
            self.assertLessEqual(x + w, layout.canvas[0] + 0.001, alignment)
            self.assertGreaterEqual(y, -0.001, alignment)
            self.assertLessEqual(y + h, layout.canvas[1] + 0.001, alignment)


class BorderTests(unittest.TestCase):
    def test_the_border_grows_the_canvas(self):
        without = B.layout(CONTENT, enabled(padding=0.0))
        with_border = B.layout(CONTENT, enabled(padding=0.0,
                                                border=B.Border(True)))
        self.assertGreater(with_border.canvas[0], without.canvas[0])

    def test_the_border_thickness_follows_the_shorter_edge(self):
        border = B.Border(enabled=True, thickness=0.01)
        self.assertAlmostEqual(border.pixels(CONTENT), 6.0)

    def test_a_disabled_border_takes_no_room(self):
        self.assertEqual(B.Border(enabled=False).pixels(CONTENT), 0.0)

    def test_the_card_is_inset_by_the_border(self):
        layout = B.layout(CONTENT, enabled(padding=0.0, border=B.Border(True)))
        self.assertAlmostEqual(layout.card[0], layout.border_width)


class ShadowTests(unittest.TestCase):
    def test_no_shadow_at_zero_strength(self):
        self.assertIsNone(B.shadow_layer(0.0, 600))

    def test_the_radius_grows_with_the_strength(self):
        weak = B.shadow_layer(0.2, 600)
        strong = B.shadow_layer(0.9, 600)
        self.assertGreater(strong.radius, weak.radius)

    def test_opacity_saturates_rather_than_tracking_the_slider(self):
        # What keeps a large shadow soft instead of a black smear.
        mid = B.shadow_layer(0.4, 600)
        full = B.shadow_layer(1.0, 600)
        self.assertLessEqual(full.alpha, 0.5)
        self.assertLess(full.alpha / mid.alpha, full.radius / mid.radius)

    def test_the_styles_differ_in_the_ways_they_are_named_for(self):
        soft = B.shadow_layer(0.5, 600, "soft")
        long_ = B.shadow_layer(0.5, 600, "long")
        glow = B.shadow_layer(0.5, 600, "glow")
        crisp = B.shadow_layer(0.5, 600, "crisp")
        self.assertGreater(long_.offset_y, soft.offset_y)
        self.assertEqual(glow.offset_y, 0.0)
        self.assertGreater(glow.radius, soft.radius)
        self.assertLess(crisp.radius, soft.radius)

    def test_an_unknown_style_behaves_like_soft(self):
        self.assertEqual(B.shadow_layer(0.5, 600, "velvet"),
                         B.shadow_layer(0.5, 600, "soft"))

    def test_it_scales_with_the_card(self):
        small = B.shadow_layer(0.5, 300)
        large = B.shadow_layer(0.5, 1200)
        self.assertAlmostEqual(large.radius / small.radius, 4.0)


class WatermarkTests(unittest.TestCase):
    CANVAS = (1000.0, 800.0)

    def test_no_marks_when_it_is_off(self):
        self.assertEqual(B.watermark_positions(self.CANVAS, B.Watermark()), [])

    def test_a_single_mark_sits_in_the_corner(self):
        marks = B.watermark_positions(self.CANVAS,
                                      B.Watermark(True, "x", density=0))
        self.assertEqual(len(marks), 1)
        self.assertGreater(marks[0][0], self.CANVAS[0] * 0.8)
        self.assertGreater(marks[0][1], self.CANVAS[1] * 0.8)

    def test_density_tiles_it(self):
        marks = B.watermark_positions(self.CANVAS,
                                      B.Watermark(True, "x", density=3))
        self.assertGreater(len(marks), 3)

    def test_more_density_means_more_marks(self):
        few = B.watermark_positions(self.CANVAS, B.Watermark(True, "x", density=2))
        many = B.watermark_positions(self.CANVAS, B.Watermark(True, "x", density=5))
        self.assertGreater(len(many), len(few))

    def test_every_mark_lands_on_the_canvas(self):
        for x, y in B.watermark_positions(self.CANVAS,
                                          B.Watermark(True, "x", density=4)):
            self.assertTrue(0 <= x <= self.CANVAS[0])
            self.assertTrue(0 <= y <= self.CANVAS[1])

    def test_a_degenerate_canvas_produces_nothing(self):
        self.assertEqual(
            B.watermark_positions((0.0, 0.0), B.Watermark(True, "x")), [])


class GradientTests(unittest.TestCase):
    def test_every_preset_has_two_colours(self):
        for name in B.GRADIENT_PRESETS:
            start, end = B.gradient_colors(name)
            self.assertEqual(len(start), 4)
            self.assertEqual(len(end), 4)

    def test_an_unknown_preset_falls_back(self):
        self.assertEqual(B.gradient_colors("chartreuse"),
                         B.gradient_colors("dusk"))


if __name__ == "__main__":
    unittest.main()
