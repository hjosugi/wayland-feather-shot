"""Cairo rendering for the annotation shapes.

Split out of the model so :mod:`.shapes` stays pure Python: this is the only
module in the editor core that touches GTK, and importing it installs the
Pango-backed text measurer the model needs.

All text goes through **Pango**.  Cairo's "toy" font API (``select_font_face``
/ ``show_text``) picks a single face and does no fallback, so every CJK
character and every emoji renders as the same `.notdef` tofu box — which made
Japanese annotations and the whole emoji palette unusable.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GdkPixbuf, Pango, PangoCairo  # noqa: E402

import cairo  # noqa: E402

from . import shapes as S  # noqa: E402

_scratch_cr: Optional[cairo.Context] = None


def _scratch() -> cairo.Context:
    """A 1x1 context used only for measuring."""
    global _scratch_cr
    if _scratch_cr is None:
        _scratch_cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
    return _scratch_cr


# -- text --------------------------------------------------------------------

def make_layout(cr, text: str, style: S.Style, bold: bool = True,
                size: Optional[float] = None):
    layout = PangoCairo.create_layout(cr)
    desc = Pango.FontDescription()
    desc.set_family(style.font_family or "Sans")
    desc.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
    # Absolute size means device units, i.e. image pixels — the same units the
    # rest of the model works in.
    desc.set_absolute_size(max(1.0, size if size is not None else style.font_size)
                           * Pango.SCALE)
    layout.set_font_description(desc)
    layout.set_text(text, -1)
    return layout


def measure(text: str, style: S.Style, bold: bool = True,
            size: Optional[float] = None) -> Tuple[float, float]:
    layout = make_layout(_scratch(), text, style, bold=bold, size=size)
    _ink, logical = layout.get_pixel_extents()
    return (float(logical.width), float(logical.height))


S.set_text_measurer(lambda text, style: measure(text, style))


def draw_text(cr, text: str, x: float, y: float, style: S.Style,
              bold: bool = True, size: Optional[float] = None,
              rgba: Optional[Tuple[float, float, float, float]] = None,
              outline: bool = False) -> None:
    """Draw *text* with its top-left at (x, y)."""
    if not text:
        return
    layout = make_layout(cr, text, style, bold=bold, size=size)
    r, g, b, a = rgba if rgba is not None else style.rgba

    if outline:
        # Stroke a contrasting halo behind the glyphs so text stays readable on
        # busy screenshots.  The halo colour is picked by luminance.
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        halo = 0.0 if luminance > 0.5 else 1.0
        cr.save()
        cr.move_to(x, y)
        PangoCairo.layout_path(cr, layout)
        cr.set_source_rgba(halo, halo, halo, a)
        cr.set_line_width(max(2.0, (size or style.font_size) * 0.12))
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.stroke()
        cr.restore()

    cr.save()
    cr.move_to(x, y)
    cr.set_source_rgba(r, g, b, a)
    # show_layout (not layout_path + fill) so colour emoji fonts render in
    # colour; a path can only carry a monochrome outline.
    PangoCairo.show_layout(cr, layout)
    cr.restore()


# -- small helpers -----------------------------------------------------------

def _set_color(cr, style: S.Style) -> None:
    cr.set_source_rgba(*style.rgba)


def rounded_rect(cr, x, y, w, h, r) -> None:
    r = max(0.0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


def _badge(cr, cx: float, cy: float, radius: float, label: str,
           style: S.Style) -> None:
    _set_color(cr, style)
    cr.arc(cx, cy, radius, 0, 2 * math.pi)
    cr.fill()
    size = radius * 1.1
    w, h = measure(label, style, size=size)
    draw_text(cr, label, cx - w / 2, cy - h / 2, style,
              size=size, rgba=(1, 1, 1, 1))


# -- redaction ---------------------------------------------------------------

def pixel_block_size(density: float) -> float:
    """Mosaic block size for a 0…1 density."""
    return 4.0 + min(max(density, 0.0), 1.0) * 36.0


def blur_radius(density: float) -> float:
    """Blur strength for a 0…1 density."""
    return 2.0 + min(max(density, 0.0), 1.0) * 28.0


def _obscured_pixbuf(base: GdkPixbuf.Pixbuf, x: int, y: int, w: int, h: int,
                     density: float, pixelate: bool) -> Optional[GdkPixbuf.Pixbuf]:
    sub = base.new_subpixbuf(x, y, w, h)
    if pixelate:
        block = max(2, int(round(pixel_block_size(density))))
        small = sub.scale_simple(max(1, w // block), max(1, h // block),
                                 GdkPixbuf.InterpType.BILINEAR)
        if small is None:
            return None
        return small.scale_simple(w, h, GdkPixbuf.InterpType.NEAREST)

    # Two down/up passes: one bilinear resample leaves enough stroke structure
    # that large text stays readable, which is the one thing a redaction must
    # never do.
    radius = max(2, int(round(blur_radius(density))))
    out = sub
    for _ in range(2):
        small = out.scale_simple(max(1, w // radius), max(1, h // radius),
                                 GdkPixbuf.InterpType.BILINEAR)
        if small is None:
            return None
        out = small.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
        if out is None:
            return None
    return out


# -- shape drawing -----------------------------------------------------------

def draw_shape(cr, shape: S.Shape, base_pixbuf) -> None:
    """Draw *shape* in page space."""
    cr.save()
    if shape.opacity < 1.0:
        cr.push_group()
    cr.translate(shape.x, shape.y)
    if shape.rotation:
        cr.rotate(shape.rotation)

    drawer = _DRAWERS.get(shape.kind)
    if drawer is not None:
        drawer(cr, shape, base_pixbuf)

    if shape.opacity < 1.0:
        cr.pop_group_to_source()
        cr.paint_with_alpha(shape.opacity)
    cr.restore()


def _draw_pen(cr, shape, base):
    props = shape.props
    points = props.points
    if len(points) < 2:
        return
    _set_color(cr, props.style)
    cr.set_line_width(props.style.width)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.move_to(*points[0])
    for p in points[1:]:
        cr.line_to(*p)
    if props.closed:
        cr.close_path()
    cr.stroke()


def _arrow_head(cr, tip, angle, size):
    spread = math.pi / 7
    cr.move_to(*tip)
    cr.line_to(tip[0] - size * math.cos(angle - spread),
               tip[1] - size * math.sin(angle - spread))
    cr.line_to(tip[0] - size * math.cos(angle + spread),
               tip[1] - size * math.sin(angle + spread))
    cr.close_path()
    cr.fill()


def _draw_arrow(cr, shape, base):
    props = shape.props
    style = props.style
    x1, y1 = props.end
    _set_color(cr, style)
    cr.set_line_width(style.width)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    angle = math.atan2(y1, x1)
    head = max(10.0, style.width * 4.0)

    # Stop the shaft short of each head so a heavy stroke can't poke through it.
    sx, sy = 0.0, 0.0
    ex, ey = x1, y1
    if props.head_end == "arrow":
        ex -= head * 0.6 * math.cos(angle)
        ey -= head * 0.6 * math.sin(angle)
    if props.head_start == "arrow":
        sx += head * 0.6 * math.cos(angle)
        sy += head * 0.6 * math.sin(angle)
    cr.move_to(sx, sy)
    cr.line_to(ex, ey)
    cr.stroke()

    if props.head_end == "arrow":
        _arrow_head(cr, (x1, y1), angle, head)
    if props.head_start == "arrow":
        _arrow_head(cr, (0.0, 0.0), angle + math.pi, head)
    if props.number is not None:
        _badge(cr, 0.0, 0.0, props.badge_radius, str(props.number), style)


def _draw_geo(cr, shape, base):
    props = shape.props
    if props.w < 1 or props.h < 1:
        return
    _set_color(cr, props.style)
    if props.geo == "ellipse":
        cr.save()
        cr.translate(props.w / 2, props.h / 2)
        cr.scale(props.w / 2, props.h / 2)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
    else:
        cr.rectangle(0, 0, props.w, props.h)
    if props.filled:
        cr.fill()
    else:
        cr.set_line_width(props.style.width)
        cr.stroke()


def _draw_highlight(cr, shape, base):
    props = shape.props
    r, g, b, _a = props.style.rgba
    cr.set_source_rgba(r, g, b, 0.35)
    cr.rectangle(0, 0, props.w, props.h)
    cr.fill()


def _draw_obscure(cr, shape, base):
    props = shape.props
    if base is None or props.w < 2 or props.h < 2:
        return
    bw, bh = base.get_width(), base.get_height()
    page = shape.page_bounds
    x = max(0, min(int(page.x), bw - 1))
    y = max(0, min(int(page.y), bh - 1))
    w = max(1, min(int(page.w), bw - x))
    h = max(1, min(int(page.h), bh - y))
    if w < 2 or h < 2:
        return
    big = _obscured_pixbuf(base, x, y, w, h, props.density, props.pixelate)
    if big is None:
        return
    cr.save()
    # Clip in the shape's own (possibly rotated) frame, then step back out to
    # page space so the sampled pixels land where they came from.
    cr.rectangle(0, 0, props.w, props.h)
    cr.clip()
    if shape.rotation:
        cr.rotate(-shape.rotation)
    cr.translate(-shape.x, -shape.y)
    Gdk.cairo_set_source_pixbuf(cr, big, x, y)
    cr.rectangle(x, y, w, h)
    cr.fill()
    cr.restore()


def _draw_text(cr, shape, base):
    props = shape.props
    if props.background:
        pad = props.padding
        cr.set_source_rgba(0, 0, 0, 0.45)
        rounded_rect(cr, -pad, -pad, props.w + 2 * pad, props.h + 2 * pad,
                     props.style.font_size * 0.25)
        cr.fill()
    draw_text(cr, props.text, 0, 0, props.style, outline=props.outline)


def _draw_marker(cr, shape, base):
    props = shape.props
    r = props.diameter / 2
    _badge(cr, r, r, r, str(props.number), props.style)


def _draw_bubble(cr, shape, base):
    props = shape.props
    w, h = props.w, props.h
    if w < 6 or h < 6:
        return
    radius = min(14.0, w / 3, h / 3)
    rounded_rect(cr, 0, 0, w, h, radius)
    cr.set_source_rgba(1, 1, 1, 0.96)
    cr.fill()
    # Tail, pointing down-left out of the bottom edge.
    tx = w * 0.28
    cr.move_to(tx, h)
    cr.line_to(tx + w * 0.12, h)
    cr.line_to(tx, h + props.tail_depth)
    cr.close_path()
    cr.set_source_rgba(1, 1, 1, 0.96)
    cr.fill()
    rounded_rect(cr, 0, 0, w, h, radius)
    _set_color(cr, props.style)
    cr.set_line_width(max(1.5, props.style.width))
    cr.stroke()
    pad = 8.0
    draw_text(cr, props.text, pad, pad, props.style, bold=False,
              size=props.style.font_size * 0.8, rgba=(0.1, 0.1, 0.12, 1.0))


def _draw_emoji(cr, shape, base):
    props = shape.props
    draw_text(cr, props.char, 0, 0, S.Style(font_size=props.size),
              bold=False, size=props.size, rgba=(0, 0, 0, 1))


_DRAWERS = {
    "pen": _draw_pen,
    "arrow": _draw_arrow,
    "geo": _draw_geo,
    "highlight": _draw_highlight,
    "obscure": _draw_obscure,
    "text": _draw_text,
    "marker": _draw_marker,
    "bubble": _draw_bubble,
    "emoji": _draw_emoji,
}


def flatten(base: GdkPixbuf.Pixbuf, shape_list) -> GdkPixbuf.Pixbuf:
    """Render the base plus every shape into one opaque pixbuf."""
    w, h = base.get_width(), base.get_height()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surface)
    Gdk.cairo_set_source_pixbuf(cr, base, 0, 0)
    cr.paint()
    for shape in shape_list:
        draw_shape(cr, shape, base)
    surface.flush()
    return Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)
