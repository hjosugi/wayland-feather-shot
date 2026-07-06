"""Flameshot-style capture overlay.

Wayland does not let arbitrary apps draw over other clients reliably across
compositors, so we do it the robust way: the portal hands us a frozen
full-screen image, we display it fullscreen, and everything happens on that
frozen image — drag-select with resize handles, then annotate in place with
a floating toolbar attached to the selection, then Ctrl+S / Ctrl+C.
"""

from __future__ import annotations

import os
from typing import Callable, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

import cairo  # noqa: E402

from . import save as save_mod
from .editor import tools
from .editor.tools import (Arrow, EllipseShape, Highlight, Line, Marker,
                           Obscure, Pen, RectShape, Style, Text)
from .i18n import _, tr

Rect = Tuple[int, int, int, int]

HANDLE_R = 6.0        # visual radius of resize handles (widget px)
HANDLE_HIT = 14.0     # hit-test radius

OVERLAY_TOOLS = [
    ("move", "Move", "Move / resize selection (V)"),
    ("pen", "Pen", "Freehand pen (P)"),
    ("line", "Line", "Straight line (L)"),
    ("arrow", "Arrow", "Arrow (A)"),
    ("rect", "Rect", "Rectangle (R)"),
    ("ellipse", "Ellipse", "Ellipse (E)"),
    ("highlight", "High", "Highlighter (H)"),
    ("text", "Text", "Text — click to place (T)"),
    ("blur", "Blur", "Blur region (B)"),
    ("pixelate", "Pixel", "Pixelate region (X)"),
    ("marker", "①②③", "Numbered marker — click (M)"),
]

TOOL_KEYS = {
    Gdk.KEY_v: "move", Gdk.KEY_p: "pen", Gdk.KEY_l: "line",
    Gdk.KEY_a: "arrow", Gdk.KEY_r: "rect", Gdk.KEY_e: "ellipse",
    Gdk.KEY_h: "highlight", Gdk.KEY_t: "text", Gdk.KEY_b: "blur",
    Gdk.KEY_x: "pixelate", Gdk.KEY_m: "marker",
}

RECT_TOOLS = {"rect", "ellipse", "highlight", "blur", "pixelate"}


class OverlayWindow(Gtk.ApplicationWindow):
    """Fullscreen frozen-image capture UI.

    open_editor(pixbuf, shapes) — optional callback used by the
    "open in editor window" button; receives the cropped base image and the
    annotation shapes translated into its coordinates.
    """

    def __init__(self, app, pixbuf: GdkPixbuf.Pixbuf, settings,
                 open_editor: Optional[Callable] = None):
        super().__init__(application=app, title="Feather Shot")
        self.pixbuf = pixbuf
        self.settings = settings
        self.open_editor = open_editor

        rgba = Gdk.RGBA()
        rgba.parse(settings.pen_color)
        self.style = Style(rgba=(rgba.red, rgba.green, rgba.blue, rgba.alpha),
                           width=float(settings.pen_width),
                           font_size=float(settings.font_size))
        self.blur_factor = int(settings.blur_factor)

        self.mode = "select"          # "select" -> "edit"
        self.tool = "move"
        self.sel: Optional[Rect] = None        # image coords
        self.shapes: List = []
        self._undo: List[tuple] = []
        self._redo: List[tuple] = []
        self._drag_kind: Optional[str] = None  # select|move|resize|draw
        self._prev_sel: Optional[Rect] = None
        self._drag_handle: Optional[str] = None
        self._drag_sel0: Optional[Rect] = None
        self._drag_start_img: Optional[Tuple[float, float]] = None
        self._pen_points: List[Tuple[float, float]] = []
        self._preview = None

        self._build_ui()
        self.set_decorated(False)
        self.fullscreen()

    # ---------------------------------------------------------------- UI --

    def _build_ui(self):
        self._root = Gtk.Overlay()
        self.set_child(self._root)

        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self._draw, None)
        self.area.set_cursor(Gdk.Cursor.new_from_name("crosshair"))
        self._root.set_child(self.area)

        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.area.add_controller(drag)

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("released", self._on_click)
        self.area.add_controller(click)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        self._install_css()
        self._toolbar = self._build_toolbar()
        self._sidebar = self._build_sidebar()
        self._toast = Gtk.Label()
        self._toast.add_css_class("wfs-toast")
        self._toast.set_halign(Gtk.Align.CENTER)
        self._toast.set_valign(Gtk.Align.END)
        self._toast.set_margin_bottom(48)
        self._toast.set_visible(False)
        for w in (self._toolbar, self._sidebar, self._toast):
            self._root.add_overlay(w)

    def _build_toolbar(self) -> Gtk.Widget:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.add_css_class("wfs-bar")
        bar.set_halign(Gtk.Align.START)
        bar.set_valign(Gtk.Align.START)
        bar.set_visible(False)

        self._tool_buttons = {}
        first = None
        for tid, label, tip in OVERLAY_TOOLS:
            btn = Gtk.ToggleButton(label=_(label))
            btn.add_css_class("wfs-round")
            btn.set_tooltip_text(_(tip))
            if first is None:
                first = btn
                btn.set_active(True)
            else:
                btn.set_group(first)
            btn.connect("toggled", self._on_tool_toggled, tid)
            bar.append(btn)
            self._tool_buttons[tid] = btn

        color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        rgba = Gdk.RGBA()
        rgba.parse(self.settings.pen_color)
        color.set_rgba(rgba)
        color.set_tooltip_text(_("Annotation color"))
        color.connect("notify::rgba", self._on_color_changed)
        bar.append(color)

        width = Gtk.SpinButton.new_with_range(1, 24, 1)
        width.set_value(float(self.settings.pen_width))
        width.set_tooltip_text(_("Line width"))
        width.connect("value-changed", self._on_width_changed)
        bar.append(width)

        undo = Gtk.Button.new_from_icon_name("edit-undo-symbolic")
        undo.add_css_class("wfs-round")
        undo.set_tooltip_text(_("Undo (Ctrl+Z)"))
        undo.connect("clicked", lambda *_: self.undo())
        redo = Gtk.Button.new_from_icon_name("edit-redo-symbolic")
        redo.add_css_class("wfs-round")
        redo.set_tooltip_text(_("Redo (Ctrl+Shift+Z)"))
        redo.connect("clicked", lambda *_: self.redo())
        bar.append(undo)
        bar.append(redo)
        return bar

    def _build_sidebar(self) -> Gtk.Widget:
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        bar.add_css_class("wfs-bar")
        bar.set_halign(Gtk.Align.START)
        bar.set_valign(Gtk.Align.START)
        bar.set_visible(False)

        def button(icon, tip, cb):
            b = Gtk.Button.new_from_icon_name(icon)
            b.add_css_class("wfs-round")
            b.set_tooltip_text(_(tip))
            b.connect("clicked", lambda *_: cb())
            bar.append(b)
            return b

        button("edit-copy-symbolic", "Copy to clipboard (Ctrl+C / Enter)",  # noqa: translated in helper
               self.copy_and_close)
        button("document-save-symbolic", "Save (Ctrl+S)", self.save_and_close)
        button("document-save-as-symbolic", "Save as… (Ctrl+Shift+S)",
               self.save_as)
        if self.open_editor:
            button("window-new-symbolic", "Open in editor window (W)",
                   self._to_editor)
        button("view-pin-symbolic", "Pin to screen (frameless window)",
               self.pin_to_screen)
        button("window-close-symbolic", "Cancel (Esc)", self.close)
        return bar

    def _install_css(self):
        css = b"""
        .wfs-bar { padding: 4px; border-radius: 22px;
                   background-color: rgba(24, 22, 28, 0.55); }
        .wfs-round { border-radius: 999px; padding: 6px 10px;
                     background-color: #8b12ae; color: #ffffff;
                     border: none; font-weight: bold; }
        .wfs-round:hover { background-color: #a63cc7; }
        .wfs-round:checked { background-color: #22c55e; color: #10331d; }
        .wfs-toast { background-color: rgba(20, 20, 24, 0.92); color: #fff;
                     border-radius: 9px; padding: 8px 18px; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def toast(self, message: str, seconds: float = 2.2):
        self._toast.set_text(message)
        self._toast.set_visible(True)
        GLib.timeout_add(int(seconds * 1000),
                         lambda: (self._toast.set_visible(False), False)[1])

    # ---------------------------------------------------------- geometry --

    def _view_params(self):
        w = max(1, self.area.get_width())
        h = max(1, self.area.get_height())
        iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
        scale = min(w / iw, h / ih)
        return scale, (w - iw * scale) / 2, (h - ih * scale) / 2

    def _to_image(self, wx, wy) -> Tuple[float, float]:
        scale, ox, oy = self._view_params()
        return ((wx - ox) / scale, (wy - oy) / scale)

    def _to_widget(self, ix, iy) -> Tuple[float, float]:
        scale, ox, oy = self._view_params()
        return (ix * scale + ox, iy * scale + oy)

    def _clamp_rect(self, x, y, w, h) -> Rect:
        iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
        x = max(0, min(int(x), iw - 1))
        y = max(0, min(int(y), ih - 1))
        w = max(1, min(int(w), iw - x))
        h = max(1, min(int(h), ih - y))
        return (x, y, w, h)

    def _handles(self):
        """8 resize handles in widget coords: name -> (x, y)."""
        if not self.sel:
            return {}
        x, y, w, h = self.sel
        x0, y0 = self._to_widget(x, y)
        x1, y1 = self._to_widget(x + w, y + h)
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        return {"nw": (x0, y0), "n": (xm, y0), "ne": (x1, y0),
                "w": (x0, ym), "e": (x1, ym),
                "sw": (x0, y1), "s": (xm, y1), "se": (x1, y1)}

    def _handle_at(self, wx, wy) -> Optional[str]:
        for name, (hx, hy) in self._handles().items():
            if abs(wx - hx) <= HANDLE_HIT and abs(wy - hy) <= HANDLE_HIT:
                return name
        return None

    def _inside_sel(self, ix, iy) -> bool:
        if not self.sel:
            return False
        x, y, w, h = self.sel
        return x <= ix <= x + w and y <= iy <= y + h

    # ----------------------------------------------------------- history --

    def _push_history(self):
        self._undo.append(tuple(self.shapes))
        if len(self._undo) > 100:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self):
        if self._undo:
            self._redo.append(tuple(self.shapes))
            self.shapes = list(self._undo.pop())
            self.area.queue_draw()

    def redo(self):
        if self._redo:
            self._undo.append(tuple(self.shapes))
            self.shapes = list(self._redo.pop())
            self.area.queue_draw()

    # ------------------------------------------------------------- input --

    def _on_tool_toggled(self, button, tool_id):
        if button.get_active():
            self.tool = tool_id
            cursor = "crosshair" if tool_id != "move" else "default"
            self.area.set_cursor(Gdk.Cursor.new_from_name(cursor))

    def select_tool(self, tool_id):
        btn = self._tool_buttons.get(tool_id)
        if btn:
            btn.set_active(True)

    def _on_color_changed(self, button, _pspec):
        rgba = button.get_rgba()
        self.style = Style(rgba=(rgba.red, rgba.green, rgba.blue, rgba.alpha),
                           width=self.style.width,
                           font_size=self.style.font_size)

    def _on_width_changed(self, spin):
        self.style = Style(rgba=self.style.rgba, width=spin.get_value(),
                           font_size=self.style.font_size)

    def _on_drag_begin(self, gesture, x, y):
        ix, iy = self._to_image(x, y)
        self._drag_start_img = (ix, iy)
        if self.mode == "select":
            self._drag_kind = "select"
            self.sel = self._clamp_rect(ix, iy, 1, 1)
        else:
            handle = self._handle_at(x, y)
            if handle:
                self._drag_kind = "resize"
                self._drag_handle = handle
                self._drag_sel0 = self.sel
            elif self.tool == "move":
                if self._inside_sel(ix, iy):
                    self._drag_kind = "move"
                    self._drag_sel0 = self.sel
                else:
                    self._drag_kind = "select"   # start a fresh selection
                    self._prev_sel = self.sel
                    self._set_bars_visible(False)
            elif self.tool in RECT_TOOLS or self.tool in ("pen", "line", "arrow"):
                self._drag_kind = "draw"
                if self.tool == "pen":
                    self._pen_points = [(ix, iy)]
            else:
                self._drag_kind = None
        self.area.queue_draw()

    def _on_drag_update(self, gesture, dx, dy):
        if self._drag_kind is None or self._drag_start_img is None:
            return
        ok, sx, sy = gesture.get_start_point()
        if not ok:
            return
        ix, iy = self._to_image(sx + dx, sy + dy)
        self._apply_drag(ix, iy)
        self.area.queue_draw()

    def _on_drag_end(self, gesture, dx, dy):
        kind, self._drag_kind = self._drag_kind, None
        if kind is None or self._drag_start_img is None:
            return
        ok, sx, sy = gesture.get_start_point()
        if ok:
            ix, iy = self._to_image(sx + dx, sy + dy)
            self._apply_drag(ix, iy)
        preview, self._preview = self._preview, None
        self._pen_points = []
        self._drag_start_img = None

        if kind == "select" and self.sel:
            if self.sel[2] >= 4 and self.sel[3] >= 4:
                self._enter_edit_mode()
            elif self.mode == "select":
                # A simple click in select mode: grab the whole screen.
                self.sel = (0, 0, self.pixbuf.get_width(),
                            self.pixbuf.get_height())
                self._enter_edit_mode()
            else:
                # Tiny drag in edit mode: restore the previous selection.
                if self._prev_sel:
                    self.sel = self._prev_sel
                self._enter_edit_mode()
        elif kind == "draw" and preview is not None:
            self._push_history()
            self.shapes.append(preview)
        elif kind in ("move", "resize"):
            self._reposition_bars()
        self.area.queue_draw()

    def _apply_drag(self, ix, iy):
        sx, sy = self._drag_start_img
        kind = self._drag_kind
        if kind == "select":
            x0, y0, x1, y1 = min(sx, ix), min(sy, iy), max(sx, ix), max(sy, iy)
            self.sel = self._clamp_rect(x0, y0, x1 - x0, y1 - y0)
        elif kind == "move" and self._drag_sel0:
            x, y, w, h = self._drag_sel0
            iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
            nx = max(0, min(int(x + ix - sx), iw - w))
            ny = max(0, min(int(y + iy - sy), ih - h))
            self.sel = (nx, ny, w, h)
            self._reposition_bars()
        elif kind == "resize" and self._drag_sel0:
            x, y, w, h = self._drag_sel0
            x0, y0, x1, y1 = x, y, x + w, y + h
            hd = self._drag_handle
            if "w" in hd:
                x0 = min(ix, x1 - 1)
            if "e" in hd:
                x1 = max(ix, x0 + 1)
            if "n" in hd:
                y0 = min(iy, y1 - 1)
            if "s" in hd:
                y1 = max(iy, y0 + 1)
            self.sel = self._clamp_rect(x0, y0, x1 - x0, y1 - y0)
            self._reposition_bars()
        elif kind == "draw":
            self._update_preview((ix, iy))

    def _update_preview(self, cur):
        start = self._drag_start_img
        tool = self.tool
        if tool == "pen":
            last = self._pen_points[-1]
            if abs(cur[0] - last[0]) + abs(cur[1] - last[1]) >= 1.0:
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

    def _on_click(self, gesture, n_press, x, y):
        if self.mode != "edit" or self.tool not in ("text", "marker"):
            return
        ix, iy = self._to_image(x, y)
        if self.tool == "marker":
            number = sum(1 for s in self.shapes if isinstance(s, Marker)) + 1
            self._push_history()
            self.shapes.append(Marker((ix, iy), number, self.style))
            self.area.queue_draw()
        else:
            self._open_text_popover(ix, iy, x, y)

    def _open_text_popover(self, ix, iy, wx, wy):
        popover = Gtk.Popover()
        popover.set_parent(self.area)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(wx), int(wy), 1, 1
        popover.set_pointing_to(rect)
        entry = Gtk.Entry()
        entry.set_placeholder_text(_("Text… (Enter to add)"))
        entry.set_width_chars(28)

        def commit(_entry):
            text = entry.get_text()
            if text.strip():
                self._push_history()
                self.shapes.append(Text((ix, iy), text, self.style))
                self.area.queue_draw()
            popover.popdown()

        entry.connect("activate", commit)
        popover.set_child(entry)
        popover.connect("closed", lambda p: GLib.idle_add(p.unparent))
        popover.popup()
        entry.grab_focus()

    def _on_key(self, _ctrl, keyval, _keycode, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        key = Gdk.keyval_to_lower(keyval)

        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if ctrl and key == Gdk.KEY_s:
            self.save_as() if shift else self.save_and_close()
            return True
        if ctrl and key == Gdk.KEY_c:
            self.copy_and_close()
            return True
        if ctrl and key == Gdk.KEY_z:
            self.redo() if shift else self.undo()
            return True
        if ctrl and key == Gdk.KEY_y:
            self.redo()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.mode == "select":
                self.sel = (0, 0, self.pixbuf.get_width(),
                            self.pixbuf.get_height())
                self._enter_edit_mode()
            else:
                self.copy_and_close()
            return True
        if self.mode == "edit" and not ctrl and not shift:
            if key in TOOL_KEYS:
                self.select_tool(TOOL_KEYS[key])
                return True
            if key == Gdk.KEY_w and self.open_editor:
                self._to_editor()
                return True
        return False

    # -------------------------------------------------------------- modes --

    def _enter_edit_mode(self):
        self.mode = "edit"
        self.select_tool("move")
        self._set_bars_visible(True)
        self._reposition_bars()

    def _set_bars_visible(self, visible: bool):
        self._toolbar.set_visible(visible)
        self._sidebar.set_visible(visible)

    def _reposition_bars(self):
        if not self.sel:
            return
        win_w = max(1, self.area.get_width())
        win_h = max(1, self.area.get_height())
        x, y, w, h = self.sel
        wx0, wy0 = self._to_widget(x, y)
        wx1, wy1 = self._to_widget(x + w, y + h)

        tb_w = self._toolbar.measure(Gtk.Orientation.HORIZONTAL, -1)[1]
        tb_h = self._toolbar.measure(Gtk.Orientation.VERTICAL, -1)[1]
        tx = (wx0 + wx1) / 2 - tb_w / 2
        tx = max(8, min(tx, win_w - tb_w - 8))
        ty = wy1 + 12
        if ty + tb_h > win_h - 8:      # no room below -> above the selection
            ty = max(8, wy0 - tb_h - 12)
        self._toolbar.set_margin_start(int(tx))
        self._toolbar.set_margin_top(int(ty))

        sb_w = self._sidebar.measure(Gtk.Orientation.HORIZONTAL, -1)[1]
        sb_h = self._sidebar.measure(Gtk.Orientation.VERTICAL, -1)[1]
        sx = wx1 + 12
        if sx + sb_w > win_w - 8:      # no room right -> left of the selection
            sx = max(8, wx0 - sb_w - 12)
        sy = max(8, min(wy0, win_h - sb_h - 8))
        self._sidebar.set_margin_start(int(sx))
        self._sidebar.set_margin_top(int(sy))

    # ------------------------------------------------------------ actions --

    def _export_cropped(self) -> GdkPixbuf.Pixbuf:
        iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, iw, ih)
        cr = cairo.Context(surface)
        Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
        cr.paint()
        for shape in self.shapes:
            shape.draw(cr, self.pixbuf)
        surface.flush()
        full = Gdk.pixbuf_get_from_surface(surface, 0, 0, iw, ih)
        x, y, w, h = self.sel or (0, 0, iw, ih)
        return full.new_subpixbuf(x, y, w, h).copy()

    def save_and_close(self):
        path = save_mod.timestamp_path(self.settings)
        try:
            path = save_mod.save_pixbuf(self._export_cropped(), path)
        except Exception as e:
            self.toast(tr("Save failed: {error}", error=e))
            return
        print(path)
        self.close()

    def save_as(self):
        dialog = Gtk.FileDialog()
        dialog.set_initial_name(
            os.path.basename(save_mod.timestamp_path(self.settings)))
        dialog.set_initial_folder(
            Gio.File.new_for_path(self.settings.save_dir_path))

        def done(dlg, result):
            try:
                gfile = dlg.save_finish(result)
            except GLib.Error:
                return
            try:
                path = save_mod.save_pixbuf(self._export_cropped(),
                                            gfile.get_path())
            except Exception as e:
                self.toast(tr("Save failed: {error}", error=e))
                return
            print(path)
            self.close()

        dialog.save(self, None, done)

    def copy_and_close(self):
        try:
            how = save_mod.copy_pixbuf(self._export_cropped())
        except Exception as e:
            self.toast(tr("Copy failed: {error}", error=e))
            return
        if how in ("wl-copy", "holder process"):
            self.close()  # a holder keeps owning the clipboard after we exit
        else:
            self.toast(_("Copied — keep this window open while pasting (install wl-clipboard to copy & close)"))

    def pin_to_screen(self):
        from .editor.pin import PinWindow
        PinWindow(self.get_application(), self._export_cropped()).present()

    def _to_editor(self):
        if not self.open_editor:
            return
        x, y, _w, _h = self.sel or (0, 0, 0, 0)
        base = (self.pixbuf if self.sel is None
                else self.pixbuf.new_subpixbuf(*self.sel).copy())
        shapes = [s.translate(-x, -y) for s in self.shapes]
        cb, self.open_editor = self.open_editor, None
        cb(base, shapes)
        self.close()

    # ------------------------------------------------------------ drawing --

    def _draw(self, area, cr, w, h, _data):
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        scale, ox, oy = self._view_params()

        def paint_content():
            cr.save()
            cr.translate(ox, oy)
            cr.scale(scale, scale)
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
            cr.paint()
            for shape in self.shapes:
                shape.draw(cr, self.pixbuf)
            if self._preview is not None:
                self._preview.draw(cr, self.pixbuf)
            cr.restore()

        paint_content()
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.paint()

        if self.sel:
            x, y, sw, sh = self.sel
            wx0, wy0 = self._to_widget(x, y)
            wx1, wy1 = self._to_widget(x + sw, y + sh)
            cr.save()
            cr.rectangle(wx0, wy0, wx1 - wx0, wy1 - wy0)
            cr.clip()
            paint_content()
            cr.restore()

            cr.set_source_rgba(0.55, 0.07, 0.68, 0.95)  # flameshot purple
            cr.set_line_width(1.5)
            cr.rectangle(wx0 + 0.5, wy0 + 0.5, wx1 - wx0, wy1 - wy0)
            cr.stroke()
            for hx, hy in self._handles().values():
                cr.arc(hx, hy, HANDLE_R, 0, 6.2832)
                cr.fill()

            label = f"{sw} × {sh}"
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                                cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(13)
            ext = cr.text_extents(label)
            lx = min(wx0 + 6, w - ext.width - 12)
            ly = max(18.0, wy0 - 10)
            cr.set_source_rgba(0, 0, 0, 0.7)
            cr.rectangle(lx - 5, ly - ext.height - 4, ext.width + 10,
                         ext.height + 9)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.move_to(lx, ly)
            cr.show_text(label)
        elif self.mode == "select":
            hint = _("Drag: select area   •   Click / Enter: full screen   •   Esc: cancel")
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                                cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(15)
            ext = cr.text_extents(hint)
            hx = (w - ext.width) / 2
            hy = 42.0
            cr.set_source_rgba(0, 0, 0, 0.65)
            cr.rectangle(hx - 14, hy - ext.height - 8, ext.width + 28,
                         ext.height + 18)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.move_to(hx, hy)
            cr.show_text(hint)
