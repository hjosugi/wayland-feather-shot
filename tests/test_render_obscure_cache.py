"""Blurred regions are remembered per base image, so edits after a blur stay cheap.

Run:  python3 tests/test_render_obscure_cache.py
"""

import gc
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    from wayland_feather_shot.editor import render
    HAVE_GI = True
except (ImportError, ValueError):
    HAVE_GI = False


@unittest.skipUnless(HAVE_GI, "PyGObject unavailable")
class ObscureCacheTests(unittest.TestCase):
    def base(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 200, 150)
        pixbuf.fill(0x3366aaff)
        return pixbuf

    def test_the_same_region_of_the_same_image_is_computed_once(self):
        base = self.base()
        first = render._obscured_pixbuf(base, 20, 20, 80, 60, 0.55, False)
        again = render._obscured_pixbuf(base, 20, 20, 80, 60, 0.55, False)
        self.assertIs(first, again)
        other = render._obscured_pixbuf(base, 30, 20, 80, 60, 0.55, False)
        self.assertIsNot(first, other)
        pixelated = render._obscured_pixbuf(base, 20, 20, 80, 60, 0.55, True)
        self.assertIsNot(first, pixelated)

    def test_a_different_image_gets_its_own_entries(self):
        first = render._obscured_pixbuf(self.base(), 20, 20, 80, 60, 0.55, False)
        second = render._obscured_pixbuf(self.base(), 20, 20, 80, 60, 0.55, False)
        self.assertIsNot(first, second)

    def test_entries_die_with_their_image(self):
        base = self.base()
        render._obscured_pixbuf(base, 20, 20, 80, 60, 0.55, False)
        self.assertIn(base, render._obscure_cache)
        del base
        gc.collect()
        self.assertEqual(len(render._obscure_cache), 0)

    def test_a_live_drag_cannot_grow_the_cache_past_its_byte_budget(self):
        # A pixelate dragged out is drawn every frame, each frame a new and
        # region-sized entry; a 4K drag once held about a gigabyte.
        base = self.base()
        kept = render._obscured_pixbuf(base, 0, 0, 100, 100, 0.55, True)
        size = kept.get_byte_length()
        budget, render._OBSCURE_CACHE_BYTES = render._OBSCURE_CACHE_BYTES, 3 * size
        self.addCleanup(setattr, render, "_OBSCURE_CACHE_BYTES", budget)
        for frame in range(1, 20):
            render._obscured_pixbuf(base, frame, 0, 100, 100, 0.55, True)
            # The region in use stays cached however many frames go by.
            self.assertIs(render._obscured_pixbuf(base, 0, 0, 100, 100, 0.55, True),
                          kept)
        entries = render._obscure_cache[base]
        self.assertLessEqual(sum(p.get_byte_length() for p in entries.values()),
                             3 * size)


if __name__ == "__main__":
    unittest.main()
