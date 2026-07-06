"""Short animated-GIF capture of a screen region.

Pick a region on a frozen first shot, then frames are grabbed on a timer via
the Screenshot portal and encoded to an animated GIF with the pure gifenc
module (no image-library dependency).

NOTE: the GIF encoder is unit-tested; this GTK/portal capture flow needs a
real Wayland session to verify (on-device checklist #17).
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from . import gifenc
from .i18n import _, tr
from .portal import Portal, cleanup_portal_file

MAX_FRAMES = 60
FRAME_INTERVAL_MS = 200
DELAY_CS = 20  # 200 ms per GIF frame


def pixbuf_crop_to_rgb(pixbuf, crop):
    """Crop *pixbuf* to *crop* (x, y, w, h) and return packed RGB bytes."""
    x, y, w, h = crop
    bw, bh = pixbuf.get_width(), pixbuf.get_height()
    x = max(0, min(x, bw - 1))
    y = max(0, min(y, bh - 1))
    w = max(1, min(w, bw - x))
    h = max(1, min(h, bh - y))
    sub = pixbuf.new_subpixbuf(x, y, w, h)
    stride = sub.get_rowstride()
    nch = sub.get_n_channels()
    data = sub.get_pixels()
    rgb = bytearray(w * h * 3)
    for row in range(h):
        base = row * stride
        for col in range(w):
            o = base + col * nch
            d = (row * w + col) * 3
            rgb[d] = data[o]
            rgb[d + 1] = data[o + 1]
            rgb[d + 2] = data[o + 2]
    return bytes(rgb), w, h


class GifCaptureWindow(Gtk.ApplicationWindow):
    def __init__(self, app, settings, portal: Portal, on_done):
        super().__init__(application=app,
                         title=_("GIF capture — Feather Shot"))
        self.settings = settings
        self.portal = portal
        self.on_done = on_done          # on_done(path_or_None, error)
        self._done = False
        self._first = None
        self._crop = None
        self._frames: List[bytes] = []
        self._size = (0, 0)
        self._phase = "loading"
        self._sel_start = self._sel_end = None
        self._scale = 1.0
        self._ox = self._oy = 0.0
        self._tick_id = 0

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(10)
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
        drag.connect("drag-begin", self._on_begin)
        drag.connect("drag-update", self._on_update)
        drag.connect("drag-end", self._on_update)
        self.area.add_controller(drag)
        self._buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                spacing=8)
        self._buttons.set_halign(Gtk.Align.CENTER)
        box.append(self._buttons)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.set_default_size(1000, 720)

    def begin(self):
        self._status.set_text(_("Choose the area to record…"))

        def got(path, error):
            if path is None:
                self._emit(None, error if error != "cancelled" else None)
                return
            try:
                self._first = GdkPixbuf.Pixbuf.new_from_file(path)
            except GLib.Error as e:
                self._emit(None, str(e))
                return
            finally:
                cleanup_portal_file(path)
            self._enter_select()

        def first(path, error):
            if path is None and error != "cancelled":
                self.portal.screenshot(got, interactive=True)
                return
            got(path, error)

        self.portal.screenshot(first, interactive=False)

    def _enter_select(self):
        self._phase = "select"
        self._status.set_text(_("Drag to select the area, then press Enter."))
        self._set_buttons([(_("Start recording"), self._start, True),
                           (_("Cancel"), self.cancel, False)])
        self.area.queue_draw()

    def _start(self, *_a):
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
        self._phase = "recording"
        self._frames = []
        self._set_buttons([(_("Stop && save"), self._stop, True),
                           (_("Cancel"), self.cancel, False)])
        self._grab()
        self._tick_id = GLib.timeout_add(FRAME_INTERVAL_MS, self._on_tick)

    def _on_tick(self):
        if self._done or len(self._frames) >= MAX_FRAMES:
            self._stop()
            return False
        self._grab()
        return True

    def _grab(self):
        def got(path, error):
            if path is None:
                return
            try:
                shot = GdkPixbuf.Pixbuf.new_from_file(path)
            except GLib.Error:
                return
            finally:
                cleanup_portal_file(path)
            rgb, w, h = pixbuf_crop_to_rgb(shot, self._crop)
            self._size = (w, h)
            self._frames.append(gifenc.quantize_rgb(rgb, w * h))
            self._status.set_text(tr("Recording…  frames: {n}",
                                     n=len(self._frames)))

        self.portal.screenshot(got, interactive=False)

    def _stop(self, *_a):
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = 0
        if len(self._frames) < 2:
            self._emit(None, _("Not enough frames captured."))
            return
        w, h = self._size
        data = gifenc.write_gif(self._frames, w, h, delay_cs=DELAY_CS)
        name = time.strftime("wfs-%Y-%m-%d_%H-%M-%S.gif")
        path = os.path.join(self.settings.save_dir_path, name)
        try:
            with open(path, "wb") as fh:
                fh.write(data)
        except OSError as e:
            self._emit(None, str(e))
            return
        self._emit(path, None)

    def cancel(self, *_a):
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = 0
        self._emit(None, None)

    # -- region select drawing --------------------------------------------

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

    def _on_begin(self, gesture, x, y):
        if self._phase != "select":
            return
        self._sel_start = self._to_image(x, y)
        self._sel_end = self._sel_start
        self.area.queue_draw()

    def _on_update(self, gesture, dx, dy):
        if self._phase != "select":
            return
        ok, sx, sy = gesture.get_start_point()
        if ok:
            self._sel_end = self._to_image(sx + dx, sy + dy)
            self.area.queue_draw()

    def _on_key(self, _ctrl, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            self.cancel()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self._phase == "select":
                self._start()
            elif self._phase == "recording":
                self._stop()
            return True
        return False

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

    def _emit(self, path, error):
        if self._done:
            return
        self._done = True
        self.on_done(path, error)
        self.close()
