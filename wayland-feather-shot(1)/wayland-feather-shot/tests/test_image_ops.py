"""Unit tests for pure image operations."""

from __future__ import annotations

import unittest

from PIL import Image

from wayland_feather_shot.image_ops import DrawOp, flatten


class ImageOpsTest(unittest.TestCase):
    def test_rectangle_draws_pixels(self):
        base = Image.new("RGBA", (80, 80), "white")
        out = flatten(base, [DrawOp("rect", [(10, 10), (60, 60)], (255, 0, 0, 255), 3)])
        self.assertNotEqual(out.getpixel((10, 10)), (255, 255, 255, 255))

    def test_blur_changes_region(self):
        base = Image.new("RGBA", (80, 80), "white")
        for x in range(30, 50):
            for y in range(30, 50):
                base.putpixel((x, y), (0, 0, 0, 255))
        out = flatten(base, [DrawOp("blur", [(20, 20), (60, 60)], radius=8)])
        self.assertNotEqual(out.getpixel((30, 30)), base.getpixel((30, 30)))


if __name__ == "__main__":
    unittest.main()
