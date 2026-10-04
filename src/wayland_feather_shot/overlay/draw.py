"""Drawing the region overlay, once per frame.

The screenshot with its finished annotations (a cached texture), the shape
being drawn or moved, the dimmed outside, the selection with its handles and
size label, and the hint. A mixin of
overlay.window.OverlayWindow.
"""

from __future__ import annotations

import math

import gi

gi.require_version("Gsk", "4.0")
from gi.repository import Gsk  # noqa: E402

import cairo  # noqa: E402

from ..editor import arrows, render
from ..i18n import _
from .canvas import color, dim_outside, rect
from .layout import position_label
from .view import HANDLE_R

OVERLAY_DIM_ALPHA = 0.32


class OverlayDrawMixin:
    def _snapshot(self, _area, snapshot, w, h):
        """Draw one frame of the overlay, bottom to top:

        1. the screenshot with the finished annotations, as one texture
           that is rebuilt only when the annotations change (canvas.py);
        2. the shape being drawn, or the shapes being moved, live;
        3. the dimmed outside, with the selection left bright;
        4. the frames of the hand's picked shapes;
        5. the selection's border, handles and size label, or the hint
           when there is no selection yet.
        """
        # 1. Black letterbox, then the screenshot and finished annotations.
        snapshot.append_color(color(0, 0, 0), rect(0, 0, w, h))
        scale, ox, oy = self._view_params()
        image_bounds = rect(ox, oy, self.pixbuf.get_width() * scale,
                            self.pixbuf.get_height() * scale)
        snapshot.append_texture(self._scene.content(self.shapes), image_bounds)

        # 2. The shapes in progress.
        for shape in self._live_shapes():
            self._draw_live(snapshot, shape, scale, ox, oy, image_bounds)

        # 3. Dim everything but the selection (its widget rectangle, or None
        # to dim it all).
        selection = None
        if self.sel:
            x, y, sw, sh = self.sel
            wx0, wy0 = self._to_widget(x, y)
            wx1, wy1 = self._to_widget(x + sw, y + sh)
            # On a fractional scale (125 %, 150 %) snap the edges to device
            # pixels, or the dim mask leaves a bright seam beside them.
            ds = self._device_scale()
            if abs(ds - round(ds)) > 0.01:
                wx0 = round(wx0 * ds) / ds
                wy0 = round(wy0 * ds) / ds
                wx1 = round(wx1 * ds) / ds
                wy1 = round(wy1 * ds) / ds
            selection = wx0, wy0, wx1, wy1
        dim_outside(snapshot, w, h, selection, OVERLAY_DIM_ALPHA)

        # 4. The hand's picked shapes: their frame and handles.
        self._draw_pick_frame(snapshot)

        # 5. The selection's frame, handles and size, or the hint.
        if selection:
            purple = color(0.55, 0.07, 0.68, 0.95)
            outline = Gsk.RoundedRect()
            outline.init_from_rect(rect(wx0 - .25, wy0 - .25,
                                        wx1 - wx0 + 1.5, wy1 - wy0 + 1.5), 0)
            snapshot.append_border(outline, [1.5] * 4, [purple] * 4)
            for hx, hy in self._handles().values():
                bounds = rect(hx - HANDLE_R, hy - HANDLE_R,
                              HANDLE_R * 2, HANDLE_R * 2)
                circle = Gsk.RoundedRect()
                circle.init_from_rect(bounds, HANDLE_R)
                snapshot.push_rounded_clip(circle)
                snapshot.append_color(purple, bounds)
                snapshot.pop()

            # The size goes with the selection's own monitor, like the bars;
            # another monitor's window would pin it to its edge.
            if self._view is self._home_view():
                self._draw_size_label(snapshot, w, h, selection, sw, sh)
        else:
            hint = (_("Drag: copy area   •   Click / Enter: copy full "
                      "screen   •   Esc: cancel") if self.copy_on_select else
                    _("Drag: select area   •   Click / Enter: full screen"
                      "   •   Esc: cancel"))
            ext = self._text_extents(hint, 15, False)
            hx, hy = (w - ext.width) / 2, 42.0
            bounds = rect(hx - 14, hy - ext.height - 8,
                          math.ceil(ext.width + 28),
                          math.ceil(ext.height + 18))
            cr = snapshot.append_cairo(bounds)
            cr.set_source_rgba(0, 0, 0, .65)
            cr.rectangle(hx - 14, hy - ext.height - 8,
                         ext.width + 28, ext.height + 18)
            cr.fill()
            self._paint_text(cr, hint, hx, hy, 15, False)
            del cr

    def _draw_live(self, snapshot, shape, scale, ox, oy, image_bounds):
        """One shape drawn on its own over the cached composite."""
        if shape.kind == "spotlight" or (shape.kind == "obscure"
                                         and not shape.props.pixelate):
            # A blur re-samples the screenshot on every frame, which made
            # dragging one out or carrying it with the hand stutter; show its
            # footprint while it moves and render the real thing on release.
            # A spotlight's scrim covers the whole screenshot, so it too is
            # rendered on release.
            box = shape.page_bounds
            footprint = rect(ox + box.x * scale, oy + box.y * scale,
                             box.w * scale, box.h * scale)
            snapshot.push_clip(image_bounds)
            snapshot.append_color(color(1, 1, 1, 0.3), footprint)
            outline = Gsk.RoundedRect()
            outline.init_from_rect(footprint, 0)
            snapshot.append_border(outline, [1.5] * 4,
                                   [color(1, 1, 1, 0.9)] * 4)
            snapshot.pop()
            return
        # The annotation renderer, restricted to the shape's bounds.
        box = shape.page_bounds
        width = shape.style.width if shape.style is not None else 0
        padding = max(2, width * scale)
        if shape.kind == "arrow":
            # The model's bounds describe the shaft, not its arrowheads.
            props = shape.props
            padding = max(padding, scale * max(
                arrows.head_size(props.head_start, props.style.width),
                arrows.head_size(props.head_end, props.style.width)))
        bounds = rect(ox + box.x * scale - padding,
                      oy + box.y * scale - padding,
                      box.w * scale + 2 * padding,
                      box.h * scale + 2 * padding)
        snapshot.push_clip(image_bounds)
        cr = snapshot.append_cairo(bounds)
        cr.translate(ox, oy)
        cr.scale(scale, scale)
        with render.uncached_obscure():
            shape.draw(cr, self.pixbuf)
        del cr
        snapshot.pop()

    def _draw_size_label(self, snapshot, w, h, selection, sw, sh):
        label = f"{sw} × {sh}"
        framed = self._framed_size()
        if framed is not None:
            label += f"  »  {framed[0]} × {framed[1]}"
        ext = self._text_extents(label, 13, True)
        label_x, label_y = position_label(
            (w, h), selection,
            (math.ceil(ext.width + 10), math.ceil(ext.height + 9)),
            self._bar_rects if self._bars_visible
            and self._view is self._bars_view else (),
        )
        bounds = rect(label_x, label_y,
                      math.ceil(ext.width + 10), math.ceil(ext.height + 9))
        cr = snapshot.append_cairo(bounds)
        cr.set_source_rgba(0, 0, 0, .7)
        cr.rectangle(label_x, label_y, ext.width + 10, ext.height + 9)
        cr.fill()
        self._paint_text(cr, label, label_x + 5,
                         label_y + ext.height + 4, 13, True)
        del cr

    # Small Cairo text helpers for the size label and the hint, which are
    # chrome rather than annotations: plain Sans, white, no Pango layout.

    @staticmethod
    def _text_extents(text, size, bold):
        cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD if bold
                            else cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(size)
        return cr.text_extents(text)

    @staticmethod
    def _paint_text(cr, text, x, y, size, bold):
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD if bold
                            else cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(size)
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(x, y)
        cr.show_text(text)
