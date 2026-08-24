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

    def test_a_redaction_actually_changes_the_pixels(self):
        base = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 120, 60)
        base.fill(0x000000ff)
        style = S.Style(font_size=28.0, rgba=(1, 1, 1, 1))
        with_text = render.flatten(base, [S.Text((4, 4), "SECRET", style)])
        redacted = render.flatten(
            with_text, [S.Obscure((0, 0, 120, 60), density=1.0)])
        self.assertNotEqual(bytes(with_text.get_pixels()),
                            bytes(redacted.get_pixels()))


if __name__ == "__main__":
    unittest.main()
