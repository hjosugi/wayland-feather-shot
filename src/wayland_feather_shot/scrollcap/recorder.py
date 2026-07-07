"""Scrolling capture.

Wayland apps cannot read another window's off-screen content, so scrolling
capture works by recording the screen (ScreenCast portal -> PipeWire ->
GStreamer) while the *user* scrolls, automatically keeping one frame per
scroll pause, then stitching the kept frames into one tall image.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from ..i18n import _, tr
from ..portal import Portal, ScreenCastSession
from . import stitcher
from .stitcher import Frame

MAX_FRAMES = 80


def gstreamer_available() -> bool:
    try:
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst  # noqa: F401
        return True
    except (ImportError, ValueError):
        return False


def _warning_text(result) -> Optional[str]:
    """A short, user-facing note if some frames could not be stitched, so a
    silently mis-stitched capture doesn't look complete.  None when clean."""
    warnings = getattr(result, "warnings", [])
    if not warnings:
        return None
    n = len(warnings)
    reasons = {_(w.reason) for w in warnings}
    detail = "; ".join(sorted(reasons))
    return tr("{n} frame(s) skipped while stitching: {detail}",
              n=n, detail=detail)


class FrameSelector:
    """Damage-driven frame keeper.

    PipeWire screen casts only deliver frames when the screen changes, so
    "the user stopped scrolling" shows up as *frames no longer arriving*.
    A periodic tick keeps the latest frame once it has been quiet for
    settle_seconds and differs from the last kept frame.
    """

    def __init__(self, settle_seconds: float = 0.35, change_delta: float = 3.0):
        self.settle = settle_seconds
        self.delta = change_delta
        self.lock = threading.Lock()
        self.kept: List[Frame] = []
        self._latest: Optional[Frame] = None
        self._latest_at = 0.0
        self._latest_sig = None
        self._kept_sig = None

    def push(self, frame: Frame):
        with self.lock:
            self._latest = frame
            self._latest_at = time.monotonic()
            self._latest_sig = None  # recompute lazily on tick

    def tick(self) -> bool:
        """Returns True when a new frame was kept."""
        with self.lock:
            frame = self._latest
            if frame is None or len(self.kept) >= MAX_FRAMES:
                return False
            if time.monotonic() - self._latest_at < self.settle:
                return False
            if self._latest_sig is None:
                self._latest_sig = stitcher.frame_signature(frame)
            if (self._kept_sig is not None and
                    stitcher.signature_diff(self._latest_sig,
                                            self._kept_sig) < self.delta):
                return False
            self.kept.append(frame)
            self._kept_sig = self._latest_sig
            return True

    def flush(self):
        """Keep the very last frame on finish, if it adds anything."""
        with self.lock:
            frame = self._latest
            if frame is None or len(self.kept) >= MAX_FRAMES:
                return
            sig = stitcher.frame_signature(frame)
            if (self._kept_sig is None or
                    stitcher.signature_diff(sig, self._kept_sig) >= self.delta):
                self.kept.append(frame)


class ScrollRecorder:
    """Owns the portal session + GStreamer pipeline and the selector."""

    def __init__(self, portal: Portal, settings):
        self.portal = portal
        self.settings = settings
        self.session = ScreenCastSession(portal)
        self.selector = FrameSelector(
            settle_seconds=float(settings.scroll_settle_seconds))
        self.pipeline = None
        self._tick_id = 0
        self.on_kept: Optional[Callable[[int], None]] = None  # main thread

    def start(self, callback):
        """callback(ok, error_msg) once the stream is running."""
        from gi.repository import Gst
        Gst.init(None)

        def on_session(node_id, fd, error):
            if node_id is None:
                callback(False, error)
                return
            try:
                self._build_pipeline(node_id, fd)
            except GLib.Error as e:
                callback(False, f"GStreamer pipeline failed: {e}")
                return
            self._tick_id = GLib.timeout_add(150, self._tick)
            callback(True, None)

        self.session.start(on_session)

    def _build_pipeline(self, node_id, fd):
        from gi.repository import Gst
        desc = (
            f"pipewiresrc fd={fd} path={node_id} do-timestamp=true "
            "! videoconvert "
            "! video/x-raw,format=RGBA "
            "! appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false"
        )
        self.pipeline = Gst.parse_launch(desc)
        sink = self.pipeline.get_by_name("sink")
        sink.connect("new-sample", self._on_sample)
        self.pipeline.set_state(Gst.State.PLAYING)

    def _on_sample(self, sink):
        from gi.repository import Gst
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        caps = sample.get_caps().get_structure(0)
        width = caps.get_value("width")
        height = caps.get_value("height")
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if ok:
            data = bytes(mapinfo.data)
            buf.unmap(mapinfo)
            stride = len(data) // height if height else 0
            if stride >= width * 4:
                self.selector.push(Frame(data, width, height, stride))
        return Gst.FlowReturn.OK

    def _tick(self):
        if self.selector.tick() and self.on_kept:
            self.on_kept(len(self.selector.kept))
        return True

    def stop(self) -> List[Frame]:
        from gi.repository import Gst
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = 0
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        self.session.close()
        self.selector.flush()
        return list(self.selector.kept)


class ScrollCaptureWindow(Gtk.ApplicationWindow):
    """Small control panel shown while recording a scrolling capture."""

    def __init__(self, app, settings, on_result, auto: bool = False):
        """on_result(pixbuf_or_None, error_msg).  auto=True drives scrolling
        through the RemoteDesktop portal instead of the user (experimental)."""
        super().__init__(application=app,
                         title=_("Scrolling capture — Feather Shot"))
        self.settings = settings
        self.on_result = on_result
        self.auto = auto
        self._portal: Optional[Portal] = None
        self._remote = None
        self._auto_id = 0
        self._auto_ctl = None       # AutoScrollController while auto-scrolling
        self._recorder: Optional[ScrollRecorder] = None
        self._done = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(20)
        box.set_margin_end(20)
        self.set_child(box)

        self._status = Gtk.Label(
            label=_("Choose the window or screen to record\nin the portal dialog…"))
        self._status.set_justify(Gtk.Justification.CENTER)
        box.append(self._status)

        self._count = Gtk.Label(label=tr("frames kept: {n}", n=0))
        box.append(self._count)

        # Auto-scroll toggle — disabled until we know the RemoteDesktop portal
        # is present (decided in begin(); manual scrolling is the safe default).
        self._auto_check = Gtk.CheckButton(label=_("Auto-scroll (experimental)"))
        self._auto_check.set_halign(Gtk.Align.CENTER)
        self._auto_check.set_sensitive(False)
        self._auto_check.set_tooltip_text(
            _("Checking for the RemoteDesktop portal…"))
        self._auto_check.connect("toggled", self._on_auto_toggled)
        box.append(self._auto_check)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btns.set_halign(Gtk.Align.CENTER)
        self._finish = Gtk.Button(label=_("Finish && stitch"))
        self._finish.add_css_class("suggested-action")
        self._finish.set_sensitive(False)
        self._finish.connect("clicked", lambda *_: self.finish())
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda *_: self.cancel())
        btns.append(self._finish)
        btns.append(cancel)
        box.append(btns)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.set_default_size(360, -1)

    def begin(self, portal: Portal):
        self._portal = portal
        self._recorder = ScrollRecorder(portal, self.settings)
        self._recorder.on_kept = lambda n: self._count.set_text(
            tr("frames kept: {n}", n=n))

        def started(ok, error):
            if not ok:
                self._emit(None, error or "screen cast failed")
                return
            self._finish.set_sensitive(True)
            self._status.set_text(_(
                "Recording.  Scroll the content slowly, top to bottom,\n"
                "pausing briefly after each scroll.\n"
                "Then press “Finish & stitch”  (or Enter)."))
            self._offer_auto_scroll(portal)

        self._recorder.start(started)

    def _offer_auto_scroll(self, portal):
        """Enable the auto-scroll toggle only when the portal can inject input.

        Satisfies the #3 acceptance criterion "auto mode is offered only when
        the portal is actually available".  If the CLI asked for --auto and the
        portal is present, tick the box (which starts auto-scroll); otherwise
        leave it disabled and stay in manual mode.
        """
        from ..portal import RemoteDesktop
        if RemoteDesktop.available(portal):
            self._auto_check.set_sensitive(True)
            self._auto_check.set_tooltip_text(_(
                "Drive scrolling automatically via the RemoteDesktop portal.  "
                "Hover the pointer over the scrollable content first."))
            if self.auto and not self._auto_check.get_active():
                self._auto_check.set_active(True)   # -> _on_auto_toggled starts
        else:
            self.auto = False
            self._auto_check.set_active(False)
            self._auto_check.set_sensitive(False)
            self._auto_check.set_tooltip_text(_(
                "RemoteDesktop portal not available on this desktop — "
                "scroll manually."))

    # -- optional auto-scroll (RemoteDesktop portal, experimental) ----------

    def _on_auto_toggled(self, check):
        active = check.get_active()
        self.auto = active
        if active:
            if self._recorder is not None and self._remote is None:
                self._begin_auto_scroll(self._portal)
        else:
            self._stop_auto()
            if self._recorder is not None and not self._done:
                self._status.set_text(
                    _("Manual scroll — scroll the content yourself."))

    def _begin_auto_scroll(self, portal):
        from ..portal import RemoteDesktop
        from .autoscroll import AutoScrollController
        if portal is None or not RemoteDesktop.available(portal):
            self._status.set_text(_("Auto-scroll unavailable — scroll manually."))
            self._auto_check.set_active(False)
            return
        self._remote = RemoteDesktop(portal)
        self._auto_ctl = AutoScrollController(
            max_steps=self.settings.scroll_auto_steps,
            delta=self.settings.scroll_auto_delta)

        def ready(ok, error):
            if not ok:
                self._status.set_text(
                    _("Auto-scroll unavailable — scroll manually."))
                self._remote = None
                self._auto_ctl = None
                self._auto_check.set_active(False)
                return
            self._status.set_text(_("Auto-scrolling…  it stops at the bottom."))
            interval = int(float(self.settings.scroll_auto_interval) * 1000)
            self._auto_id = GLib.timeout_add(max(200, interval), self._auto_tick)

        self._remote.start(ready)

    def _auto_tick(self):
        if self._done or self._remote is None or self._auto_ctl is None:
            return False
        kept = len(self._recorder.selector.kept) if self._recorder else 0
        decision = self._auto_ctl.tick(kept)
        if not decision.scroll:
            # Reached the step cap or the bottom of the page — stitch what we
            # have.  finish() calls _stop_auto(), so clear our timer id first.
            self._auto_id = 0
            self.finish()
            return False
        self._remote.scroll(decision.delta)
        return True

    def _stop_auto(self):
        if self._auto_id:
            GLib.source_remove(self._auto_id)
            self._auto_id = 0
        self._auto_ctl = None
        if self._remote is not None:
            self._remote.close()
            self._remote = None

    def _on_key(self, _ctrl, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            self.cancel()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self._finish.get_sensitive():
                self.finish()
            return True
        return False

    def cancel(self):
        self._stop_auto()
        if self._recorder:
            self._recorder.stop()
            self._recorder = None
        self._emit(None, "cancelled")

    def finish(self):
        self._stop_auto()
        if not self._recorder:
            return
        frames = self._recorder.stop()
        self._recorder = None
        if not frames:
            self._emit(None, _("no frames captured — was anything scrolled?"))
            return
        self._status.set_text(tr("Stitching {n} frames…", n=len(frames)))
        self._finish.set_sensitive(False)

        top = int(self.settings.scroll_top_margin)
        bottom = int(self.settings.scroll_bottom_margin)
        max_h = int(self.settings.scroll_max_height)

        def work():
            result = stitcher.stitch(frames, top_margin=top, bottom_margin=bottom)
            GLib.idle_add(done, result)

        def done(result):
            if result is None:
                self._emit(None, _("stitching failed"))
                return False
            height = min(result.height, max_h)
            data = bytes(result.data[: height * result.width * 4])
            pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
                GLib.Bytes.new(data), GdkPixbuf.Colorspace.RGB, True, 8,
                result.width, height, result.width * 4)
            self._emit(pixbuf.copy(), None, _warning_text(result))
            return False

        threading.Thread(target=work, daemon=True).start()

    def _emit(self, pixbuf, error, warning=None):
        if self._done:
            return
        self._done = True
        self.on_result(pixbuf, error, warning)
        self.close()
