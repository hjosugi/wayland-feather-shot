"""Opening the full-screen overlay on the monitor the pointer is on.

The full-screen overlay is one window showing the whole screenshot, every
monitor's part fitted in (window.py), and it belongs on the monitor the key
was pressed on. Wayland has no call that says where the pointer is, and a
fullscreen window given no monitor goes where the compositor puts it, which
need not be there. A window does learn of the pointer once it is over it,
and the compositor tells a window that appears under the pointer straight
away, without the pointer moving.

So each monitor first gets a window showing its own part of the screenshot:
the screen looks frozen, as it does for a region capture. The overlay opens
on the monitor whose window the pointer enters first, and these windows
close.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .canvas import OverlayCanvas, color, rect

# With no word of the pointer by then (a touch screen, say), the overlay
# opens where the compositor puts it.
WAIT_MS = 500
# How long a monitor's frozen window stays under the overlay opening over
# it after the overlay's first frame, so the desktop does not show through
# while the compositor brings the overlay in (GNOME animates it 150 ms).
COVER_MS = 250


class PointerProbe:
    """A frozen window on each monitor of *layout* ((Gdk.Monitor, image
    rect) each) showing its part of *texture*, the screenshot, until the
    pointer enters one; then *overlay* opens on that monitor."""

    def __init__(self, overlay, texture, layout):
        self._overlay = overlay
        self._monitors = [monitor for monitor, _rect in layout]
        self._windows = [self._frozen_window(texture, index, area)
                         for index, (_monitor, area) in enumerate(layout)]
        self._timer = None
        self._done = False

    def start(self):
        for monitor, window in zip(self._monitors, self._windows):
            window.fullscreen_on_monitor(monitor)
            window.present()
        self._timer = GLib.timeout_add(WAIT_MS, self._timed_out)

    def _frozen_window(self, texture, index, area):
        """A window showing the image rect *area* as the overlay does at
        zoom 1, which reports the pointer entering it to _found."""
        vx, vy, vw, vh = area

        def draw(_canvas, snapshot, width, height):
            scale = min(width / vw, height / vh)
            ox = (width - vw * scale) / 2 - vx * scale
            oy = (height - vh * scale) / 2 - vy * scale
            snapshot.append_color(color(0, 0, 0), rect(0, 0, width, height))
            snapshot.append_texture(texture, rect(
                ox, oy, texture.get_width() * scale,
                texture.get_height() * scale))

        window = Gtk.Window(title="Feather Shot")
        window.set_decorated(False)
        canvas = OverlayCanvas(draw)
        canvas.set_cursor(Gdk.Cursor.new_from_name("crosshair"))
        window.set_child(canvas)
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self._found(index))
        window.add_controller(motion)
        return window

    def _found(self, index):
        """Open the overlay on the monitor of window *index* (None: where
        the compositor puts it). The other monitors' frozen windows close
        now, the one it opens over once it has appeared."""
        if self._done:
            return
        self._done = True
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        overlay = self._overlay
        if index is None:
            covering = list(self._windows)
        else:
            covering = [self._windows[index]]
            overlay.fullscreen_on_monitor(self._monitors[index])
        for window in self._windows:
            if window not in covering:
                window.destroy()
        overlay.present()

        clock = overlay.get_frame_clock()
        if clock is None:
            GLib.timeout_add(COVER_MS, _close, covering)
            return

        def painted(_clock):
            clock.disconnect(handler)
            GLib.timeout_add(COVER_MS, _close, covering)

        handler = clock.connect("after-paint", painted)

    def _timed_out(self):
        self._timer = None
        self._found(None)
        return False


def _close(windows):
    for window in windows:
        window.destroy()
    return False
