"""Rendering tests for the editor's text stack.

These need PyGObject/Pango, so they skip where the GObject stack is absent
(the CI test job installs no GTK).

Run:  python3 tests/test_editor_text.py
"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import cairo
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    from wayland_feather_shot.editor import render, shapes as S
    HAVE_GTK = True
except Exception:  # pragma: no cover - depends on the host
    HAVE_GTK = False


@unittest.skipUnless(HAVE_GTK, "PyGObject/Pango not available")
class TextRenderingTests(unittest.TestCase):
    """#20: cairo's toy font API renders every non-Latin glyph as the same
    `.notdef` box.  Pango does script itemization and font fallback, so the
    glyphs have to come out distinct."""

    STYLE = None

    def setUp(self):
        self.STYLE = S.Style(font_size=40.0, rgba=(1, 1, 1, 1))

    def _raster(self, text):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 160, 90)
        cr = cairo.Context(surface)
        render.draw_text(cr, text, 5, 5, self.STYLE)
        surface.flush()
        return hashlib.md5(bytes(surface.get_data())).hexdigest()

    def test_japanese_glyphs_are_distinct_from_each_other(self):
        rasters = {self._raster(ch) for ch in "日本語"}
        self.assertEqual(len(rasters), 3, "CJK glyphs collapsed to one bitmap")

    def test_japanese_is_not_the_latin_fallback_box(self):
        self.assertNotEqual(self._raster("日"), self._raster("A"))

    def test_japanese_text_is_not_blank(self):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 90)
        cr = cairo.Context(surface)
        render.draw_text(cr, "日本語", 5, 5, self.STYLE)
        surface.flush()
        self.assertTrue(any(bytes(surface.get_data())), "nothing was drawn")

    def test_cjk_advance_is_full_width(self):
        # Three full-width characters at 40px should measure about 120px; the
        # tofu box was 18px wide, which is what made the bug visible in the
        # first place.
        width, _height = render.measure("日本語", self.STYLE)
        self.assertGreater(width, 100)

    def test_measurement_matches_what_the_model_stores(self):
        shape = S.Text((0, 0), "日本語", self.STYLE)
        width, height = render.measure("日本語", self.STYLE)
        self.assertAlmostEqual(shape.props.w, width)
        self.assertAlmostEqual(shape.props.h, height)

    def test_emoji_render(self):
        self.assertTrue(any(bytes(self._render_surface("✅").get_data())))

    def _render_surface(self, text):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 120, 80)
        cr = cairo.Context(surface)
        render.draw_text(cr, text, 5, 5, self.STYLE)
        surface.flush()
        return surface

    def test_multiline_text_is_taller_than_one_line(self):
        one = render.measure("a", self.STYLE)[1]
        two = render.measure("a\nb", self.STYLE)[1]
        self.assertGreater(two, one * 1.5)


@unittest.skipUnless(HAVE_GTK, "PyGObject/Pango not available")
class RedactionTests(unittest.TestCase):
    """#22: strength is a property of the region, not a global setting."""

    def test_density_drives_the_blur_radius_and_block_size(self):
        self.assertLess(render.blur_radius(0.0), render.blur_radius(1.0))
        self.assertLess(render.pixel_block_size(0.0),
                        render.pixel_block_size(1.0))

    def test_density_is_clamped(self):
        self.assertEqual(render.blur_radius(-5), render.blur_radius(0))
        self.assertEqual(render.blur_radius(5), render.blur_radius(1))

    def _amplitude(self, pixbuf, rect):
        x, y, w, h = rect
        data = pixbuf.get_pixels()
        stride, channels = pixbuf.get_rowstride(), pixbuf.get_n_channels()
        values = [data[(y + j) * stride + (x + i) * channels]
                  for j in range(h) for i in range(w)]
        return max(values) - min(values)

    def test_redacting_text_leaves_nothing_to_read(self):
        """The acceptance criterion from the issue, without needing an OCR
        engine installed: what decides legibility is how much contrast is left
        in the region."""
        base = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 300, 60)
        base.fill(0xFFFFFFFF)
        style = S.Style(rgba=(0.0, 0.0, 0.0, 1.0), font_size=28.0)
        with_text = render.flatten(base, [S.Text((6, 6), "sk_live_9f2c", style)])
        region = (4, 4, 240, 44)
        self.assertGreater(self._amplitude(with_text, region), 200)

        redacted = render.flatten(with_text,
                                  [S.Obscure((0, 0, 300, 60), density=0.9)])
        self.assertLess(self._amplitude(redacted, region), 40)

    def test_a_stronger_density_leaves_less(self):
        base = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 300, 60)
        base.fill(0xFFFFFFFF)
        style = S.Style(rgba=(0.0, 0.0, 0.0, 1.0), font_size=28.0)
        with_text = render.flatten(base, [S.Text((6, 6), "sk_live_9f2c", style)])
        region = (4, 4, 240, 44)
        light = render.flatten(with_text, [S.Obscure((0, 0, 300, 60),
                                                     density=0.1)])
        heavy = render.flatten(with_text, [S.Obscure((0, 0, 300, 60),
                                                     density=1.0)])
        self.assertGreater(self._amplitude(light, region),
                           self._amplitude(heavy, region))

    def test_a_redaction_does_not_smear_its_own_edge_inwards(self):
        """The blur samples a padded rect, so a region on a dark background
        picks up that background rather than fading its own border."""
        base = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 120, 60)
        base.fill(0x000000FF)
        inner = render.flatten(base, [S.Obscure((40, 20, 40, 20), density=0.9)])
        data = inner.get_pixels()
        stride, channels = inner.get_rowstride(), inner.get_n_channels()
        # A uniform background blurs to the same uniform value everywhere.
        self.assertEqual(data[30 * stride + 45 * channels], 0)

    def test_a_redaction_actually_changes_the_pixels(self):
        base = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 120, 60)
        base.fill(0x000000ff)
        style = S.Style(font_size=28.0, rgba=(1, 1, 1, 1))
        with_text = render.flatten(base, [S.Text((4, 4), "SECRET", style)])
        redacted = render.flatten(
            with_text, [S.Obscure((0, 0, 120, 60), density=1.0)])
        self.assertNotEqual(bytes(with_text.get_pixels()),
                            bytes(redacted.get_pixels()))


@unittest.skipUnless(HAVE_GTK, "PyGObject/Pango not available")
class SpotlightRenderingTests(unittest.TestCase):
    """#34: the scrim is a union, not one dim per region."""

    def setUp(self):
        self.base = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8,
                                         200, 100)
        self.base.fill(0xFFFFFFFF)

    def _pixel(self, pixbuf, x, y):
        data = pixbuf.get_pixels()
        offset = y * pixbuf.get_rowstride() + x * pixbuf.get_n_channels()
        return tuple(data[offset:offset + 3])

    def test_outside_a_spotlight_is_dimmed(self):
        out = render.flatten(self.base, [S.Spotlight((50, 20, 60, 60))])
        self.assertLess(self._pixel(out, 5, 5)[0], 200)

    def test_inside_a_spotlight_is_untouched(self):
        out = render.flatten(self.base, [S.Spotlight((50, 20, 60, 60))])
        self.assertEqual(self._pixel(out, 80, 50), (255, 255, 255))

    def test_overlapping_spotlights_do_not_double_darken(self):
        out = render.flatten(self.base, [S.Spotlight((10, 10, 80, 80)),
                                         S.Spotlight((50, 10, 80, 80))])
        # The overlap has to be exactly as bright as either region alone.
        self.assertEqual(self._pixel(out, 60, 50), self._pixel(out, 20, 50))
        self.assertEqual(self._pixel(out, 60, 50), (255, 255, 255))

    def test_a_stronger_scrim_is_darker(self):
        light = render.flatten(self.base, [S.Spotlight((50, 20, 60, 60),
                                                       scrim=0.2)])
        heavy = render.flatten(self.base, [S.Spotlight((50, 20, 60, 60),
                                                       scrim=0.9)])
        self.assertGreater(self._pixel(light, 5, 5)[0],
                           self._pixel(heavy, 5, 5)[0])

    def test_the_strongest_spotlight_sets_the_scrim(self):
        out = render.flatten(self.base, [S.Spotlight((10, 10, 20, 20),
                                                     scrim=0.2),
                                         S.Spotlight((100, 10, 20, 20),
                                                     scrim=0.9)])
        only_light = render.flatten(self.base, [S.Spotlight((10, 10, 20, 20),
                                                            scrim=0.2)])
        self.assertLess(self._pixel(out, 180, 90)[0],
                        self._pixel(only_light, 180, 90)[0])

    def test_annotations_stay_bright_over_a_dimmed_area(self):
        style = S.Style(rgba=(1.0, 0.0, 0.0, 1.0), width=10.0)
        with_spot = render.flatten(
            self.base, [S.Spotlight((150, 10, 40, 40)),
                        S.RectShape((5, 40, 60, 20), style, filled=True)])
        # The rectangle is outside the spotlight but drawn after the scrim, so
        # it keeps its colour rather than being dimmed with the background.
        self.assertEqual(self._pixel(with_spot, 30, 50), (255, 0, 0))

    def test_no_spotlight_means_no_scrim(self):
        out = render.flatten(self.base, [])
        self.assertEqual(self._pixel(out, 5, 5), (255, 255, 255))

    def test_a_zero_scrim_dims_nothing(self):
        out = render.flatten(self.base, [S.Spotlight((50, 20, 60, 60),
                                                     scrim=0.0)])
        self.assertEqual(self._pixel(out, 5, 5), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
