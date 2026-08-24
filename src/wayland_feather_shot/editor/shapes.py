"""The annotation shape model.

Pure Python — no ``gi``, no cairo — so the model and everything derived from it
can be unit-tested in CI.  Drawing lives in :mod:`.render`, pointer handling in
:mod:`.interaction`, and the GTK widget in :mod:`.canvas`.

Every shape is a :class:`Shape`: a **transform** (position, rotation, opacity)
plus a kind-specific payload.  The payload is expressed in the shape's own
local space, so rotation and resizing work the same way for every kind instead
of being re-implemented per class.  Page space — the space the transform lands
in — is the captured image's own pixel space, which makes export a 1:1 draw.

Shapes are frozen: an edit returns a copy.  Undo just snapshots the tuple.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace
from typing import Callable, List, Optional, Sequence, Tuple

from . import arrows
from . import freehand
from .geometry import (Box, Circle2d, Ellipse2d, Geometry, Group2d, Point,
                       Polygon2d, Polyline2d, Rect2d, norm_rect, rotate)

# Stroke widths, font sizes and badge diameters are authored against an image
# this many pixels on its longest edge, then scaled to the capture's real size.
# Without it the same "4" is a hairline on a 4K capture and a slab on a crop.
REFERENCE_EDGE = 1080.0

_ids = itertools.count(1)


def _new_id() -> str:
    return f"s{next(_ids)}"


def page_stroke_width(slider_value: float, image_edge: float) -> float:
    """Convert an authored width into page (image pixel) units."""
    if image_edge <= 0:
        return max(1.0, slider_value)
    return max(1.0, slider_value * image_edge / REFERENCE_EDGE)


def density_from_factor(factor) -> float:
    """Map the legacy 2…24 ``blur_factor`` setting onto the 0…1 density a
    redaction shape carries."""
    return min(1.0, max(0.0, (float(factor) - 2.0) / 22.0))


def slider_stroke_width(page_width: float, image_edge: float) -> float:
    """The inverse of :func:`page_stroke_width`, for showing a shape's width
    back in the toolbar."""
    if image_edge <= 0:
        return page_width
    return page_width * REFERENCE_EDGE / image_edge


# -- style -------------------------------------------------------------------

@dataclass(frozen=True)
class Style:
    rgba: Tuple[float, float, float, float] = (1.0, 0.23, 0.19, 1.0)
    width: float = 3.0
    font_size: float = 22.0
    font_family: str = "Sans"


# -- text measurement --------------------------------------------------------
#
# Text geometry needs to know how wide a string renders, which only Pango can
# answer — and Pango is not importable in CI.  The renderer installs the real
# measurer at import time; until then a rough monospace estimate keeps the
# model usable (and testable) on its own.

MeasureFn = Callable[[str, Style, float], Tuple[float, float]]


def _estimate_text(text: str, style: Style,
                   wrap_width: float = 0.0) -> Tuple[float, float]:
    """A rough monospace guess, for when Pango is not importable (CI)."""
    per_char = style.font_size * 0.6
    lines = text.split("\n") or [""]
    if wrap_width > 0:
        columns = max(1, int(wrap_width / per_char))
        wrapped = 0
        for line in lines:
            wrapped += max(1, -(-len(line) // columns))
        return (wrap_width, wrapped * style.font_size * 1.3)
    width = max((len(line) for line in lines), default=0) * per_char
    return (width, len(lines) * style.font_size * 1.3)


_measure_text: MeasureFn = _estimate_text


def set_text_measurer(fn: MeasureFn) -> None:
    """Install the real (Pango-backed) text measurer."""
    global _measure_text
    _measure_text = fn


def measure_text(text: str, style: Style,
                 wrap_width: float = 0.0) -> Tuple[float, float]:
    """Measure a string, hooking up the real measurer on first use.

    The estimate exists so the model can be imported and tested without a
    GObject stack; anywhere the stack *is* available — including callers that
    build shapes without touching the renderer first, like the capture
    overlay — the Pango measurement is the one that has to be used, or the
    stored size will not match what gets drawn.
    """
    global _measure_text
    if _measure_text is _estimate_text:
        try:
            from . import render  # noqa: F401  (installs the measurer)
        except Exception:
            # No GObject stack: keep the estimate.
            _measure_text = _estimate_text_final
    return _measure_text(text, style, wrap_width)


def _estimate_text_final(text: str, style: Style,
                         wrap_width: float = 0.0) -> Tuple[float, float]:
    """The estimate, under a distinct name so the hook only runs once."""
    return _estimate_text(text, style, wrap_width)


# -- payloads ----------------------------------------------------------------

class Props:
    """Base for a shape's kind-specific payload, in the shape's local space."""

    KIND = "?"
    style: Optional[Style] = None

    def geometry(self) -> Geometry:
        raise NotImplementedError

    def scaled(self, sx: float, sy: float, width_only: bool = False) -> "Props":
        """Return a copy scaled about the local origin.

        *width_only* means the drag was a side handle rather than a corner;
        only text cares, and for it the distinction is the difference between
        resizing the box and resizing the type.
        """
        raise NotImplementedError

    def restyled(self, style: Style) -> "Props":
        return replace(self, style=style) if self.style is not None else self


def _mean_scale(sx: float, sy: float) -> float:
    return (abs(sx) + abs(sy)) / 2.0


@dataclass(frozen=True)
class PenProps(Props):
    """A freehand stroke.  Points are local and start at (0, 0)."""

    KIND = "pen"
    points: Tuple[Point, ...]
    style: Style
    closed: bool = False

    def stroke_options(self) -> freehand.StrokeOptions:
        return freehand.options_for(self.style.width, complete=True)

    def geometry(self):
        if len(self.points) < 2:
            radius = max(self.style.width, 1.0)
            return Circle2d(radius * 2, filled=True)
        # The streamlined centreline, padded by the stroke's half-width: it is
        # what the ink follows, it costs a fraction of the full outline, and it
        # keeps what you grab in step with what you see.
        line = freehand.centerline(self.points, self.stroke_options())
        padding = max(self.style.width / 2, 1.0)
        if self.closed:
            return Polygon2d(line, filled=False, padding=padding)
        return Polyline2d(line, padding=padding)

    def scaled(self, sx, sy, width_only: bool = False):
        return replace(self, points=tuple((x * sx, y * sy) for x, y in self.points))


@dataclass(frozen=True)
class ArrowProps(Props):
    """A straight shaft from the local origin to *end*.

    ``head_end``/``head_start`` are ``"none"`` or ``"arrow"``; a plain line is
    an arrow with no heads, so line and arrow share one implementation.
    ``number`` turns it into a step arrow with a badge at the tail.
    """

    KIND = "arrow"
    end: Point
    style: Style
    head_end: str = "arrow"
    head_start: str = "none"
    number: Optional[int] = None
    #: Signed perpendicular distance from the straight chord to the arrow's
    #: middle.  Zero is a straight line; anything else bows it into an arc.
    bend: float = 0.0

    @property
    def badge_radius(self) -> float:
        return max(11.0, self.style.font_size * 0.55)

    @property
    def start(self) -> Point:
        return (0.0, 0.0)

    def path(self):
        return arrows.path_points(self.start, self.end, self.bend)

    def middle(self) -> Point:
        return arrows.middle_point(self.start, self.end, self.bend)

    def geometry(self):
        shaft = Polyline2d(self.path(), padding=max(self.style.width / 2, 1.0))
        if self.number is None:
            return shaft
        r = self.badge_radius
        return Group2d([shaft, _Placed(Circle2d(r * 2, filled=True), (-r, -r))])

    def scaled(self, sx, sy, width_only: bool = False):
        return replace(self, end=(self.end[0] * sx, self.end[1] * sy),
                       bend=self.bend * _mean_scale(sx, sy))


@dataclass(frozen=True)
class GeoProps(Props):
    """A rectangle or an ellipse, inscribed in the local box (0, 0, w, h)."""

    KIND = "geo"
    w: float
    h: float
    style: Style
    geo: str = "rect"          # "rect" | "ellipse"
    filled: bool = False

    def geometry(self):
        cls = Ellipse2d if self.geo == "ellipse" else Rect2d
        return cls(self.w, self.h, filled=self.filled)

    def scaled(self, sx, sy, width_only: bool = False):
        return replace(self, w=max(1.0, abs(self.w * sx)), h=max(1.0, abs(self.h * sy)))


@dataclass(frozen=True)
class HighlightProps(Props):
    """A translucent marker band."""

    KIND = "highlight"
    w: float
    h: float
    style: Style

    def geometry(self):
        return Rect2d(self.w, self.h, filled=True)

    def scaled(self, sx, sy, width_only: bool = False):
        return replace(self, w=max(1.0, abs(self.w * sx)), h=max(1.0, abs(self.h * sy)))


@dataclass(frozen=True)
class SpotlightProps(Props):
    """A region to keep bright while everything else is dimmed.

    The scrim is not drawn per shape — several spotlights have to leave a
    single union undimmed rather than double-darkening where they overlap — so
    the renderer paints one scrim pass and punches every spotlight out of it.
    """

    KIND = "spotlight"
    w: float
    h: float
    #: How dark the surrounding scrim is, 0…1.
    scrim: float = 0.55

    def geometry(self):
        return Rect2d(self.w, self.h, filled=True)

    def scaled(self, sx, sy, width_only: bool = False):
        return replace(self, w=max(1.0, abs(self.w * sx)),
                       h=max(1.0, abs(self.h * sy)))


@dataclass(frozen=True)
class ObscureProps(Props):
    """A blurred or pixelated region of the *base* image.

    ``density`` is 0…1 and drives both the blur radius and the mosaic block
    size, so strength stays adjustable after the region is drawn.
    """

    KIND = "obscure"
    w: float
    h: float
    density: float = 0.55
    pixelate: bool = False

    def geometry(self):
        return Rect2d(self.w, self.h, filled=True)

    def scaled(self, sx, sy, width_only: bool = False):
        return replace(self, w=max(1.0, abs(self.w * sx)), h=max(1.0, abs(self.h * sy)))


ALIGNMENTS = ("left", "center", "right")

#: A wrapped text box never gets narrower than this many page units.
MIN_TEXT_WIDTH = 24.0


@dataclass(frozen=True)
class TextProps(Props):
    """Text anchored at the local origin.

    ``w``/``h`` are the measured size, kept on the payload so geometry and
    hit-testing stay pure; :meth:`remeasured` refreshes them whenever the text,
    the style or the wrap width changes.

    While ``auto_size`` is true the box is exactly as wide as its text.
    Dragging a side handle turns it off and sets ``wrap_width``, which is how
    text switches from growing to wrapping.
    """

    KIND = "text"
    text: str
    style: Style
    w: float = 0.0
    h: float = 0.0
    outline: bool = True
    background: bool = False
    align: str = "left"
    auto_size: bool = True
    wrap_width: float = 0.0

    @property
    def padding(self) -> float:
        return self.style.font_size * 0.3

    @property
    def effective_wrap(self) -> float:
        """The width text wraps into, or 0 when it grows instead."""
        return 0.0 if self.auto_size else max(self.wrap_width, MIN_TEXT_WIDTH)

    def geometry(self):
        pad = self.padding
        return _Placed(Rect2d(self.w + 2 * pad, self.h + 2 * pad, filled=True),
                       (-pad, -pad))

    def scaled(self, sx, sy, width_only: bool = False):
        if width_only:
            # A side handle sets the width text wraps into rather than scaling
            # the type: that is the whole gesture for turning a growing box
            # into a wrapping one.
            width = self.w if not self.auto_size else self.w
            return replace(self, auto_size=False,
                           wrap_width=max(MIN_TEXT_WIDTH,
                                          abs(width * sx))).remeasured()
        scale = _mean_scale(sx, sy)
        style = replace(self.style, font_size=max(4.0, self.style.font_size * scale))
        wrap = self.wrap_width * scale if not self.auto_size else self.wrap_width
        return replace(self, style=style, wrap_width=wrap).remeasured()

    def restyled(self, style):
        return replace(self, style=style).remeasured()

    def with_text(self, text: str) -> "TextProps":
        return replace(self, text=text).remeasured()

    def remeasured(self) -> "TextProps":
        w, h = measure_text(self.text, self.style, self.effective_wrap)
        return replace(self, w=w, h=h)


@dataclass(frozen=True)
class MarkerProps(Props):
    """An auto-numbered badge filling the local box (0, 0, d, d)."""

    KIND = "marker"
    number: int
    diameter: float
    style: Style

    def geometry(self):
        return Circle2d(self.diameter, filled=True)

    def scaled(self, sx, sy, width_only: bool = False):
        return replace(self, diameter=max(8.0, self.diameter * _mean_scale(sx, sy)))


@dataclass(frozen=True)
class BubbleProps(Props):
    """A rounded speech bubble with a tail below its body."""

    KIND = "bubble"
    w: float
    h: float
    text: str
    style: Style

    @property
    def tail_depth(self) -> float:
        return min(24.0, self.h * 0.4)

    def geometry(self):
        return Rect2d(self.w, self.h + self.tail_depth, filled=True)

    def scaled(self, sx, sy, width_only: bool = False):
        return replace(self, w=max(6.0, abs(self.w * sx)), h=max(6.0, abs(self.h * sy)))


@dataclass(frozen=True)
class EmojiProps(Props):
    """A single character placed as a sticker."""

    KIND = "emoji"
    char: str
    size: float

    @property
    def w(self) -> float:
        return self.size * max(1, len(self.char))

    def geometry(self):
        return Rect2d(self.w, self.size, filled=True)

    def scaled(self, sx, sy, width_only: bool = False):
        return replace(self, size=max(8.0, self.size * _mean_scale(sx, sy)))


class _Placed(Geometry):
    """A primitive offset inside its shape's local space (a badge that hangs
    off an arrow's tail, text padded around its anchor)."""

    def __init__(self, inner: Geometry, offset: Point):
        self.inner = inner
        self.offset = offset
        self.filled = inner.filled

    def _local(self, p: Point) -> Point:
        return (p[0] - self.offset[0], p[1] - self.offset[1])

    @property
    def vertices(self):
        ox, oy = self.offset
        return [(x + ox, y + oy) for x, y in self.inner.vertices]

    @property
    def closed(self):
        return self.inner.closed

    @property
    def bounds(self):
        b = self.inner.bounds
        return Box(b.x + self.offset[0], b.y + self.offset[1], b.w, b.h)

    def hit_test(self, p, margin=0.0, hit_inside=False):
        return self.inner.hit_test(self._local(p), margin, hit_inside)

    def overlaps_polygon(self, poly):
        return self.inner.overlaps_polygon([self._local(p) for p in poly])


# -- the shape ---------------------------------------------------------------

@dataclass(frozen=True)
class Shape:
    """A payload placed in page space."""

    x: float
    y: float
    props: Props
    rotation: float = 0.0
    opacity: float = 1.0
    sid: str = field(default_factory=_new_id, compare=False)

    @property
    def kind(self) -> str:
        return self.props.KIND

    @property
    def style(self) -> Optional[Style]:
        return self.props.style

    @property
    def origin(self) -> Point:
        return (self.x, self.y)

    # -- transforms --

    def to_local(self, p: Point) -> Point:
        """A page point in this shape's local space."""
        return rotate((p[0] - self.x, p[1] - self.y), -self.rotation)

    def to_page(self, p: Point) -> Point:
        px, py = rotate(p, self.rotation)
        return (px + self.x, py + self.y)

    def translate(self, dx: float, dy: float) -> "Shape":
        return replace(self, x=self.x + dx, y=self.y + dy)

    def moved_to(self, x: float, y: float) -> "Shape":
        return replace(self, x=x, y=y)

    def rotated(self, delta: float, center: Point) -> "Shape":
        nx, ny = rotate((self.x, self.y), delta, center)
        return replace(self, x=nx, y=ny, rotation=self.rotation + delta)

    def scaled(self, sx: float, sy: float, width_only: bool = False) -> "Shape":
        return replace(self, props=self.props.scaled(sx, sy, width_only))

    def retexted(self, text: str) -> "Shape":
        """Set a text shape's content, keeping its alignment anchor fixed.

        Centred text grows evenly to both sides and right-aligned text grows
        leftwards; without this every edit would shove the box rightwards from
        wherever it was placed.
        """
        if self.kind != "text":
            return self
        before = self.props.w
        props = self.props.with_text(text)
        delta = props.w - before
        if delta == 0 or props.align == "left":
            return replace(self, props=props)
        shift = delta / 2 if props.align == "center" else delta
        # The shift happens in the shape's own frame, so rotated text still
        # grows the right way.
        dx, dy = rotate((shift, 0.0), self.rotation)
        return replace(self, x=self.x - dx, y=self.y - dy, props=props)

    def restyled(self, style: Style) -> "Shape":
        return replace(self, props=self.props.restyled(style))

    # -- geometry --

    def geometry(self) -> Geometry:
        return self.props.geometry()

    @property
    def local_bounds(self) -> Box:
        return self.geometry().bounds

    @property
    def page_corners(self) -> List[Point]:
        """The local bounds as a (possibly rotated) quad in page space."""
        return [self.to_page(p) for p in self.local_bounds.corners]

    @property
    def page_bounds(self) -> Box:
        geometry = self.geometry()
        vertices = geometry.vertices
        if not vertices:
            return Box(self.x, self.y, 0.0, 0.0)
        box = Box.from_points(self.to_page(v) for v in vertices)
        # A path that carries its own half-width (a pen stroke) covers more
        # than its centreline does.
        padding = getattr(geometry, "padding", 0.0)
        return box.expand(padding) if padding else box

    @property
    def is_filled(self) -> bool:
        """Whether a click in the middle grabs the shape."""
        return self.geometry().filled

    def hit_test(self, page_point: Point, margin: float = 0.0) -> bool:
        return self.geometry().hit_test(self.to_local(page_point), margin,
                                        hit_inside=self.is_filled)

    def overlaps(self, page_polygon: Sequence[Point]) -> bool:
        return self.geometry().overlaps_polygon(
            [self.to_local(p) for p in page_polygon])

    # -- drawing (delegates to the cairo renderer) --

    def draw(self, cr, base_pixbuf) -> None:
        from . import render
        render.draw_shape(cr, self, base_pixbuf)


# -- constructors ------------------------------------------------------------
#
# Named for the tools they back, and taking page-space arguments, so call sites
# stay readable: `Arrow(tail, head, style)` rather than an origin plus a local
# delta.

def Pen(points: Sequence[Point], style: Style, closed: bool = False) -> Shape:
    pts = list(points) or [(0.0, 0.0)]
    ox, oy = pts[0]
    local = tuple((x - ox, y - oy) for x, y in pts)
    return Shape(ox, oy, PenProps(local, style, closed))


def Line(p0: Point, p1: Point, style: Style) -> Shape:
    return Shape(p0[0], p0[1],
                 ArrowProps((p1[0] - p0[0], p1[1] - p0[1]), style, head_end="none"))


def Arrow(p0: Point, p1: Point, style: Style) -> Shape:
    return Shape(p0[0], p0[1], ArrowProps((p1[0] - p0[0], p1[1] - p0[1]), style))


def StepArrow(p0: Point, p1: Point, number: int, style: Style) -> Shape:
    return Shape(p0[0], p0[1],
                 ArrowProps((p1[0] - p0[0], p1[1] - p0[1]), style, number=number))


def RectShape(rect, style: Style, filled: bool = False) -> Shape:
    x, y, w, h = rect
    return Shape(x, y, GeoProps(w, h, style, geo="rect", filled=filled))


def EllipseShape(rect, style: Style) -> Shape:
    x, y, w, h = rect
    return Shape(x, y, GeoProps(w, h, style, geo="ellipse"))


def Highlight(rect, style: Style) -> Shape:
    x, y, w, h = rect
    return Shape(x, y, HighlightProps(w, h, style))


def Spotlight(rect, scrim: float = 0.55) -> Shape:
    x, y, w, h = rect
    return Shape(x, y, SpotlightProps(w, h, scrim=scrim))


def Obscure(rect, density: float = 0.55, pixelate: bool = False) -> Shape:
    x, y, w, h = rect
    return Shape(x, y, ObscureProps(w, h, density=density, pixelate=pixelate))


def Text(pos: Point, text: str, style: Style, outline: bool = True,
         background: bool = False, align: str = "left") -> Shape:
    props = TextProps(text, style, outline=outline, background=background,
                      align=align).remeasured()
    return Shape(pos[0], pos[1], props)


def Marker(pos: Point, number: int, style: Style,
           diameter: Optional[float] = None) -> Shape:
    d = diameter if diameter is not None else max(26.0, style.font_size * 1.3)
    return Shape(pos[0] - d / 2, pos[1] - d / 2, MarkerProps(number, d, style))


def SpeechBubble(rect, text: str, style: Style) -> Shape:
    x, y, w, h = rect
    return Shape(x, y, BubbleProps(w, h, text, style))


def EmojiSticker(pos: Point, char: str, style: Style,
                 size: Optional[float] = None) -> Shape:
    return Shape(pos[0], pos[1],
                 EmojiProps(char, size if size is not None
                            else max(28.0, style.font_size * 2.2)))


# -- collection helpers ------------------------------------------------------

def next_number(shapes: Sequence[Shape]) -> int:
    """The next unused badge number.

    Taking the maximum rather than counting is what keeps numbering correct
    after a delete or an undo: counting hands out a duplicate as soon as any
    badge but the last one goes away.  Markers and step arrows share one
    sequence, because a step-by-step guide reads as one sequence.
    """
    used = [s.props.number for s in shapes
            if s.kind == "marker" or (s.kind == "arrow" and s.props.number is not None)]
    return (max(used) if used else 0) + 1


def hit_shape(shapes: Sequence[Shape], page_point: Point,
              margin: float = 4.0) -> Optional[int]:
    """Index of the topmost shape actually under *page_point*, or None."""
    for i in range(len(shapes) - 1, -1, -1):
        if shapes[i].hit_test(page_point, margin):
            return i
    return None


def shapes_in(shapes: Sequence[Shape], box: Box) -> List[int]:
    """Indices of every shape a marquee *box* touches."""
    poly = box.corners
    return [i for i, s in enumerate(shapes) if s.overlaps(poly)]


def selection_bounds(shapes: Sequence[Shape]) -> Optional[Box]:
    """The page-space frame around a selection, axis-aligned."""
    boxes = [s.page_bounds for s in shapes]
    return Box.union(boxes) if boxes else None


__all__ = [
    "REFERENCE_EDGE", "Style", "Shape", "Props", "Box", "Point",
    "PenProps", "ArrowProps", "GeoProps", "HighlightProps", "ObscureProps",
    "SpotlightProps", "Spotlight",
    "TextProps", "MarkerProps", "BubbleProps", "EmojiProps",
    "ALIGNMENTS", "MIN_TEXT_WIDTH",
    "Pen", "Line", "Arrow", "StepArrow", "RectShape", "EllipseShape",
    "Highlight", "Obscure", "Text", "Marker", "SpeechBubble", "EmojiSticker",
    "next_number", "hit_shape", "shapes_in", "selection_bounds", "norm_rect",
    "page_stroke_width", "slider_stroke_width", "measure_text",
    "density_from_factor",
    "set_text_measurer",
]
