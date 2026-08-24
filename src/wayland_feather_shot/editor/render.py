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
from collections import OrderedDict
from typing import List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GdkPixbuf, Pango, PangoCairo  # noqa: E402

import cairo  # noqa: E402

from . import arrows  # noqa: E402
from . import freehand  # noqa: E402
from . import shapes as S  # noqa: E402

_scratch_cr: Optional[cairo.Context] = None


def _scratch() -> cairo.Context:
    """A 1x1 context used only for measuring."""
    global _scratch_cr
    if _scratch_cr is None:
        _scratch_cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
    return _scratch_cr


# -- text --------------------------------------------------------------------

_ALIGNMENTS = {
    "left": Pango.Alignment.LEFT,
    "center": Pango.Alignment.CENTER,
    "right": Pango.Alignment.RIGHT,
}


def make_layout(cr, text: str, style: S.Style, bold: bool = True,
                size: Optional[float] = None, wrap_width: float = 0.0,
                align: str = "left"):
    layout = PangoCairo.create_layout(cr)
    desc = Pango.FontDescription()
    desc.set_family(style.font_family or "Sans")
    desc.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
    # Absolute size means device units, i.e. image pixels — the same units the
    # rest of the model works in.
    desc.set_absolute_size(max(1.0, size if size is not None else style.font_size)
                           * Pango.SCALE)
    layout.set_font_description(desc)
    if wrap_width > 0:
        layout.set_width(int(wrap_width * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    layout.set_alignment(_ALIGNMENTS.get(align, Pango.Alignment.LEFT))
    layout.set_text(text, -1)
    return layout


def measure(text: str, style: S.Style, bold: bool = True,
            size: Optional[float] = None,
            wrap_width: float = 0.0) -> Tuple[float, float]:
    layout = make_layout(_scratch(), text, style, bold=bold, size=size,
                         wrap_width=wrap_width)
    _ink, logical = layout.get_pixel_extents()
    # A wrapped box keeps the width it was given, so the box does not snap to
    # the longest line every time a word moves between rows.
    width = wrap_width if wrap_width > 0 else float(logical.width)
    return (width, float(logical.height))


S.set_text_measurer(
    lambda text, style, wrap_width=0.0: measure(text, style,
                                                wrap_width=wrap_width))


def draw_text(cr, text: str, x: float, y: float, style: S.Style,
              bold: bool = True, size: Optional[float] = None,
              rgba: Optional[Tuple[float, float, float, float]] = None,
              outline: bool = False, wrap_width: float = 0.0,
              align: str = "left") -> None:
    """Draw *text* with its top-left at (x, y)."""
    if not text:
        return
    layout = make_layout(cr, text, style, bold=bold, size=size,
                         wrap_width=wrap_width, align=align)
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


# Committed strokes get redrawn on every frame - panning, drawing something
# else, moving another shape - and re-running the whole pipeline for ink that
# has not moved is pure waste.  Keyed on the payload's identity, which is
# stable because the payloads are frozen.
_OUTLINE_CACHE: "OrderedDict[Tuple[int, int, float], List[Tuple[float, float]]]" = OrderedDict()
_OUTLINE_CACHE_LIMIT = 128


def pen_outline(props) -> List[Tuple[float, float]]:
    key = (id(props), len(props.points), props.style.width)
    cached = _OUTLINE_CACHE.get(key)
    if cached is not None:
        _OUTLINE_CACHE.move_to_end(key)
        return cached
    outline = freehand.get_stroke(props.points, props.stroke_options())
    _OUTLINE_CACHE[key] = outline
    if len(_OUTLINE_CACHE) > _OUTLINE_CACHE_LIMIT:
        _OUTLINE_CACHE.popitem(last=False)
    return outline


def _smooth_closed_path(cr, points) -> None:
    """Trace a closed polygon as quadratic curves through its midpoints.

    Filling the raw outline shows every vertex as a facet; running the curve
    through the midpoints instead is what makes the ink read as ink.
    """
    if len(points) < 3:
        return
    mid = _midpoint(points[-1], points[0])
    cr.move_to(*mid)
    for i in range(len(points)):
        control = points[i]
        end = _midpoint(control, points[(i + 1) % len(points)])
        _quad_to(cr, control, end)
    cr.close_path()


def _midpoint(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _quad_to(cr, control, end) -> None:
    """Cairo only has cubics, so raise the quadratic's degree."""
    start = cr.get_current_point()
    cr.curve_to(start[0] + 2 / 3 * (control[0] - start[0]),
                start[1] + 2 / 3 * (control[1] - start[1]),
                end[0] + 2 / 3 * (control[0] - end[0]),
                end[1] + 2 / 3 * (control[1] - end[1]),
                end[0], end[1])


def _draw_pen(cr, shape, base):
    props = shape.props
    if len(props.points) < 2:
        return
    outline = pen_outline(props)
    if len(outline) < 3:
        return
    _set_color(cr, props.style)
    _smooth_closed_path(cr, outline)
    cr.set_fill_rule(cairo.FILL_RULE_WINDING)
    cr.fill()


def _draw_head(cr, style_name: str, tip, angle: float, style) -> None:
    kind, points = arrows.head_path(style_name, tip, angle, style.width)
    if len(points) < 2:
        return
    cr.move_to(*points[0])
    for p in points[1:]:
        cr.line_to(*p)
    if kind == "fill":
        cr.close_path()
        cr.fill()
    else:
        if kind == "outline":
            cr.close_path()
        cr.set_line_width(style.width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.stroke()


def _draw_arrow(cr, shape, base):
    props = shape.props
    style = props.style
    start, end = props.start, props.end
    _set_color(cr, style)
    cr.set_line_width(style.width)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)

    # Trim the shaft by each head's own length, so a heavy stroke stops exactly
    # where the head starts instead of poking out through the tip.
    shaft = arrows.trimmed(
        start, end, props.bend,
        start_trim=arrows.head_length(props.head_start, style.width),
        end_trim=arrows.head_length(props.head_end, style.width))
    if len(shaft) >= 2:
        cr.move_to(*shaft[0])
        for p in shaft[1:]:
            cr.line_to(*p)
        cr.stroke()

    # On a bent arrow the head follows the tangent, not the chord.
    _draw_head(cr, props.head_end, end,
               arrows.direction_at(start, end, props.bend, at_end=True), style)
    _draw_head(cr, props.head_start, start,
               arrows.direction_at(start, end, props.bend, at_end=False), style)

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
    draw_text(cr, props.text, 0, 0, props.style, outline=props.outline,
              wrap_width=props.effective_wrap, align=props.align)


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


def _draw_spotlight(cr, shape, base):
    """Nothing: the scrim pass in :func:`draw_scene` handles spotlights.

    Drawing one here would darken each region separately, and two overlapping
    spotlights would double-darken where they meet — the opposite of what a
    spotlight means.
    """


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
    "spotlight": _draw_spotlight,
}


def draw_scrim(cr, spotlights, width: float, height: float) -> None:
    """Dim everything outside the union of the spotlight regions.

    Painted into a group and then cleared through, rather than drawn with a
    fill rule: with even-odd or winding, the overlap of two spotlights lands
    back inside the dimmed area.  Clearing is idempotent, so overlapping
    regions leave a single bright union — which is what a spotlight is for.
    """
    if not spotlights:
        return
    alpha = max(min(max(s.props.scrim, 0.0), 1.0) for s in spotlights)
    if alpha <= 0:
        return

    cr.save()
    cr.push_group()
    cr.set_source_rgba(0, 0, 0, alpha)
    cr.rectangle(0, 0, width, height)
    cr.fill()
    cr.set_operator(cairo.OPERATOR_CLEAR)
    for shape in spotlights:
        cr.save()
        cr.translate(shape.x, shape.y)
        if shape.rotation:
            cr.rotate(shape.rotation)
        cr.rectangle(0, 0, shape.props.w, shape.props.h)
        cr.fill()
        cr.restore()
    cr.pop_group_to_source()
    cr.paint()
    cr.restore()


def draw_scene(cr, base, shape_list, skip_sid=None) -> None:
    """Base image, then the spotlight scrim, then the annotations.

    The scrim sits between them on purpose: an arrow drawn over a dimmed area
    stays at full contrast, which is the whole point of pointing at something.
    """
    Gdk.cairo_set_source_pixbuf(cr, base, 0, 0)
    cr.paint()
    spotlights = [s for s in shape_list if s.kind == "spotlight"]
    draw_scrim(cr, spotlights, base.get_width(), base.get_height())
    for shape in shape_list:
        if shape.sid != skip_sid:
            draw_shape(cr, shape, base)


def flatten(base: GdkPixbuf.Pixbuf, shape_list) -> GdkPixbuf.Pixbuf:
    """Render the base plus every shape into one opaque pixbuf."""
    w, h = base.get_width(), base.get_height()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surface)
    draw_scene(cr, base, shape_list)
    surface.flush()
    return Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)
