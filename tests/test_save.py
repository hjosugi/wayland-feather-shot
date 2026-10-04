"""Tests for the pure image-format helpers (no GTK needed).

Run:  python3 tests/test_save.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot import imaging  # noqa: E402


class FormatForPathTests(unittest.TestCase):
    def test_png_default(self):
        self.assertEqual(imaging.format_for_path("a.png", set()),
                         ("png", "a.png", []))

    def test_unknown_extension_becomes_png(self):
        name, path, _ = imaging.format_for_path("a.xyz", {"jpeg"})
        self.assertEqual(name, "png")
        self.assertTrue(path.endswith(".xyz.png"))

    def test_jpeg_when_writable(self):
        name, path, opts = imaging.format_for_path("a.jpg", {"jpeg"})
        self.assertEqual((name, path), ("jpeg", "a.jpg"))
        self.assertIn(("quality", "92"), opts)

    def test_jpeg_falls_back_to_png_when_not_writable(self):
        name, path, _ = imaging.format_for_path("a.jpg", set())
        self.assertEqual(name, "png")
        self.assertTrue(path.endswith("a.jpg.png"))

    def test_webp_and_avif_when_writable(self):
        self.assertEqual(imaging.format_for_path("a.webp", {"webp"})[0], "webp")
        self.assertEqual(imaging.format_for_path("a.avif", {"avif"})[0], "avif")

    def test_webp_unavailable_becomes_png(self):
        self.assertEqual(imaging.format_for_path("a.webp", set())[0], "png")


try:
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf  # noqa: E402
    from wayland_feather_shot import save  # noqa: E402
    HAVE_GI = True
except (ImportError, ValueError):
    HAVE_GI = False


@unittest.skipUnless(HAVE_GI, "PyGObject unavailable")
class PngBytesTests(unittest.TestCase):
    def test_the_clipboard_png_is_quick_and_still_lossless(self):
        # The copy path uses the lightest compression: ten times quicker
        # for a screen-sized image, and the pixels come back unchanged.
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 64, 48)
        pixbuf.fill(0x336699ff)
        for fast in (False, True):
            with self.subTest(fast=fast):
                data = save.pixbuf_to_png_bytes(pixbuf, fast=fast)
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                back = save.pixbuf_from_png_bytes(data)
                self.assertEqual(back.get_pixels(), pixbuf.get_pixels())


if __name__ == "__main__":
    unittest.main(verbosity=2)
