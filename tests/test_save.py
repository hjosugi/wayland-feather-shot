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

    def test_writable_extensions_lists_png_first(self):
        exts = imaging.writable_image_extensions({"jpeg", "webp"})
        self.assertEqual(exts[0], "png")
        self.assertIn("jpg", exts)
        self.assertIn("webp", exts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
