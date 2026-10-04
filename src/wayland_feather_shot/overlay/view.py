"""Where things are on the region overlay.

Image and widget coordinates, zoom and pan, the monitors inside the
screenshot and the selection's resize handles. A mixin of
overlay.window.OverlayWindow.

With several monitors the overlay has one fullscreen window per monitor,
each a MonitorView showing its own part of the screenshot at that
monitor's scale, rather than every monitor shrunk into one screen. The
window state (selection, shapes, tools) is shared; ``_view`` is the view
being drawn or used, and ``area``, ``_zoom``, ``_pan`` and ``_pointer``
read through it.
"""

from __future__ import annotations

import contextlib
import math
from typing import List, Optional, Tuple

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


class MonitorView:
    """One window's look at the screenshot: its canvas, the part of the
    image it shows at zoom 1 (a monitor, or the whole image), and its own
    zoom, pan and pointer."""

    def __init__(self, window, root, area, rect: Rect, monitor=None):
        self.window = window        # the OverlayWindow, or a plain Gtk.Window
        self.root = root            # its Gtk.Overlay: canvas plus the bars
        self.area = area            # its OverlayCanvas
        self.rect = rect            # image rect shown at zoom 1
        self.monitor = monitor      # Gdk.Monitor to go fullscreen on, or None
        self.zoom = 1.0
        self.pan = (0.0, 0.0)       # widget px, added to the fitted origin
        self.pinch_zoom0 = 1.0      # zoom level when a pinch started
        self.pointer: Optional[Tuple[float, float]] = None


def _through_view(name):
    """A property that reads and writes *name* on the current view."""
    return property(lambda self: getattr(self._view, name),
                    lambda self, value: setattr(self._view, name, value))


class OverlayViewMixin:
    """Image pixels are the screenshot's (selection, shapes); widget pixels
    are the current view's window (pointer, handles, bars). _view_params
    links them."""

    area = property(lambda self: self._view.area)
    _zoom = _through_view("zoom")
    _pan = _through_view("pan")
    _pinch_zoom0 = _through_view("pinch_zoom0")
    _pointer = _through_view("pointer")

    @contextlib.contextmanager
    def _looking_through(self, view):
        """Work in *view*'s coordinates for a moment (drawing it, placing
        bars on it), then go back to the view in use."""
        previous, self._view = self._view, view
        try:
            yield view
        finally:
            self._view = previous

    def _view_params(self):
        """(scale, origin x, origin y): image pixels to widget pixels."""
        w = max(1, self.area.get_width())
        h = max(1, self.area.get_height())
        vx, vy, vw, vh = self._view.rect
        scale = min(w / vw, h / vh) * self._zoom
        return (scale, (w - vw * scale) / 2 + self._pan[0] - vx * scale,
                (h - vh * scale) / 2 + self._pan[1] - vy * scale)

    def _zoom_max(self) -> float:
        """How far in the zoom goes: ZOOM_MAX times "it fits", or for a
        picture that fits only far below its own size (a scrolling
        capture's tall result) until a pixel is ZOOM_MAX screen pixels."""
        w = max(1, self.area.get_width())
        h = max(1, self.area.get_height())
        _vx, _vy, vw, vh = self._view.rect
        return max(ZOOM_MAX, ZOOM_MAX / min(w / vw, h / vh))

    def _fit_tall_picture(self) -> None:
        """Start a picture much taller than the window (a scrolling
        capture's result) at the window's width, from its top, rather than
        as a sliver in the middle."""
        w = max(1, self.area.get_width())
        h = max(1, self.area.get_height())
        _vx, _vy, vw, vh = self._view.rect
        base = min(w / vw, h / vh)
        zoom = (w / vw) / base
        if zoom < 1.5:
            return
        over_y = vh * base * zoom - h
        self._set_view(zoom, (0.0, over_y / 2))

    def _set_view(self, zoom: float, pan: Tuple[float, float]) -> None:
        """Apply a zoom level and pan, clamped so the image never leaves a
        gap at an edge it is large enough to cover."""
        zoom = max(1.0, min(self._zoom_max(), zoom))
        w = max(1, self.area.get_width())
        h = max(1, self.area.get_height())
        _vx, _vy, vw, vh = self._view.rect
        scale = min(w / vw, h / vh) * zoom
        px, py = pan
        over_x, over_y = vw * scale - w, vh * scale - h
        px = 0.0 if over_x <= 0.5 else max(-over_x / 2, min(over_x / 2, px))
        py = 0.0 if over_y <= 0.5 else max(-over_y / 2, min(over_y / 2, py))
        self._zoom, self._pan = zoom, (px, py)
        self._update_control_layout()
        self._position_text_view()
        self._style_text_view()
        self._redraw()

    def zoom_to(self, zoom: float, anchor=None) -> None:
        """Set the zoom level keeping the image point under *anchor* (widget
        coordinates; the pointer by default, else the centre) in place."""
        w = max(1, self.area.get_width())
        h = max(1, self.area.get_height())
        vx, vy, vw, vh = self._view.rect
        if anchor is None:
            anchor = self._pointer or (w / 2, h / 2)
        ax, ay = anchor
        ix, iy = self._to_image(ax, ay)
        zoom = max(1.0, min(self._zoom_max(), zoom))
        scale = min(w / vw, h / vh) * zoom
        self._set_view(zoom, (ax - (ix - vx) * scale - (w - vw * scale) / 2,
                              ay - (iy - vy) * scale - (h - vh * scale) / 2))

    def zoom_at(self, factor: float, anchor=None) -> None:
        """Zoom by *factor* around *anchor* (see zoom_to)."""
        self.zoom_to(self._zoom * factor, anchor)

    def _on_pinch_begin(self, _gesture, _sequence):
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
        vx, vy, vw, vh = self._view.rect
        x, y, sw, sh = self.sel
        base = min(w / vw, h / vh)
        zoom = min(w / (sw * base), h / (sh * base)) * 0.9
        zoom = max(1.0, min(self._zoom_max(), zoom))
        scale = base * zoom
        cx, cy = x + sw / 2, y + sh / 2
        self._set_view(zoom, (w / 2 - (cx - vx) * scale - (w - vw * scale) / 2,
                              h / 2 - (cy - vy) * scale - (h - vh * scale) / 2))

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
        window = self._view.window
        try:
            surface = window.get_surface()
            if surface is not None and hasattr(surface, "get_scale"):
                s = surface.get_scale()
                if s and s > 0:
                    return float(s)
        except Exception:
            pass
        try:
            return float(window.get_scale_factor()) or 1.0
        except Exception:
            return 1.0

    def _monitor_layout(self) -> List[Tuple[object, Rect]]:
        """(Gdk.Monitor, image rect) for each monitor the screenshot spans.

        The portal returns one image spanning every monitor; each monitor's
        logical geometry maps into it through the union bounding box. With
        one monitor, or when the image does not look like that union (its
        proportions differ), the answer is one entry for the whole image
        and no monitor, which keeps the single-window overlay.
        """
        whole = [(None, (0, 0, self.pixbuf.get_width(),
                         self.pixbuf.get_height()))]
        try:
            monitors = list(Gdk.Display.get_default().get_monitors())
            pairs = [(m, m.get_geometry()) for m in monitors]
            pairs = [(m, g) for m, g in pairs
                     if g and g.width > 0 and g.height > 0]
            if len(pairs) < 2:
                return whole
            ux0 = min(g.x for _m, g in pairs)
            uy0 = min(g.y for _m, g in pairs)
            uw = max(g.x + g.width for _m, g in pairs) - ux0
            uh = max(g.y + g.height for _m, g in pairs) - uy0
            iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
            if uw <= 0 or uh <= 0 or abs(iw / ih - uw / uh) > 0.02 * (uw / uh):
                return whole
            sx, sy = iw / uw, ih / uh
            return [(m, (round((g.x - ux0) * sx), round((g.y - uy0) * sy),
                         round(g.width * sx), round(g.height * sy)))
                    for m, g in pairs]
        except Exception:
            return whole

    def _monitor_rects_image(self):
        """Monitor rects in image coordinates, for snapping a selection to
        their edges; [] with one monitor, where there is nothing to snap."""
        layout = self._monitor_layout()
        return [rect for _m, rect in layout] if len(layout) > 1 else []

    def _view_of(self, area):
        """The view whose canvas is *area*."""
        for view in self._views:
            if view.area is area:
                return view
        return self._views[0]

    def _home_view(self):
        """The view the selection's bars belong in: the one holding the
        selection's centre, or the nearest when the centre falls between
        monitors."""
        if len(self._views) == 1:
            return self._views[0]
        if not self.sel:
            return self._view
        x, y, w, h = self.sel
        cx, cy = x + w / 2, y + h / 2

        def distance(view):
            vx, vy, vw, vh = view.rect
            dx = max(vx - cx, 0, cx - (vx + vw))
            dy = max(vy - cy, 0, cy - (vy + vh))
            return dx * dx + dy * dy
        return min(self._views, key=distance)

    def _redraw(self):
        """Every view shows the same selection and shapes; redraw them all."""
        for view in self._views:
            view.area.queue_draw()

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
