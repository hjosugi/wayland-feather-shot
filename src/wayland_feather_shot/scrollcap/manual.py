"""GStreamer-free scrolling capture (fallback).

When GStreamer/PipeWire is unavailable, scroll capture falls back to repeated
Screenshot-portal grabs of a region the user picks, while *they* scroll
between grabs.  The frames feed the same GUI-free stitcher as the PipeWire
path, so the result is identical — just slower and manual.

No new dependencies: frames are GdkPixbuf buffers converted to the stitcher's
raw-RGBA :class:`Frame`, never PIL.

NOTE: the GTK/portal flow here needs a real Wayland session to exercise; the
stitching core it feeds is unit-tested (tests/test_stitcher.py).
"""

from __future__ import annotations

from typing import List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from ..i18n import _, tr
from ..portal import Portal
from . import stitcher
from .stitcher import Frame


def pixbuf_to_frame(pixbuf: GdkPixbuf.Pixbuf) -> Frame:
    """Convert a GdkPixbuf to a stitcher Frame (raw RGBA, 4 bytes/pixel)."""
    if not pixbuf.get_has_alpha():
        pixbuf = pixbuf.add_alpha(False, 0, 0, 0)
    data = bytes(pixbuf.get_pixels())
    return Frame(data=data, width=pixbuf.get_width(),
                 height=pixbuf.get_height(), stride=pixbuf.get_rowstride())


class ManualScrollWindow(Gtk.ApplicationWindow):
    """Two phases: pick a region on the first shot, then capture + scroll."""

    def __init__(self, app, settings, portal: Portal, on_result):
        super().__init__(application=app,
                         title=_("Scrolling capture — Feather Shot"))
        self.settings = settings
        self.portal = portal
        self.on_result = on_result
        self._done = False

        self._first: Optional[GdkPixbuf.Pixbuf] = None
        self._crop = None                 # (x, y, w, h) in image coords
        self._frames: List[Frame] = []
        self._phase = "loading"           # loading -> select -> capture
        self._sel_start = None
        self._sel_end = None
        self._scale = 1.0
        self._ox = self._oy = 0.0

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        self.set_child(box)

        self._status = Gtk.Label(label=_("Preparing…"))
        self._status.set_wrap(True)
        box.append(self._status)

        self.area = Gtk.DrawingArea()
        self.area.set_vexpand(True)
        self.area.set_hexpand(True)
        self.area.set_draw_func(self._draw)
        box.append(self.area)

        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.area.add_controller(drag)

        self._buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                spacing=8)
        self._buttons.set_halign(Gtk.Align.CENTER)
        box.append(self._buttons)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.set_default_size(1000, 720)

    # -- lifecycle ----------------------------------------------------------

    def begin(self):
        self._status.set_text(_("Choose the area to capture…"))

        def got(path, error):
            if path is None:
                if error and error != "cancelled":
                    self._emit(None, error)
                else:
                    self._emit(None, "cancelled")
                return
            from ..portal import cleanup_portal_file
            try:
                self._first = GdkPixbuf.Pixbuf.new_from_file(path)
            except GLib.Error as e:
                self._emit(None, str(e))
                return
            finally:
                cleanup_portal_file(path)
            self._enter_select()

        def got_interactive(path, error):
            got(path, error)

        def first(path, error):
            if path is None and error != "cancelled":
                # retry with the portal's own dialog
                self.portal.screenshot(got_interactive, interactive=True)
                return
            got(path, error)

        self.portal.screenshot(first, interactive=False)

    def _enter_select(self):
        self._phase = "select"
        self._status.set_text(_(
            "Drag to select the scrolling area, then press Enter."))
        self._set_buttons([
            (_("Use this area"), self._confirm_area, True),
            (_("Cancel"), self.cancel, False),
        ])
        self.area.queue_draw()

    def _enter_capture(self):
        self._phase = "capture"
        self._frames = []
        self._grab_frame()  # keep the first frame
        self._set_buttons([
            (_("Capture frame"), self._grab_frame, True),
            (_("Finish && stitch"), self._finish, False),
            (_("Cancel"), self.cancel, False),
        ])
        self._update_capture_status()

    def _update_capture_status(self):
        self._status.set_text(tr(
            "Scroll a little, then press “Capture frame”.  Frames: {n}",
            n=len(self._frames)))

    # -- region selection ---------------------------------------------------

    def _confirm_area(self, *_a):
        if not self._sel_start or not self._sel_end:
            return
        x0, y0 = self._sel_start
        x1, y1 = self._sel_end
        left, right = sorted((int(x0), int(x1)))
        top, bottom = sorted((int(y0), int(y1)))
        if right - left < 10 or bottom - top < 10:
            self._status.set_text(_("Selection too small — drag a larger area."))
            return
        self._crop = (left, top, right - left, bottom - top)
        self._enter_capture()

    def _grab_frame(self, *_a):
        if self._crop is None:
            return

        def got(path, error):
            if path is None:
                if error and error != "cancelled":
                    self._status.set_text(
                        tr("Capture failed: {error}", error=error))
                return
            from ..portal import cleanup_portal_file
            try:
                shot = GdkPixbuf.Pixbuf.new_from_file(path)
            except GLib.Error:
                return
            finally:
                cleanup_portal_file(path)
            x, y, w, h = self._crop
            bw, bh = shot.get_width(), shot.get_height()
            x = max(0, min(x, bw - 1))
            y = max(0, min(y, bh - 1))
            w = max(1, min(w, bw - x))
            h = max(1, min(h, bh - y))
            sub = shot.new_subpixbuf(x, y, w, h).copy()
            self._frames.append(pixbuf_to_frame(sub))
            self._update_capture_status()

        self.portal.screenshot(got, interactive=False)

    def _finish(self, *_a):
        if len(self._frames) < 2:
            self._status.set_text(_("Capture at least two frames first."))
            return
        self._status.set_text(tr("Stitching {n} frames…", n=len(self._frames)))
        top = int(self.settings.scroll_top_margin)
        bottom = int(self.settings.scroll_bottom_margin)
        max_h = int(self.settings.scroll_max_height)
        result = stitcher.stitch(self._frames, top_margin=top,
                                 bottom_margin=bottom)
        if result is None:
            self._emit(None, _("stitching failed"))
            return
        height = min(result.height, max_h)
        data = bytes(result.data[: height * result.width * 4])
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(data), GdkPixbuf.Colorspace.RGB, True, 8,
            result.width, height, result.width * 4)
        warning = None
        if getattr(result, "warnings", None):
            warning = tr("{n} frame(s) skipped while stitching: {detail}",
                         n=len(result.warnings),
                         detail="; ".join(sorted({_(w.reason)
                                                  for w in result.warnings})))
        self._emit(pixbuf.copy(), None, warning)

    def cancel(self, *_a):
        self._emit(None, "cancelled")

    # -- drawing / input ----------------------------------------------------

    def _draw(self, area, cr, width, height):
        cr.set_source_rgb(0.10, 0.10, 0.12)
        cr.paint()
        if self._first is None:
            return
        iw, ih = self._first.get_width(), self._first.get_height()
        self._scale = min(width / iw, height / ih, 1.0)
        self._ox = max(0, (width - iw * self._scale) / 2)
        self._oy = max(0, (height - ih * self._scale) / 2)
        cr.save()
        cr.translate(self._ox, self._oy)
        cr.scale(self._scale, self._scale)
        Gdk.cairo_set_source_pixbuf(cr, self._first, 0, 0)
        cr.paint()
        rect = self._crop
        if self._phase == "select" and self._sel_start and self._sel_end:
            x0, y0 = self._sel_start
            x1, y1 = self._sel_end
            rect = (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
        if rect:
            cr.set_source_rgba(0.3, 0.7, 1.0, 0.25)
            cr.rectangle(*rect)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.set_line_width(2 / max(self._scale, 0.001))
            cr.stroke()
        cr.restore()

    def _to_image(self, x, y):
        ix = (x - self._ox) / max(self._scale, 0.0001)
        iy = (y - self._oy) / max(self._scale, 0.0001)
        iw = self._first.get_width() if self._first else 0
        ih = self._first.get_height() if self._first else 0
        return (max(0, min(ix, iw)), max(0, min(iy, ih)))

    def _on_drag_begin(self, gesture, x, y):
        if self._phase != "select":
            return
        self._sel_start = self._to_image(x, y)
        self._sel_end = self._sel_start
        self.area.queue_draw()

    def _on_drag_update(self, gesture, dx, dy):
        if self._phase != "select":
            return
        ok, sx, sy = gesture.get_start_point()
        if ok:
            self._sel_end = self._to_image(sx + dx, sy + dy)
            self.area.queue_draw()

    def _on_drag_end(self, gesture, dx, dy):
        self._on_drag_update(gesture, dx, dy)

    def _on_key(self, _ctrl, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            self.cancel()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self._phase == "select":
                self._confirm_area()
            elif self._phase == "capture":
                self._grab_frame()
            return True
        return False

    # -- helpers ------------------------------------------------------------

    def _set_buttons(self, specs):
        child = self._buttons.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._buttons.remove(child)
            child = nxt
        for label, cb, suggested in specs:
            btn = Gtk.Button(label=label)
            if suggested:
                btn.add_css_class("suggested-action")
            btn.connect("clicked", cb)
            self._buttons.append(btn)

    def _emit(self, pixbuf, error, warning=None):
        if self._done:
            return
        self._done = True
        self.on_result(pixbuf, error, warning)
        self.close()
