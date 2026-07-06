"""Annotation shapes drawn on top of the captured image.

Shapes are lightweight immutable-ish objects rendered with cairo.  The canvas
keeps them in a list; undo/redo snapshots that list, so shapes must never be
mutated after being committed (translate() returns a copy).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, replace
from typing import List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkPixbuf  # noqa: E402

import cairo  # noqa: E402


@dataclass(frozen=True)
class Style:
    rgba: Tuple[float, float, float, float] = (1.0, 0.23, 0.19, 1.0)
    width: float = 3.0
    font_size: float = 22.0
    font_family: str = "Sans"


def _set_color(cr, style: Style):
    cr.set_source_rgba(*style.rgba)


class Shape:
    def draw(self, cr, base_pixbuf: GdkPixbuf.Pixbuf) -> None:
        raise NotImplementedError

    def translate(self, dx: float, dy: float) -> "Shape":
        raise NotImplementedError


@dataclass(frozen=True)
class Pen(Shape):
    points: Tuple[Tuple[float, float], ...]
    style: Style

    def draw(self, cr, base_pixbuf):
        if len(self.points) < 2:
            return
        _set_color(cr, self.style)
        cr.set_line_width(self.style.width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.move_to(*self.points[0])
        for p in self.points[1:]:
            cr.line_to(*p)
        cr.stroke()

    def translate(self, dx, dy):
        return replace(self, points=tuple((x + dx, y + dy) for x, y in self.points))


@dataclass(frozen=True)
class Line(Shape):
    p0: Tuple[float, float]
    p1: Tuple[float, float]
    style: Style

    def draw(self, cr, base_pixbuf):
        _set_color(cr, self.style)
        cr.set_line_width(self.style.width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(*self.p0)
        cr.line_to(*self.p1)
        cr.stroke()

    def translate(self, dx, dy):
        return replace(self, p0=(self.p0[0] + dx, self.p0[1] + dy),
                       p1=(self.p1[0] + dx, self.p1[1] + dy))


@dataclass(frozen=True)
class Arrow(Shape):
    p0: Tuple[float, float]   # tail
    p1: Tuple[float, float]   # head
    style: Style

    def draw(self, cr, base_pixbuf):
        _set_color(cr, self.style)
        cr.set_line_width(self.style.width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        x0, y0 = self.p0
        x1, y1 = self.p1
        angle = math.atan2(y1 - y0, x1 - x0)
        head = max(10.0, self.style.width * 4.0)
        # Stop the shaft a bit short so it doesn't poke through the head.
        sx = x1 - head * 0.6 * math.cos(angle)
        sy = y1 - head * 0.6 * math.sin(angle)
        cr.move_to(x0, y0)
        cr.line_to(sx, sy)
        cr.stroke()
        spread = math.pi / 7
        cr.move_to(x1, y1)
        cr.line_to(x1 - head * math.cos(angle - spread),
                   y1 - head * math.sin(angle - spread))
        cr.line_to(x1 - head * math.cos(angle + spread),
                   y1 - head * math.sin(angle + spread))
        cr.close_path()
        cr.fill()

    def translate(self, dx, dy):
        return replace(self, p0=(self.p0[0] + dx, self.p0[1] + dy),
                       p1=(self.p1[0] + dx, self.p1[1] + dy))


def _norm_rect(x0, y0, x1, y1):
    return (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))


@dataclass(frozen=True)
class RectShape(Shape):
    rect: Tuple[float, float, float, float]  # x, y, w, h
    style: Style
    filled: bool = False

    def draw(self, cr, base_pixbuf):
        _set_color(cr, self.style)
        x, y, w, h = self.rect
        cr.rectangle(x, y, w, h)
        if self.filled:
            cr.fill()
        else:
            cr.set_line_width(self.style.width)
            cr.stroke()

    def translate(self, dx, dy):
        x, y, w, h = self.rect
        return replace(self, rect=(x + dx, y + dy, w, h))


@dataclass(frozen=True)
class EllipseShape(Shape):
    rect: Tuple[float, float, float, float]
    style: Style

    def draw(self, cr, base_pixbuf):
        x, y, w, h = self.rect
        if w < 1 or h < 1:
            return
        _set_color(cr, self.style)
        cr.save()
        cr.translate(x + w / 2, y + h / 2)
        cr.scale(w / 2, h / 2)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.set_line_width(self.style.width)
        cr.stroke()

    def translate(self, dx, dy):
        x, y, w, h = self.rect
        return replace(self, rect=(x + dx, y + dy, w, h))


@dataclass(frozen=True)
class Highlight(Shape):
    """Semi-transparent marker band, like a highlighter pen."""
    rect: Tuple[float, float, float, float]
    style: Style

    def draw(self, cr, base_pixbuf):
        r, g, b, _ = self.style.rgba
        cr.set_source_rgba(r, g, b, 0.35)
        cr.rectangle(*self.rect)
        cr.fill()

    def translate(self, dx, dy):
        x, y, w, h = self.rect
        return replace(self, rect=(x + dx, y + dy, w, h))


@dataclass(frozen=True)
class Text(Shape):
    pos: Tuple[float, float]   # top-left of the first line's cap height
    text: str
    style: Style
    outline: bool = True       # contrasting outline for readability
    background: bool = False    # translucent chip behind the text

    def _lines(self):
        return self.text.split("\n") or [""]

    def _metrics(self, cr):
        """Return (line_height, [(line, width)], max_width, ascent)."""
        cr.select_font_face(self.style.font_family, cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(self.style.font_size)
        fe = cr.font_extents()
        ascent, line_h = fe[0], fe[2]
        line_h = max(line_h, self.style.font_size * 1.25)
        sized = [(ln, cr.text_extents(ln).width) for ln in self._lines()]
        max_w = max((w for _, w in sized), default=0.0)
        return line_h, sized, max_w, ascent

    def bounds(self, cr):
        """Bounding box (x, y, w, h) in image coordinates."""
        line_h, sized, max_w, ascent = self._metrics(cr)
        x, y = self.pos
        pad = self.style.font_size * 0.3
        h = line_h * len(sized)
        return (x - pad, y - pad, max_w + 2 * pad, h + 2 * pad)

    def draw(self, cr, base_pixbuf):
        line_h, sized, max_w, ascent = self._metrics(cr)
        x, y = self.pos

        if self.background:
            bx, by, bw, bh = self.bounds(cr)
            cr.set_source_rgba(0, 0, 0, 0.45)
            _rounded_rect(cr, bx, by, bw, bh, self.style.font_size * 0.25)
            cr.fill()

        r, g, b, a = self.style.rgba
        # Outline in the colour that contrasts with the fill (luminance test).
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        oc = 0.0 if luminance > 0.5 else 1.0
        for i, (line, _w) in enumerate(sized):
            baseline = y + ascent + i * line_h
            if self.outline:
                cr.move_to(x, baseline)
                cr.text_path(line)
                cr.set_source_rgba(oc, oc, oc, a)
                cr.set_line_width(max(2.0, self.style.font_size * 0.12))
                cr.set_line_join(cairo.LINE_JOIN_ROUND)
                cr.stroke()
            cr.move_to(x, baseline)
            cr.set_source_rgba(r, g, b, a)
            cr.show_text(line)

    def translate(self, dx, dy):
        return replace(self, pos=(self.pos[0] + dx, self.pos[1] + dy))


def _rounded_rect(cr, x, y, w, h, r):
    r = max(0.0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


@dataclass(frozen=True)
class Obscure(Shape):
    """Blur or pixelate a rectangle of the *original* image.

    factor is the downscale divisor; pixelate=True gives hard mosaic blocks,
    False gives a soft blur (bilinear down+up resampling).
    """
    rect: Tuple[float, float, float, float]
    factor: int = 8
    pixelate: bool = False

    def draw(self, cr, base_pixbuf):
        bw, bh = base_pixbuf.get_width(), base_pixbuf.get_height()
        x, y, w, h = (int(v) for v in self.rect)
        x = max(0, min(x, bw - 1))
        y = max(0, min(y, bh - 1))
        w = max(1, min(w, bw - x))
        h = max(1, min(h, bh - y))
        if w < 2 or h < 2:
            return
        sub = base_pixbuf.new_subpixbuf(x, y, w, h)
        f = max(2, int(self.factor) * (2 if self.pixelate else 1))
        small = sub.scale_simple(max(1, w // f), max(1, h // f),
                                 GdkPixbuf.InterpType.BILINEAR)
        interp = (GdkPixbuf.InterpType.NEAREST if self.pixelate
                  else GdkPixbuf.InterpType.BILINEAR)
        big = small.scale_simple(w, h, interp)
        cr.save()
        Gdk.cairo_set_source_pixbuf(cr, big, x, y)
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.restore()

    def translate(self, dx, dy):
        x, y, w, h = self.rect
        return replace(self, rect=(x + dx, y + dy, w, h))


@dataclass(frozen=True)
class Marker(Shape):
    """Auto-numbered circle badge (1, 2, 3, ...)."""
    pos: Tuple[float, float]
    number: int
    style: Style

    def draw(self, cr, base_pixbuf):
        x, y = self.pos
        radius = max(13.0, self.style.font_size * 0.65)
        _set_color(cr, self.style)
        cr.arc(x, y, radius, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 1)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(radius * 1.1)
        label = str(self.number)
        ext = cr.text_extents(label)
        cr.move_to(x - ext.width / 2 - ext.x_bearing,
                   y - ext.height / 2 - ext.y_bearing)
        cr.show_text(label)

    def translate(self, dx, dy):
        return replace(self, pos=(self.pos[0] + dx, self.pos[1] + dy))


def norm_rect(x0: float, y0: float, x1: float, y1: float):
    return _norm_rect(x0, y0, x1, y1)


# -- selection helpers (used by the select tool) --------------------------

def shape_bbox(shape: Shape, cr) -> Tuple[float, float, float, float]:
    """Axis-aligned bounding box (x, y, w, h) of *shape* in image coords.

    *cr* is a cairo context used only to measure text; it may be a scratch
    context on any surface.
    """
    if isinstance(shape, Pen):
        xs = [p[0] for p in shape.points] or [0.0]
        ys = [p[1] for p in shape.points] or [0.0]
        pad = shape.style.width
        return (min(xs) - pad, min(ys) - pad,
                max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)
    if isinstance(shape, (Line, Arrow)):
        (x0, y0), (x1, y1) = shape.p0, shape.p1
        pad = max(shape.style.width, 6.0)
        return (min(x0, x1) - pad, min(y0, y1) - pad,
                abs(x1 - x0) + 2 * pad, abs(y1 - y0) + 2 * pad)
    if isinstance(shape, (RectShape, EllipseShape, Highlight, Obscure)):
        x, y, w, h = shape.rect
        return (x, y, w, h)
    if isinstance(shape, Text):
        return shape.bounds(cr)
    if isinstance(shape, Marker):
        x, y = shape.pos
        r = max(13.0, shape.style.font_size * 0.65)
        return (x - r, y - r, 2 * r, 2 * r)
    return (0.0, 0.0, 0.0, 0.0)


def hit_test(shapes: List[Shape], cr, x: float, y: float) -> Optional[int]:
    """Index of the topmost shape whose bounding box contains (x, y), or
    None.  Shapes are drawn in order, so the last match wins (topmost)."""
    for i in range(len(shapes) - 1, -1, -1):
        bx, by, bw, bh = shape_bbox(shapes[i], cr)
        if bx <= x <= bx + bw and by <= y <= by + bh:
            return i
    return None


def has_style(shape: Shape) -> bool:
    return any(f.name == "style" for f in fields(shape))


def with_style(shape: Shape, style: Style) -> Shape:
    """Return a copy of *shape* restyled, or the shape unchanged if it has no
    style (e.g. Obscure blur/pixelate has no colour)."""
    if has_style(shape):
        return replace(shape, style=style)
    return shape
