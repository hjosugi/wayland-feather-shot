"""Unit tests for the pure scroll stitcher.

Run from repository root:

    PYTHONPATH=src python3 tests/test_stitcher.py
"""

from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from wayland_feather_shot.scrollcap.stitcher import ScrollStitcher, StitchOptions


def make_tall_image(width: int = 180, height: int = 640) -> Image.Image:
    image = Image.new("RGBA", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for y in range(0, height, 20):
        shade = 220 if (y // 20) % 2 == 0 else 245
        draw.rectangle((0, y, width, y + 19), fill=(shade, shade, shade, 255))
        draw.text((8, y + 3), f"row-{y}", fill=(0, 0, 0, 255))
    return image


class StitcherTest(unittest.TestCase):
    def test_stitches_overlapping_frames(self):
        tall = make_tall_image()
        frame1 = tall.crop((0, 0, 180, 240))
        frame2 = tall.crop((0, 160, 180, 400))
        frame3 = tall.crop((0, 320, 180, 560))
        stitcher = ScrollStitcher(StitchOptions(min_overlap=40, search_step=1, accept_score=1.0))
        output, matches = stitcher.stitch([frame1, frame2, frame3])
        self.assertEqual(len(matches), 2)
        self.assertTrue(all(m.accepted for m in matches))
        self.assertEqual(matches[0].overlap, 80)
        self.assertEqual(matches[1].overlap, 80)
        self.assertEqual(output.size, (180, 560))

    def test_rejects_non_matching_frame(self):
        a = Image.new("RGBA", (100, 120), "white")
        b = Image.new("RGBA", (100, 120), "black")
        stitcher = ScrollStitcher(StitchOptions(min_overlap=20, accept_score=1.0))
        output, matches = stitcher.stitch([a, b])
        self.assertFalse(matches[0].accepted)
        self.assertEqual(output.size, (100, 240))


if __name__ == "__main__":
    unittest.main()
