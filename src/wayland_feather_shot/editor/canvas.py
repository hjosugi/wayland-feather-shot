"""Editor canvas: renders the capture plus annotations, handles tool input,
and owns undo/redo history."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

import cairo  # noqa: E402

from . import tools
from .tools import (Arrow, EllipseShape, Highlight, Line, Marker, Obscure,
                    Pen, RectShape, Shape, Style, Text)

RECT_TOOLS = {"rect", "ellipse", "highlight", "blur", "pixelate", "crop"}
DRAG_TOOLS = RECT_TOOLS | {"pen", "line", "arrow"}
CLICK_TOOLS = {"text", "marker"}


class EditorCanvas(Gtk.DrawingArea):
    def __init__(self, pixbuf: GdkPixbuf.Pixbuf, style: Style, blur_factor: int = 8):
        super().__init__()
        self.base = pixbuf
        self.shapes: List[Shape] = []
        self.style = style
        self.blur_factor = blur_factor
        self.tool = "pen"
        self._undo: List[Tuple[GdkPixbuf.Pixbuf, tuple]] = []
        self._redo: List[Tuple[GdkPixbuf.Pixbuf, tuple]] = []
        self._drag_start: Optional[Tuple[float, float]] = None
        self._pen_points: List[Tuple[float, float]] = []
        self._preview: Optional[Shape] = None
        self._crop_preview: Optional[Tuple[float, float, float, float]] = None

        # Set by the window: called as (img_x, img_y, widget_x, widget_y).
        self.on_request_text: Optional[Callable] = None
        self.on_changed: Optional[Callable] = None

        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_focusable(True)
        self.set_draw_func(self._draw, None)
        self.set_cursor(Gdk.Cursor.new_from_name("crosshair"))

        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("released", self._on_click)
        self.add_controller(click)

    # -- geometry ------------------------------------------------------------

    def _view_params(self) -> Tuple[float, float, float]:
        """(scale, offset_x, offset_y) mapping image coords to widget coords."""
        w = max(1, self.get_width())
        h = max(1, self.get_height())
        iw, ih = self.base.get_width(), self.base.get_height()
        scale = min(w / iw, h / ih, 1.0)
        ox = (w - iw * scale) / 2
        oy = (h - ih * scale) / 2
        return scale, ox, oy

    def _to_image(self, wx: float, wy: float) -> Tuple[float, float]:
        scale, ox, oy = self._view_params()
        ix = (wx - ox) / scale
        iy = (wy - oy) / scale
        return (max(0.0, min(ix, self.base.get_width())),
                max(0.0, min(iy, self.base.get_height())))

    # -- history ---------------------------------------------------------------

    def _push_history(self):
        self._undo.append((self.base, tuple(self.shapes)))
        if len(self._undo) > 100:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self):
        if not self._undo:
            return
        self._redo.append((self.base, tuple(self.shapes)))
        self.base, shapes = self._undo.pop()
        self.shapes = list(shapes)
        self._notify()

    def redo(self):
        if not self._redo:
            return
        self._undo.append((self.base, tuple(self.shapes)))
        self.base, shapes = self._redo.pop()
        self.shapes = list(shapes)
        self._notify()

    def _notify(self):
        self.queue_draw()
        if self.on_changed:
            self.on_changed()

    # -- input -----------------------------------------------------------------

    def _on_drag_begin(self, gesture, x, y):
        if self.tool not in DRAG_TOOLS:
            return
        self._drag_start = self._to_image(x, y)
        if self.tool == "pen":
            self._pen_points = [self._drag_start]

    def _on_drag_update(self, gesture, dx, dy):
        if self._drag_start is None:
            return
        ok, sx, sy = gesture.get_start_point()
        if not ok:
            return
        cur = self._to_image(sx + dx, sy + dy)
        self._update_preview(cur)
        self.queue_draw()

    def _on_drag_end(self, gesture, dx, dy):
        if self._drag_start is None:
            return
        ok, sx, sy = gesture.get_start_point()
        cur = self._to_image(sx + dx, sy + dy) if ok else self._drag_start
        self._update_preview(cur)
        start, self._drag_start = self._drag_start, None
        preview, self._preview = self._preview, None
        crop, self._crop_preview = self._crop_preview, None
        self._pen_points = []

        if self.tool == "crop":
            if crop and crop[2] >= 4 and crop[3] >= 4:
                self._apply_crop(crop)
            else:
                self.queue_draw()
            return
        if preview is not None:
            self._push_history()
            self.shapes.append(preview)
            self._notify()
        else:
            self.queue_draw()

    def _update_preview(self, cur: Tuple[float, float]):
        start = self._drag_start
        tool = self.tool
        if tool == "pen":
            last = self._pen_points[-1]
            if abs(cur[0] - last[0]) + abs(cur[1] - last[1]) >= 1.5:
                self._pen_points.append(cur)
            self._preview = Pen(tuple(self._pen_points), self.style)
        elif tool == "line":
            self._preview = Line(start, cur, self.style)
        elif tool == "arrow":
            self._preview = Arrow(start, cur, self.style)
        elif tool in RECT_TOOLS:
            rect = tools.norm_rect(start[0], start[1], cur[0], cur[1])
            if tool == "rect":
                self._preview = RectShape(rect, self.style)
            elif tool == "ellipse":
                self._preview = EllipseShape(rect, self.style)
            elif tool == "highlight":
                self._preview = Highlight(rect, self.style)
            elif tool == "blur":
                self._preview = Obscure(rect, self.blur_factor, pixelate=False)
            elif tool == "pixelate":
                self._preview = Obscure(rect, self.blur_factor, pixelate=True)
            elif tool == "crop":
                self._preview = None
                self._crop_preview = rect

    def _on_click(self, gesture, n_press, x, y):
        if self.tool not in CLICK_TOOLS:
            return
        ix, iy = self._to_image(x, y)
        if self.tool == "marker":
            number = sum(1 for s in self.shapes if isinstance(s, Marker)) + 1
            self._push_history()
            self.shapes.append(Marker((ix, iy), number, self.style))
            self._notify()
        elif self.tool == "text" and self.on_request_text:
            self.on_request_text(ix, iy, x, y)

    def add_text(self, ix: float, iy: float, text: str):
        if not text.strip():
            return
        self._push_history()
        self.shapes.append(Text((ix, iy), text, self.style))
        self._notify()

    # -- crop --------------------------------------------------------------------

    def _apply_crop(self, rect):
        x, y, w, h = (int(v) for v in rect)
        bw, bh = self.base.get_width(), self.base.get_height()
        x = max(0, min(x, bw - 1))
        y = max(0, min(y, bh - 1))
        w = max(1, min(w, bw - x))
        h = max(1, min(h, bh - y))
        self._push_history()
        self.base = self.base.new_subpixbuf(x, y, w, h).copy()
        self.shapes = [s.translate(-x, -y) for s in self.shapes]
        self._notify()

    # -- rendering ---------------------------------------------------------------

    def _draw(self, area, cr, w, h, _data):
        cr.set_source_rgb(0.13, 0.13, 0.15)
        cr.paint()
        scale, ox, oy = self._view_params()
        cr.save()
        cr.translate(ox, oy)
        cr.scale(scale, scale)
        self._render_content(cr)
        cr.restore()

        if self._crop_preview:
            x, y, cw, ch = self._crop_preview
            cr.save()
            cr.translate(ox, oy)
            cr.scale(scale, scale)
            cr.set_source_rgba(0.3, 0.7, 1.0, 0.95)
            cr.set_line_width(2.0 / scale)
            cr.set_dash([6.0 / scale, 4.0 / scale])
            cr.rectangle(x, y, cw, ch)
            cr.stroke()
            cr.restore()

    def _render_content(self, cr):
        Gdk.cairo_set_source_pixbuf(cr, self.base, 0, 0)
        cr.paint()
        for shape in self.shapes:
            shape.draw(cr, self.base)
        if self._preview is not None:
            self._preview.draw(cr, self.base)

    def export_pixbuf(self) -> GdkPixbuf.Pixbuf:
        w, h = self.base.get_width(), self.base.get_height()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(surface)
        Gdk.cairo_set_source_pixbuf(cr, self.base, 0, 0)
        cr.paint()
        for shape in self.shapes:
            shape.draw(cr, self.base)
        surface.flush()
        return Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)
