"""Where things are on the region overlay.

Image and widget coordinates, zoom and pan, the monitors inside the
screenshot and the selection's resize handles. A mixin of
overlay.window.OverlayWindow: it reads ``pixbuf``, ``area``, ``sel``,
``_zoom``, ``_pan``, ``_pointer`` and ``_mon_rects`` from the window.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk  # noqa: E402

Rect = Tuple[int, int, int, int]

HANDLE_R = 6.0        # visual radius of resize handles (widget px)
HANDLE_HIT = 14.0     # hit-test radius

ZOOM_MAX = 8.0          # relative to "the whole screen fits"
ZOOM_STEP = 1.25        # per Ctrl+plus / Ctrl+minus
WHEEL_ZOOM = 1.15       # per wheel notch with Ctrl held
PAN_STEP = 48.0         # widget px per wheel notch


class OverlayViewMixin:
    """Image pixels are the screenshot's (selection, shapes); widget pixels
    are the window's (pointer, handles, bars). _view_params links them."""

    def _view_params(self):
        """(scale, origin x, origin y): image pixels to widget pixels."""
        w = max(1, self.area.get_width())
        h = max(1, self.area.get_height())
        iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
        scale = min(w / iw, h / ih) * self._zoom
        return (scale, (w - iw * scale) / 2 + self._pan[0],
                (h - ih * scale) / 2 + self._pan[1])

    def _set_view(self, zoom: float, pan: Tuple[float, float]) -> None:
        """Apply a zoom level and pan, clamped so the image never leaves a
        gap at an edge it is large enough to cover."""
        zoom = max(1.0, min(ZOOM_MAX, zoom))
        w = max(1, self.area.get_width())
        h = max(1, self.area.get_height())
        iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
        scale = min(w / iw, h / ih) * zoom
        px, py = pan
        over_x, over_y = iw * scale - w, ih * scale - h
        px = 0.0 if over_x <= 0.5 else max(-over_x / 2, min(over_x / 2, px))
        py = 0.0 if over_y <= 0.5 else max(-over_y / 2, min(over_y / 2, py))
        self._zoom, self._pan = zoom, (px, py)
        self._update_control_layout()
        self._position_text_view()
        self._style_text_view()
        self.area.queue_draw()

    def zoom_to(self, zoom: float, anchor=None) -> None:
        """Set the zoom level keeping the image point under *anchor* (widget
        coordinates; the pointer by default, else the centre) in place."""
        w = max(1, self.area.get_width())
        h = max(1, self.area.get_height())
        iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
        if anchor is None:
            anchor = self._pointer or (w / 2, h / 2)
        ax, ay = anchor
        ix, iy = self._to_image(ax, ay)
        zoom = max(1.0, min(ZOOM_MAX, zoom))
        scale = min(w / iw, h / ih) * zoom
        self._set_view(zoom, (ax - ix * scale - (w - iw * scale) / 2,
                              ay - iy * scale - (h - ih * scale) / 2))

    def zoom_at(self, factor: float, anchor=None) -> None:
        """Zoom by *factor* around *anchor* (see zoom_to)."""
        self.zoom_to(self._zoom * factor, anchor)

    def _on_pinch_begin(self, gesture, _sequence):
        self._pinch_zoom0 = self._zoom

    def _on_pinch_scale(self, gesture, scale):
        # GestureZoom reports the scale relative to the start of the pinch.
        ok, cx, cy = gesture.get_bounding_box_center()
        self.zoom_to(self._pinch_zoom0 * scale, (cx, cy) if ok else None)

    def zoom_reset(self) -> None:
        self._set_view(1.0, (0.0, 0.0))

    def zoom_to_selection(self) -> None:
        """Fill the window with the selection, with a little room around."""
        if not self.sel:
            return
        w = max(1, self.area.get_width())
        h = max(1, self.area.get_height())
        iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
        x, y, sw, sh = self.sel
        base = min(w / iw, h / ih)
        zoom = min(w / (sw * base), h / (sh * base)) * 0.9
        zoom = max(1.0, min(ZOOM_MAX, zoom))
        scale = base * zoom
        cx, cy = x + sw / 2, y + sh / 2
        self._set_view(zoom, (w / 2 - cx * scale - (w - iw * scale) / 2,
                              h / 2 - cy * scale - (h - ih * scale) / 2))

    def _on_scroll(self, controller, dx, dy):
        """Ctrl+wheel zooms around the pointer; while zoomed in, the wheel
        pans (Shift+wheel sideways). At zoom 1 the wheel is left alone."""
        state = controller.get_current_event_state()
        if state & Gdk.ModifierType.CONTROL_MASK:
            self.zoom_at(WHEEL_ZOOM ** -dy)       # wheel up zooms in
            return True
        if self._zoom <= 1.0:
            return False
        if state & Gdk.ModifierType.SHIFT_MASK and dx == 0:
            dx, dy = dy, 0.0
        px, py = self._pan
        self._set_view(self._zoom, (px - dx * PAN_STEP, py - dy * PAN_STEP))
        return True

    def _device_scale(self) -> float:
        """The surface's device scale (fractional on 125%/150% displays)."""
        try:
            surface = self.get_surface()
            if surface is not None and hasattr(surface, "get_scale"):
                s = surface.get_scale()
                if s and s > 0:
                    return float(s)
        except Exception:
            pass
        try:
            return float(self.get_scale_factor()) or 1.0
        except Exception:
            return 1.0

    def _monitor_rects_image(self):
        """Monitor geometries mapped into image (buffer-pixel) coords.

        The portal returns one image spanning every monitor; map each
        GdkMonitor's logical geometry through the union bounding box so the
        selection can snap to monitor edges.  Returns [] on any failure so the
        single-monitor path is never affected.
        """
        try:
            monitors = list(Gdk.Display.get_default().get_monitors())
            geos = [m.get_geometry() for m in monitors]
            geos = [g for g in geos if g and g.width > 0 and g.height > 0]
            if len(geos) < 2:
                return []  # snapping only matters with 2+ monitors
            ux0 = min(g.x for g in geos)
            uy0 = min(g.y for g in geos)
            uw = max(g.x + g.width for g in geos) - ux0
            uh = max(g.y + g.height for g in geos) - uy0
            if uw <= 0 or uh <= 0:
                return []
            iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
            sx, sy = iw / uw, ih / uh
            return [(round((g.x - ux0) * sx), round((g.y - uy0) * sy),
                     round(g.width * sx), round(g.height * sy)) for g in geos]
        except Exception:
            return []

    def _snap_selection(self, x0, y0, x1, y1, thresh=14):
        """Snap selection edges to nearby monitor boundaries (image
        coordinates), so a monitor is easy to select exactly."""
        rects = self._mon_rects
        if not rects:
            return x0, y0, x1, y1
        xs, ys = set(), set()
        for mx, my, mw, mh in rects:
            xs |= {mx, mx + mw}
            ys |= {my, my + mh}

        def snap(v, cands):
            best = v
            bestd = thresh + 1
            for c in cands:
                d = abs(v - c)
                if d <= thresh and d < bestd:
                    best, bestd = c, d
            return best

        return snap(x0, xs), snap(y0, ys), snap(x1, xs), snap(y1, ys)

    def _to_image(self, wx, wy) -> Tuple[float, float]:
        scale, ox, oy = self._view_params()
        return ((wx - ox) / scale, (wy - oy) / scale)

    def _to_widget(self, ix, iy) -> Tuple[float, float]:
        scale, ox, oy = self._view_params()
        return (ix * scale + ox, iy * scale + oy)

    def _clamp_rect(self, x, y, w, h) -> Rect:
        """Clip a rectangle to the image edge by edge: a selection dragged
        out past the left or top keeps its right and bottom where they were."""
        iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
        x1 = min(math.floor(x + w), iw)
        y1 = min(math.floor(y + h), ih)
        x = max(0, min(int(x), iw - 1))
        y = max(0, min(int(y), ih - 1))
        return (x, y, max(1, x1 - x), max(1, y1 - y))

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
        """The resize handle within reach of a widget point, if any."""
        for name, (hx, hy) in self._handles().items():
            if abs(wx - hx) <= HANDLE_HIT and abs(wy - hy) <= HANDLE_HIT:
                return name
        return None

    def _inside_sel(self, ix, iy) -> bool:
        if not self.sel:
            return False
        x, y, w, h = self.sel
        return x <= ix <= x + w and y <= iy <= y + h
