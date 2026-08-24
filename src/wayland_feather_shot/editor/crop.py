"""Crop geometry: aspect presets, handles, and the rect editor.

Pure Python — no GTK — so all of the fiddly clamping is unit-testable.

The crop rect lives in **normalized** coordinates (0…1 of the source image,
top-left origin, y-down).  Keeping it normalized is what lets a crop be stored
in the sidecar and re-applied to the pristine image later: the rect describes a
region, not a pixel operation, so a crop can be widened again instead of only
tightened.

Aspect ratios are expressed in *pixel* terms and converted to a normalized
width/height ratio using the source dimensions, because a normalized square is
only a square when the image is.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

Rect = Tuple[float, float, float, float]   # x, y, w, h, normalized
Point = Tuple[float, float]

UNIT: Rect = (0.0, 0.0, 1.0, 1.0)

# Presets offered while cropping, in the order they appear in the toolbar.
ASPECTS: Tuple[str, ...] = ("free", "original", "1:1", "16:9", "9:16", "4:3", "3:2")

ASPECT_TITLES: Dict[str, str] = {
    "free": "Freeform",
    "original": "Original",
    "1:1": "1:1",
    "16:9": "16:9",
    "9:16": "9:16",
    "4:3": "4:3",
    "3:2": "3:2",
}

_PIXEL_RATIOS: Dict[str, float] = {
    "1:1": 1.0,
    "16:9": 16.0 / 9.0,
    "9:16": 9.0 / 16.0,
    "4:3": 4.0 / 3.0,
    "3:2": 3.0 / 2.0,
}

# The eight drag handles, as their normalized position inside the crop rect.
HANDLES: Dict[str, Point] = {
    "nw": (0.0, 0.0), "n": (0.5, 0.0), "ne": (1.0, 0.0),
    "w": (0.0, 0.5), "e": (1.0, 0.5),
    "sw": (0.0, 1.0), "s": (0.5, 1.0), "se": (1.0, 1.0),
}

CORNERS = ("nw", "ne", "se", "sw")


def is_corner(handle: str) -> bool:
    return handle in CORNERS


def _is_left(handle: str) -> bool:
    return handle in ("nw", "w", "sw")


def _is_top(handle: str) -> bool:
    return handle in ("nw", "n", "ne")


def locks_aspect(aspect: str) -> bool:
    return aspect != "free"


def pixel_ratio(aspect: str, image_size: Tuple[float, float]) -> Optional[float]:
    """The desired pixel width/height for *aspect*, or None for freeform."""
    if aspect == "free":
        return None
    if aspect == "original":
        w, h = image_size
        return (w / h) if h > 0 else None
    return _PIXEL_RATIOS.get(aspect)


def normalized_ratio(aspect: str,
                     image_size: Tuple[float, float]) -> Optional[float]:
    """The normalized width/height that renders as `pixel_ratio` once scaled
    back into pixels."""
    ratio = pixel_ratio(aspect, image_size)
    w, h = image_size
    if ratio is None or w <= 0 or h <= 0:
        return None
    return ratio * h / w


def _clamp(value: float, upper: float = 1.0) -> float:
    return min(max(value, 0.0), upper)


def _rect(min_x: float, min_y: float, max_x: float, max_y: float) -> Rect:
    return (min_x, min_y, max_x - min_x, max_y - min_y)


def handle_point(rect: Rect, handle: str) -> Point:
    """Where a handle sits, in normalized coordinates."""
    x, y, w, h = rect
    u, v = HANDLES[handle]
    return (x + w * u, y + h * v)


def contains(rect: Rect, point: Point) -> bool:
    x, y, w, h = rect
    return x <= point[0] <= x + w and y <= point[1] <= y + h


def to_pixels(rect: Rect, image_size: Tuple[float, float]) -> Tuple[int, int, int, int]:
    """The rect as integer pixels, clamped to the image and never empty."""
    iw, ih = int(image_size[0]), int(image_size[1])
    x = max(0, min(int(round(rect[0] * iw)), max(0, iw - 1)))
    y = max(0, min(int(round(rect[1] * ih)), max(0, ih - 1)))
    w = max(1, min(int(round(rect[2] * iw)), iw - x))
    h = max(1, min(int(round(rect[3] * ih)), ih - y))
    return (x, y, w, h)


def from_pixels(pixels: Tuple[float, float, float, float],
                image_size: Tuple[float, float]) -> Rect:
    iw, ih = image_size
    if iw <= 0 or ih <= 0:
        return UNIT
    return (pixels[0] / iw, pixels[1] / ih, pixels[2] / iw, pixels[3] / ih)


def move(rect: Rect, dx: float, dy: float) -> Rect:
    """Translate the rect, keeping it wholly inside the image."""
    x, y, w, h = rect
    return (_clamp(x + dx, max(0.0, 1.0 - w)),
            _clamp(y + dy, max(0.0, 1.0 - h)), w, h)


def apply_aspect(rect: Rect, ratio: Optional[float]) -> Rect:
    """Fit the largest rect of *ratio* centred on *rect*, inside the image."""
    if ratio is None or ratio <= 0:
        return rect
    x, y, w, h = rect
    if h <= 0 or w <= 0:
        return rect

    if w / h > ratio:
        w = h * ratio
    else:
        h = w / ratio
    # A ratio wider or taller than the image itself has to shrink to fit.
    if w > 1.0:
        w, h = 1.0, 1.0 / ratio
    if h > 1.0:
        h, w = 1.0, 1.0 * ratio

    cx, cy = x + rect[2] / 2, y + rect[3] / 2
    x, y = cx - w / 2, cy - h / 2
    x = min(max(x, 0.0), max(0.0, 1.0 - w))
    y = min(max(y, 0.0), max(0.0, 1.0 - h))
    return (x, y, w, h)


def resize(rect: Rect, handle: str, point: Point,
           ratio: Optional[float] = None,
           min_size: float = 0.01,
           from_center: bool = False) -> Rect:
    """Drag *handle* to *point*.

    Corner drags respect an aspect lock; edge drags ignore it, because forcing
    a ratio onto a single-axis drag makes the other edge jump away from where
    the pointer is.  With *from_center* the rect grows symmetrically about its
    own centre and the centre stays put.
    """
    point = (_clamp(point[0]), _clamp(point[1]))
    min_w = min(min_size, 1.0)
    min_h = min(min_size, 1.0)

    if from_center:
        return _resize_from_center(rect, handle, point, ratio, min_w, min_h)
    if is_corner(handle):
        return _resize_corner(rect, handle, point, ratio, min_w, min_h)

    x, y, w, h = rect
    min_x, min_y, max_x, max_y = x, y, x + w, y + h
    if handle == "w":
        min_x = min(point[0], max_x - min_w)
    elif handle == "e":
        max_x = max(point[0], min_x + min_w)
    elif handle == "n":
        min_y = min(point[1], max_y - min_h)
    elif handle == "s":
        max_y = max(point[1], min_y + min_h)
    return _rect(min_x, min_y, max_x, max_y)


def _resize_corner(rect: Rect, handle: str, point: Point,
                   ratio: Optional[float], min_w: float, min_h: float) -> Rect:
    x, y, w, h = rect
    left, top = _is_left(handle), _is_top(handle)
    anchor_x = (x + w) if left else x
    anchor_y = (y + h) if top else y

    corner_x = min(point[0], anchor_x - min_w) if left else max(point[0], anchor_x + min_w)
    corner_y = min(point[1], anchor_y - min_h) if top else max(point[1], anchor_y + min_h)

    if ratio and ratio > 0:
        width = abs(corner_x - anchor_x)
        height = abs(corner_y - anchor_y)
        if height > 0 and width / height > ratio:
            width = height * ratio
        else:
            height = width / ratio
        # Keep the ratio-locked corner inside the image.
        max_width = anchor_x if left else (1.0 - anchor_x)
        max_height = anchor_y if top else (1.0 - anchor_y)
        if width > max_width:
            width = max_width
            height = width / ratio
        if height > max_height:
            height = max_height
            width = height * ratio
        corner_x = anchor_x - width if left else anchor_x + width
        corner_y = anchor_y - height if top else anchor_y + height

    return _rect(min(corner_x, anchor_x), min(corner_y, anchor_y),
                 max(corner_x, anchor_x), max(corner_y, anchor_y))


def _resize_from_center(rect: Rect, handle: str, point: Point,
                        ratio: Optional[float], min_w: float,
                        min_h: float) -> Rect:
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    half_w, half_h = w / 2, h / 2

    if is_corner(handle):
        half_w = abs(point[0] - cx)
        half_h = abs(point[1] - cy)
        if ratio and ratio > 0:
            if half_h > 0 and half_w / half_h > ratio:
                half_w = half_h * ratio
            else:
                half_h = half_w / ratio
    elif handle in ("w", "e"):
        half_w = abs(point[0] - cx)
    else:
        half_h = abs(point[1] - cy)

    half_w = max(half_w, min_w / 2)
    half_h = max(half_h, min_h / 2)
    # Bounded by the nearer edge, so the centre cannot drift.
    half_w = min(half_w, cx, 1.0 - cx)
    half_h = min(half_h, cy, 1.0 - cy)
    if ratio and ratio > 0 and is_corner(handle):
        if half_h > 0 and half_w / half_h > ratio:
            half_w = half_h * ratio
        else:
            half_h = half_w / ratio

    return (cx - half_w, cy - half_h, half_w * 2, half_h * 2)


def compose(outer: Rect, inner: Rect) -> Rect:
    """A crop *inner*, expressed against an image that is already cropped to
    *outer*, re-expressed against the original.

    Crops stack: this is what keeps the stored rect anchored to the pristine
    image however many times it has been adjusted.
    """
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (ox + ix * ow, oy + iy * oh, iw * ow, ih * oh)
