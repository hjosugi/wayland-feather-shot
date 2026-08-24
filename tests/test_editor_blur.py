"""Unit tests for the Gaussian blur kernel (GTK-free).

Run:  python3 tests/test_editor_blur.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.editor import blur  # noqa: E402


def solid(width, height, value=0):
    return bytearray([value] * (width * height * 4))


def with_dot(width, height, x, y, value=255):
    pixels = solid(width, height, 0)
    offset = (y * width + x) * 4
    pixels[offset:offset + 4] = bytes([value, value, value, 255])
    return pixels


def channel(pixels, width, x, y, index=0):
    return pixels[(y * width + x) * 4 + index]


class BoxSizeTests(unittest.TestCase):
    def test_box_sizes_are_odd(self):
        for sigma in (1, 2, 3.5, 10, 40):
            for box in blur.boxes_for_gauss(sigma):
                self.assertEqual(box % 2, 1, f"sigma={sigma} box={box}")

    def test_bigger_sigma_means_bigger_boxes(self):
        self.assertGreater(sum(blur.boxes_for_gauss(10)),
                           sum(blur.boxes_for_gauss(2)))

    def test_the_requested_number_of_passes(self):
        self.assertEqual(len(blur.boxes_for_gauss(4, passes=3)), 3)
        self.assertEqual(len(blur.boxes_for_gauss(4, passes=5)), 5)

    def test_zero_sigma_is_a_no_op_box(self):
        self.assertEqual(blur.boxes_for_gauss(0), [1, 1, 1])


class BlurTests(unittest.TestCase):
    SIZE = 17

    def test_a_flat_image_stays_flat(self):
        pixels = solid(self.SIZE, self.SIZE, 120)
        out = blur.gaussian_blur(pixels, self.SIZE, self.SIZE, 3.0)
        self.assertEqual(set(out), {120})

    def test_a_dot_spreads_into_a_smooth_bump(self):
        centre = self.SIZE // 2
        out = blur.gaussian_blur(with_dot(self.SIZE, self.SIZE, centre, centre),
                                 self.SIZE, self.SIZE, 2.0)
        row = [channel(out, self.SIZE, x, centre) for x in range(self.SIZE)]
        self.assertEqual(row.index(max(row)), centre)
        # Monotonic up to the peak and back down: a bump, not ringing.
        for i in range(centre):
            self.assertLessEqual(row[i], row[i + 1])
        for i in range(centre, self.SIZE - 1):
            self.assertGreaterEqual(row[i], row[i + 1])

    def test_the_bump_is_symmetric(self):
        centre = self.SIZE // 2
        out = blur.gaussian_blur(with_dot(self.SIZE, self.SIZE, centre, centre),
                                 self.SIZE, self.SIZE, 2.0)
        for offset in range(1, centre + 1):
            self.assertEqual(channel(out, self.SIZE, centre - offset, centre),
                             channel(out, self.SIZE, centre + offset, centre))

    def test_it_blurs_both_axes(self):
        centre = self.SIZE // 2
        out = blur.gaussian_blur(with_dot(self.SIZE, self.SIZE, centre, centre),
                                 self.SIZE, self.SIZE, 2.0)
        self.assertGreater(channel(out, self.SIZE, centre, centre - 2), 0)
        self.assertGreater(channel(out, self.SIZE, centre - 2, centre), 0)

    def _lit_width(self, pixels, row):
        """How many pixels of a row carry any light at all."""
        return sum(1 for x in range(self.SIZE)
                   if channel(pixels, self.SIZE, x, row) > 0)

    def test_a_bigger_sigma_spreads_further(self):
        # A block rather than a single pixel: one lit pixel spread thinly
        # quantizes to zero in an integer box blur, which says nothing about
        # how far it reached.
        centre = self.SIZE // 2
        source = solid(self.SIZE, self.SIZE, 0)
        for y in range(centre - 1, centre + 2):
            for x in range(centre - 1, centre + 2):
                offset = (y * self.SIZE + x) * 4
                source[offset:offset + 4] = bytes([255, 255, 255, 255])
        near = blur.gaussian_blur(source, self.SIZE, self.SIZE, 1.0)
        far = blur.gaussian_blur(source, self.SIZE, self.SIZE, 4.0)
        self.assertGreater(self._lit_width(far, centre),
                           self._lit_width(near, centre))

    def test_edges_clamp_rather_than_darken(self):
        # A solid image must not fade towards its own border.
        pixels = solid(9, 9, 200)
        out = blur.gaussian_blur(pixels, 9, 9, 3.0)
        self.assertEqual(channel(out, 9, 0, 0), 200)
        self.assertEqual(channel(out, 9, 8, 8), 200)

    def test_zero_sigma_changes_nothing(self):
        pixels = with_dot(9, 9, 4, 4)
        self.assertEqual(blur.gaussian_blur(pixels, 9, 9, 0.0), pixels)

    def test_a_single_pixel_image_survives(self):
        self.assertEqual(len(blur.gaussian_blur(solid(1, 1, 50), 1, 1, 3.0)), 4)

    def test_a_wrong_sized_buffer_is_refused(self):
        with self.assertRaises(ValueError):
            blur.gaussian_blur(bytearray(10), 5, 5, 1.0)

    def test_the_output_is_a_new_buffer(self):
        pixels = with_dot(9, 9, 4, 4)
        out = blur.gaussian_blur(pixels, 9, 9, 2.0)
        self.assertIsNot(out, pixels)
        self.assertEqual(len(out), len(pixels))


class RedactionStrengthTests(unittest.TestCase):
    """#22 is a security-shaped issue: the blur has to actually destroy the
    structure, not merely soften it."""

    WIDTH, HEIGHT, PERIOD = 96, 16, 4

    def _stripes(self):
        """Hard vertical stripes — a stand-in for text strokes."""
        pixels = solid(self.WIDTH, self.HEIGHT, 0)
        for y in range(self.HEIGHT):
            for x in range(self.WIDTH):
                value = 255 if (x // self.PERIOD) % 2 else 0
                offset = (y * self.WIDTH + x) * 4
                pixels[offset:offset + 4] = bytes([value, value, value, 255])
        return pixels

    def _amplitude(self, pixels):
        """Peak-to-trough over the middle of the image.

        Amplitude, not total variation: smoothing a step into a ramp leaves
        the total variation *unchanged* (it telescopes), so a gradient-energy
        metric reports a blur as doing nothing right up until the peaks merge.
        What decides legibility is how much contrast is left, and the middle is
        measured because a small test image is otherwise dominated by the edge
        clamping.
        """
        margin = self.WIDTH // 4
        values = [channel(pixels, self.WIDTH, x, y)
                  for y in range(self.HEIGHT)
                  for x in range(margin, self.WIDTH - margin)]
        return max(values) - min(values)

    def test_sharp_stripes_are_full_contrast(self):
        self.assertEqual(self._amplitude(self._stripes()), 255)

    def test_a_strong_blur_leaves_no_contrast_to_read(self):
        blurred = blur.gaussian_blur(self._stripes(), self.WIDTH, self.HEIGHT,
                                     5.0)
        self.assertLess(self._amplitude(blurred), 10)

    def test_contrast_falls_as_the_blur_grows(self):
        sharp = self._stripes()
        amplitudes = [
            self._amplitude(blur.gaussian_blur(sharp, self.WIDTH, self.HEIGHT,
                                               sigma))
            for sigma in (1.0, 2.0, 3.0, 4.0)
        ]
        self.assertEqual(amplitudes, sorted(amplitudes, reverse=True))
        self.assertLess(amplitudes[-1], amplitudes[0] / 10)


if __name__ == "__main__":
    unittest.main()
