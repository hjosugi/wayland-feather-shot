"""The editor canvas widget.

A thin GTK layer over the editor core: it owns the base image and the camera,
turns GTK events into :class:`~.interaction.PointerInfo` values, and draws.
Everything about *what* an interaction means lives in :mod:`.interaction`, and
everything about what a shape is lives in :mod:`.shapes` — both of which are
pure Python and unit-tested.
"""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

from . import render, shapes as S  # noqa: E402
from .document import Document  # noqa: E402
from .geometry import norm_rect  # noqa: E402
from .interaction import (CORNER_HANDLES, HANDLE_UNIT, ROTATE_HANDLE_OFFSET,
                          Editor, PointerInfo, Viewport)  # noqa: E402

MIN_ZOOM = 0.1
MAX_ZOOM = 16.0
ZOOM_STEP = 1.25

HANDLE_R = 4.5          # widget px
ROTATE_HANDLE_R = 4.0
SELECTION_RGBA = (0.20, 0.60, 1.00, 0.95)


class EditorCanvas(Gtk.DrawingArea):
    def __init__(self, pixbuf: GdkPixbuf.Pixbuf, style: S.Style,
                 blur_factor: int = 8):
        super().__init__()
        self.base = pixbuf
        self.editor = Editor(Document(), style)
        self.editor.on_change = self._notify
        self.editor.base_provider = lambda: self.base
        self.editor.redaction_density = S.density_from_factor(blur_factor)

        # When True, blur/pixelate flattens the annotations below it into the
        # base first, so a redaction covers drawn annotations too.
        self.blur_composite = False
        self._crop_preview: Optional[Tuple[float, float, float, float]] = None
        self._crop_start: Optional[Tuple[float, float]] = None

        # Camera.
        self.zoom_to_fit = True
        self._manual_scale = 1.0
        self._pan = (0.0, 0.0)
        self._pan_start: Optional[Tuple[float, float, float, float]] = None

        # Set by the window: called as (img_x, img_y, widget_x, widget_y).
        self.on_request_text: Optional[Callable] = None
        self.on_request_bubble: Optional[Callable] = None
        self.on_request_emoji: Optional[Callable] = None
        self.on_changed: Optional[Callable] = None
        self.on_zoom_changed: Optional[Callable] = None

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

        pan = Gtk.GestureDrag()
        pan.set_button(2)
        pan.connect("drag-begin", self._on_pan_begin)
        pan.connect("drag-update", self._on_pan_update)
        self.add_controller(pan)

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("released", self._on_click)
        self.add_controller(click)

        scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)

        self._modifiers = Gdk.ModifierType(0)
        keys = Gtk.EventControllerKey()
        keys.connect("modifiers", self._on_modifiers)
        self.add_controller(keys)

    # -- compatibility surface used by the window ----------------------------

    @property
    def shapes(self) -> List[S.Shape]:
        return self.editor.doc.shapes

    @shapes.setter
    def shapes(self, value) -> None:
        self.editor.doc.replace_all(list(value))

    @property
    def tool(self) -> str:
        return self.editor.tool

    @tool.setter
    def tool(self, value: str) -> None:
        if value != self.editor.tool:
            self.editor.tool = value
            if value != "select":
                self.editor.doc.clear_selection()
            self.queue_draw()

    @property
    def style(self) -> S.Style:
        return self.editor.style

    @style.setter
    def style(self, value: S.Style) -> None:
        self.editor.style = value

    @property
    def selected(self) -> bool:
        return self.editor.doc.has_selection

    # -- geometry ------------------------------------------------------------

    def _fit_scale(self) -> float:
        w = max(1, self.get_width())
        h = max(1, self.get_height())
        iw, ih = self.base.get_width(), self.base.get_height()
        return min(w / iw, h / ih, 1.0)

    def _view_params(self) -> Tuple[float, float, float]:
        """(scale, offset_x, offset_y) mapping page coords to widget coords."""
        w = max(1, self.get_width())
        h = max(1, self.get_height())
        iw, ih = self.base.get_width(), self.base.get_height()
        scale = self._fit_scale() if self.zoom_to_fit else self._manual_scale
        px, py = self._clamped_pan(scale)
        ox = (w - iw * scale) / 2 + px
        oy = (h - ih * scale) / 2 + py
        return scale, ox, oy

    def _clamped_pan(self, scale: float) -> Tuple[float, float]:
        w, h = max(1, self.get_width()), max(1, self.get_height())
        iw, ih = self.base.get_width(), self.base.get_height()
        max_x = max(0.0, (iw * scale - w) / 2)
        max_y = max(0.0, (ih * scale - h) / 2)
        return (min(max(self._pan[0], -max_x), max_x),
                min(max(self._pan[1], -max_y), max_y))

    def _sync_viewport(self) -> None:
        scale, ox, oy = self._view_params()
        self.editor.viewport = Viewport(
            image_size=(float(self.base.get_width()), float(self.base.get_height())),
            scale=scale, offset=(ox, oy))

    def _to_image(self, wx: float, wy: float) -> Tuple[float, float]:
        self._sync_viewport()
        return self.editor.viewport.to_page(wx, wy)

    def _clamped_to_image(self, p) -> Tuple[float, float]:
        return (max(0.0, min(p[0], self.base.get_width())),
                max(0.0, min(p[1], self.base.get_height())))

    # -- zoom ----------------------------------------------------------------

    @property
    def zoom_percent(self) -> int:
        scale, _ox, _oy = self._view_params()
        return max(1, int(round(scale * 100)))

    def zoom_in(self):
        self._set_scale(self._current_scale() * ZOOM_STEP)

    def zoom_out(self):
        self._set_scale(self._current_scale() / ZOOM_STEP)

    def zoom_fit(self):
        self.zoom_to_fit = True
        self._pan = (0.0, 0.0)
        self._notify_zoom()

    def zoom_actual(self):
        self._set_scale(1.0)

    def _current_scale(self) -> float:
        return self._fit_scale() if self.zoom_to_fit else self._manual_scale

    def _set_scale(self, scale: float, focus: Optional[Tuple[float, float]] = None):
        old = self._current_scale()
        new = min(max(scale, MIN_ZOOM), MAX_ZOOM)
        if focus is not None and old > 0:
            # Keep the page point under the pointer where it is.
            w, h = max(1, self.get_width()), max(1, self.get_height())
            iw, ih = self.base.get_width(), self.base.get_height()
            px, py = self._clamped_pan(old)
            ox = (w - iw * old) / 2 + px
            oy = (h - ih * old) / 2 + py
            page = ((focus[0] - ox) / old, (focus[1] - oy) / old)
            self._pan = (focus[0] - (w - iw * new) / 2 - page[0] * new,
                         focus[1] - (h - ih * new) / 2 - page[1] * new)
        self._manual_scale = new
        self.zoom_to_fit = False
        self._notify_zoom()

    def _notify_zoom(self):
        self.queue_draw()
        if self.on_zoom_changed:
            self.on_zoom_changed()

    def _on_scroll(self, controller, dx, dy):
        state = controller.get_current_event_state()
        if state & Gdk.ModifierType.CONTROL_MASK:
            factor = ZOOM_STEP if dy < 0 else (1 / ZOOM_STEP if dy > 0 else 1.0)
            if factor != 1.0:
                ok, x, y = _pointer_position(controller, self)
                self._set_scale(self._current_scale() * factor,
                                (x, y) if ok else None)
            return True
        step = 60.0
        if state & Gdk.ModifierType.SHIFT_MASK:
            dx, dy = dy, dx
        self._pan = (self._pan[0] - dx * step, self._pan[1] - dy * step)
        self.queue_draw()
        return True

    def _on_pan_begin(self, gesture, x, y):
        self._pan_start = (x, y, self._pan[0], self._pan[1])

    def _on_pan_update(self, gesture, dx, dy):
        if self._pan_start is None:
            return
        _sx, _sy, px, py = self._pan_start
        self._pan = (px + dx, py + dy)
        self.queue_draw()

    # -- history -------------------------------------------------------------

    def undo(self):
        self.base = self.editor.doc.undo(self.base) or self.base
        self._notify()

    def redo(self):
        self.base = self.editor.doc.redo(self.base) or self.base
        self._notify()

    def _notify(self):
        self.queue_draw()
        if self.on_changed:
            self.on_changed()

    # -- input ---------------------------------------------------------------

    def _on_modifiers(self, _controller, state):
        self._modifiers = state
        return False

    def _pointer(self, wx: float, wy: float, state=None) -> PointerInfo:
        self._sync_viewport()
        state = self._modifiers if state is None else state
        page = self.editor.viewport.to_page(wx, wy)
        return PointerInfo(
            widget=(wx, wy), page=page,
            shift=bool(state & Gdk.ModifierType.SHIFT_MASK),
            ctrl=bool(state & Gdk.ModifierType.CONTROL_MASK),
            alt=bool(state & Gdk.ModifierType.ALT_MASK))

    def _on_drag_begin(self, gesture, x, y):
        state = gesture.get_current_event_state()
        if self.tool == "crop":
            self._crop_start = self._clamped_to_image(self._to_image(x, y))
            self._crop_preview = None
            return
        self.editor.pointer_down(self._pointer(x, y, state))

    def _on_drag_update(self, gesture, dx, dy):
        ok, sx, sy = gesture.get_start_point()
        if not ok:
            return
        state = gesture.get_current_event_state()
        if self.tool == "crop":
            if self._crop_start is None:
                return
            cur = self._clamped_to_image(self._to_image(sx + dx, sy + dy))
            self._crop_preview = norm_rect(*self._crop_start, *cur)
            self.queue_draw()
            return
        self.editor.pointer_move(self._pointer(sx + dx, sy + dy, state))

    def _on_drag_end(self, gesture, dx, dy):
        ok, sx, sy = gesture.get_start_point()
        state = gesture.get_current_event_state()
        if self.tool == "crop":
            crop, self._crop_preview = self._crop_preview, None
            self._crop_start = None
            if crop and crop[2] >= 4 and crop[3] >= 4:
                self.apply_crop(crop)
            else:
                self.queue_draw()
            return
        if not ok:
            return
        pointer = self._pointer(sx + dx, sy + dy, state)
        doc = self.editor.doc
        composite = self.blur_composite and self.tool in ("blur", "pixelate")
        in_flight = doc.shapes[-1].sid if composite and doc.shapes else None
        self.editor.pointer_up(pointer)
        # Only once the redaction has actually survived the release: a click
        # without a drag is thrown away, and flattening for it would bake the
        # annotations in for nothing.
        if in_flight and doc.shape(in_flight) is not None:
            self._flatten_under_redaction(in_flight)

    def _flatten_under_redaction(self, sid: str) -> None:
        """Bake the annotations below a redaction into the base, so the
        redaction covers them too rather than only the photo underneath.

        The undo snapshot taken when the drag started carries the untouched
        base, so this stays a single reversible step.
        """
        doc = self.editor.doc
        index = doc.index_of(sid)
        if index is None or index == 0:
            return  # nothing underneath to bake in
        below, rest = doc.shapes[:index], doc.shapes[index:]
        self.base = render.flatten(self.base, below)
        doc.shapes = list(rest)

    def _on_click(self, gesture, n_press, x, y):
        if self.tool not in ("text", "marker", "bubble", "emoji"):
            return
        pointer = self._pointer(x, y, gesture.get_current_event_state())
        request = self.editor.click(pointer)
        if request is None:
            return
        ix, iy = pointer.page
        callback = {"text": self.on_request_text,
                    "bubble": self.on_request_bubble,
                    "emoji": self.on_request_emoji}.get(request)
        if callback:
            callback(ix, iy, x, y)

    # -- placing shapes from the window's popovers ---------------------------

    def add_text(self, ix, iy, text, outline=True, background=False):
        if not text.strip():
            return
        self.editor.add_shape(S.Text((ix, iy), text, self.editor.page_style,
                                     outline=outline, background=background))

    def add_bubble(self, ix, iy, text, w=170.0, h=74.0):
        if not text.strip():
            return
        self.editor.add_shape(
            S.SpeechBubble((ix, iy, w, h), text, self.editor.page_style))

    def add_emoji(self, ix, iy, char):
        if not char:
            return
        self.editor.add_shape(
            S.EmojiSticker((ix, iy), char, self.editor.page_style))

    # -- selection actions ---------------------------------------------------

    def delete_selected(self) -> bool:
        doc = self.editor.doc
        if not doc.has_selection:
            return False
        doc.mark_undo(self.base)
        doc.delete_selected()
        self._notify()
        return True

    def restyle_selected(self, style: S.Style) -> bool:
        doc = self.editor.doc
        if not doc.has_selection:
            return False
        page_style = S.Style(rgba=style.rgba, font_size=style.font_size,
                             font_family=style.font_family,
                             width=S.page_stroke_width(
                                 style.width, self.editor.viewport.image_edge))
        doc.mark_undo(self.base)
        if not doc.restyle_selected(page_style):
            doc.cancel_undo()
            return False
        self._notify()
        return True

    def nudge_selected(self, dx: float, dy: float) -> bool:
        doc = self.editor.doc
        if not doc.has_selection:
            return False
        doc.mark_undo(self.base)
        doc.nudge_selected(dx, dy)
        self._notify()
        return True

    def select_all(self) -> bool:
        if not self.shapes:
            return False
        self.editor.doc.select_all()
        self.tool = "select"
        self._notify()
        return True

    def raise_selected(self) -> bool:
        return self._reorder(self.editor.doc.bring_to_front)

    def lower_selected(self) -> bool:
        return self._reorder(self.editor.doc.send_to_back)

    def _reorder(self, action) -> bool:
        doc = self.editor.doc
        if not doc.has_selection:
            return False
        doc.mark_undo(self.base)
        action()
        self._notify()
        return True

    # -- crop ----------------------------------------------------------------

    def apply_crop(self, rect):
        x, y, w, h = (int(v) for v in rect)
        bw, bh = self.base.get_width(), self.base.get_height()
        x = max(0, min(x, bw - 1))
        y = max(0, min(y, bh - 1))
        w = max(1, min(w, bw - x))
        h = max(1, min(h, bh - y))
        self.editor.doc.mark_undo(self.base)
        self.base = self.base.new_subpixbuf(x, y, w, h).copy()
        self.editor.doc.translate_all(-x, -y)
        self._notify()

    # -- rendering -----------------------------------------------------------

    def _draw(self, area, cr, w, h, _data):
        cr.set_source_rgb(0.13, 0.13, 0.15)
        cr.paint()
        scale, ox, oy = self._view_params()
        self._sync_viewport()

        cr.save()
        cr.translate(ox, oy)
        cr.scale(scale, scale)
        self._render_content(cr)
        cr.restore()

        self._draw_chrome(cr, scale, ox, oy)

    def _render_content(self, cr):
        Gdk.cairo_set_source_pixbuf(cr, self.base, 0, 0)
        cr.paint()
        for shape in self.shapes:
            render.draw_shape(cr, shape, self.base)

    def _draw_chrome(self, cr, scale, ox, oy):
        """Selection frame, handles, marquee and crop preview — drawn in widget
        space so they stay the same size at every zoom level."""
        if self._crop_preview:
            x, y, cw, ch = self._crop_preview
            cr.save()
            cr.set_source_rgba(0.3, 0.7, 1.0, 0.95)
            cr.set_line_width(2.0)
            cr.set_dash([6.0, 4.0])
            cr.rectangle(ox + x * scale, oy + y * scale, cw * scale, ch * scale)
            cr.stroke()
            cr.restore()

        brush = self.editor.brush
        if brush is not None and (brush.w or brush.h):
            cr.save()
            cr.set_source_rgba(*SELECTION_RGBA)
            cr.set_line_width(1.0)
            cr.set_dash([4.0, 3.0])
            cr.rectangle(ox + brush.x * scale, oy + brush.y * scale,
                         brush.w * scale, brush.h * scale)
            cr.stroke()
            cr.set_source_rgba(0.2, 0.6, 1.0, 0.12)
            cr.rectangle(ox + brush.x * scale, oy + brush.y * scale,
                         brush.w * scale, brush.h * scale)
            cr.fill()
            cr.restore()

        if self.tool != "select":
            return
        frame = self.editor.selection_frame
        if frame is None:
            return

        corners = [self.editor.viewport.to_widget(p) for p in frame.page_corners]
        cr.save()
        cr.set_source_rgba(*SELECTION_RGBA)
        cr.set_line_width(1.5)
        cr.set_dash([5.0, 3.0])
        cr.move_to(*corners[0])
        for p in corners[1:]:
            cr.line_to(*p)
        cr.close_path()
        cr.stroke()
        cr.set_dash([])

        multi = len(self.editor.doc.selected) > 1
        for handle, (u, v) in HANDLE_UNIT.items():
            x, y = self.editor.viewport.to_widget(frame.unit_point(u, v))
            cr.set_source_rgb(1, 1, 1)
            cr.rectangle(x - HANDLE_R, y - HANDLE_R, HANDLE_R * 2, HANDLE_R * 2)
            cr.fill_preserve()
            cr.set_source_rgba(*SELECTION_RGBA)
            cr.set_line_width(1.0)
            cr.stroke()

        center = self.editor.viewport.to_widget(frame.page_center)
        for corner in CORNER_HANDLES:
            u, v = HANDLE_UNIT[corner]
            x, y = self.editor.viewport.to_widget(frame.unit_point(u, v))
            dx, dy = x - center[0], y - center[1]
            length = math.hypot(dx, dy) or 1.0
            rx = x + dx / length * ROTATE_HANDLE_OFFSET
            ry = y + dy / length * ROTATE_HANDLE_OFFSET
            cr.set_source_rgba(*SELECTION_RGBA)
            cr.arc(rx, ry, ROTATE_HANDLE_R, 0, 2 * math.pi)
            cr.fill()
        cr.restore()

    # -- export --------------------------------------------------------------

    def export_pixbuf(self) -> GdkPixbuf.Pixbuf:
        return render.flatten(self.base, self.shapes)


def _pointer_position(controller, widget) -> Tuple[bool, float, float]:
    event = controller.get_current_event()
    if event is None:
        return (False, 0.0, 0.0)
    ok, x, y = event.get_position()
    if not ok:
        return (False, 0.0, 0.0)
    surface_widget = widget.get_native()
    if surface_widget is None:
        return (True, x, y)
    ok2, wx, wy = surface_widget.translate_coordinates(widget, x, y)
    return (True, wx, wy) if ok2 else (True, x, y)
