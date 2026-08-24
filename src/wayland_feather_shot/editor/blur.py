"""Gaussian blur over raw RGBA bytes.

Pure Python — no GTK, no cairo — so it can be unit-tested in CI, and it works
on plain buffers rather than pixbufs.  numpy is used when it is installed (it
already is an optional dependency, for the scroll stitcher) and the pure-Python
path is the fallback, exactly as the stitcher does it.

A true Gaussian convolution is too slow to run per frame in Python, so this
uses the standard approximation: **three successive box blurs converge on a
Gaussian** to within a few percent, and each box pass is a running sum, so it
costs one add and one subtract per pixel regardless of radius.

This is a redaction primitive, so the bias is towards destroying information:
the caller downsamples before blurring, which both makes the work small and
makes the result genuinely unrecoverable rather than merely smeared.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

try:  # pragma: no cover - depends on the host
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None

CHANNELS = 4


def boxes_for_gauss(sigma: float, passes: int = 3) -> List[int]:
    """Box sizes whose successive application approximates a Gaussian.

    Kutskir's construction: pick the ideal averaging width, split it into
    `passes` boxes of two adjacent odd sizes, and the result is within a few
    percent of a true Gaussian at a fraction of the cost.
    """
    if sigma <= 0:
        return [1] * passes
    ideal = math.sqrt((12 * sigma * sigma / passes) + 1)
    lower = int(math.floor(ideal))
    if lower % 2 == 0:
        lower -= 1
    upper = lower + 2

    ideal_m = (12 * sigma * sigma - passes * lower * lower
               - 4 * passes * lower - 3 * passes) / (-4 * lower - 4)
    m = round(ideal_m)
    return [max(1, lower if i < m else upper) for i in range(passes)]


def _box_blur_pass(pixels: bytearray, width: int, height: int,
                   radius: int, horizontal: bool) -> bytearray:
    """One box blur along one axis, with a running sum.

    Edges clamp: the first and last pixel of each line are repeated to fill the
    window, so a blurred region does not darken towards its own border.
    """
    if radius < 1:
        return pixels
    out = bytearray(len(pixels))
    window = radius * 2 + 1

    outer, inner = (height, width) if horizontal else (width, height)
    # Steps through the buffer, in bytes.
    step = CHANNELS if horizontal else width * CHANNELS
    line_step = width * CHANNELS if horizontal else CHANNELS

    for line in range(outer):
        base = line * line_step
        for channel in range(CHANNELS):
            first = pixels[base + channel]
            last = pixels[base + (inner - 1) * step + channel]
            total = first * (radius + 1)
            for i in range(radius):
                total += pixels[base + min(i, inner - 1) * step + channel]

            for i in range(inner):
                leaving = (pixels[base + (i - radius - 1) * step + channel]
                           if i - radius - 1 >= 0 else first)
                entering = (pixels[base + (i + radius) * step + channel]
                            if i + radius < inner else last)
                total += entering - leaving
                out[base + i * step + channel] = total // window
    return out


def _box_blur_pass_numpy(array, radius: int, axis: int):  # pragma: no cover
    """The same pass, vectorised.  Edges clamp the same way."""
    if radius < 1:
        return array
    window = radius * 2 + 1
    padded = _np.pad(array, [(radius + 1, radius) if a == axis else (0, 0)
                             for a in range(array.ndim)], mode="edge")
    cumulative = _np.cumsum(padded.astype(_np.int64), axis=axis)
    upper = _np.take(cumulative, range(window, cumulative.shape[axis]), axis=axis)
    lower = _np.take(cumulative, range(0, cumulative.shape[axis] - window),
                     axis=axis)
    return ((upper - lower) // window).astype(_np.uint8)


def gaussian_blur(pixels: Sequence[int], width: int, height: int,
                  sigma: float, passes: int = 3) -> bytearray:
    """Blur a tightly packed RGBA buffer.

    ``len(pixels)`` must be ``width * height * 4``; the result is a new buffer
    of the same shape.
    """
    expected = width * height * CHANNELS
    if len(pixels) != expected:
        raise ValueError(f"expected {expected} bytes, got {len(pixels)}")
    if width < 1 or height < 1 or sigma <= 0:
        return bytearray(pixels)

    boxes = boxes_for_gauss(sigma, passes)
    if _np is not None:  # pragma: no cover - exercised only where numpy exists
        array = _np.frombuffer(bytes(pixels), dtype=_np.uint8).reshape(
            height, width, CHANNELS)
        for box in boxes:
            radius = (box - 1) // 2
            array = _box_blur_pass_numpy(array, radius, axis=1)
            array = _box_blur_pass_numpy(array, radius, axis=0)
        return bytearray(array.tobytes())

    buffer = bytearray(pixels)
    for box in boxes:
        radius = (box - 1) // 2
        buffer = _box_blur_pass(buffer, width, height, radius, horizontal=True)
        buffer = _box_blur_pass(buffer, width, height, radius, horizontal=False)
    return buffer


def has_numpy() -> bool:
    return _np is not None
