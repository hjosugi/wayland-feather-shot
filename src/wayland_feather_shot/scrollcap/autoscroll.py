"""Auto-scroll control logic (issue #3).

Pure, GTK-free decision logic for the optional RemoteDesktop-portal auto-scroll,
so the "when do we scroll / when do we stop" policy can be reasoned about and
unit-tested without a Wayland session.  The GTK side
(:class:`~wayland_feather_shot.scrollcap.recorder.ScrollCaptureWindow`) is a thin
adapter: on each timer tick it asks the controller what to do and either injects
one scroll event through the RemoteDesktop portal or stops and stitches.

Nothing here imports gi, so it is safe to pull into the import-light
``diagnose`` command as well.
"""

from __future__ import annotations

from dataclasses import dataclass

# Guard rails for values that come from user config (config.json), so a typo
# there can never turn into a runaway or zero-distance scroll loop.
MAX_DELTA = 20000.0
MAX_STEPS = 1000
DEFAULT_STALL_LIMIT = 3


def clamp_delta(delta) -> float:
    """A sane, strictly-positive per-step scroll distance (portal axis units)."""
    try:
        value = float(delta)
    except (TypeError, ValueError):
        value = 0.0
    if not value > 0:          # also catches NaN
        value = 1.0
    return min(value, MAX_DELTA)


def sane_steps(steps) -> int:
    """Clamp the configured step budget into [1, MAX_STEPS]."""
    try:
        value = int(steps)
    except (TypeError, ValueError):
        value = 0
    return max(1, min(value, MAX_STEPS))


@dataclass(frozen=True)
class AutoScrollDecision:
    """What the adapter should do this tick."""

    scroll: bool               # inject a scroll event?
    delta: float = 0.0         # distance, when scroll is True
    reason: str = ""           # why we stopped, when scroll is False


class AutoScrollController:
    """Decides, tick by tick, whether to keep auto-scrolling.

    Stops when the step budget is exhausted or when the recorder has kept no
    new frame for ``stall_limit`` consecutive ticks — i.e. the page reached the
    bottom or nothing is scrolling.  Progress is measured by the number of
    frames the :class:`FrameSelector` has kept, which the caller passes in on
    every :meth:`tick`.  Once stopped it stays stopped (idempotent).
    """

    def __init__(self, max_steps, delta, stall_limit: int = DEFAULT_STALL_LIMIT):
        self.max_steps = sane_steps(max_steps)
        self.delta = clamp_delta(delta)
        self.stall_limit = max(1, int(stall_limit))
        self.steps_taken = 0
        self.stall_count = 0
        self._last_kept = 0
        self._stopped_reason = ""

    @property
    def stopped(self) -> bool:
        return bool(self._stopped_reason)

    def tick(self, kept_frames: int) -> AutoScrollDecision:
        """Advance one step given how many frames have been kept so far."""
        if self._stopped_reason:
            return AutoScrollDecision(False, reason=self._stopped_reason)

        # kept_frames only ever grows; treat "no growth" as a stall so we stop
        # at the bottom of the page instead of scrolling into the void.
        if kept_frames <= self._last_kept:
            self.stall_count += 1
        else:
            self.stall_count = 0
        self._last_kept = kept_frames

        if self.steps_taken >= self.max_steps:
            return self._stop("reached the step limit")
        if self.stall_count >= self.stall_limit:
            return self._stop("no new content — reached the bottom")

        self.steps_taken += 1
        return AutoScrollDecision(True, delta=self.delta)

    def _stop(self, reason: str) -> AutoScrollDecision:
        self._stopped_reason = reason
        return AutoScrollDecision(False, reason=reason)


def auto_scroll_availability(remote_desktop: bool, gstreamer: bool) -> tuple:
    """Whether ``scroll --auto`` can actually drive scrolling on this machine.

    Auto-scroll needs *both* the RemoteDesktop portal (to inject scroll input)
    and the GStreamer/PipeWire recorder — the GStreamer-free repeated-screenshot
    fallback cannot be auto-driven.  Returns ``(usable, human_readable_reason)``.
    """
    if remote_desktop and gstreamer:
        return True, "available (RemoteDesktop portal + GStreamer/PipeWire)"
    missing = []
    if not remote_desktop:
        missing.append("RemoteDesktop portal")
    if not gstreamer:
        missing.append("GStreamer/PipeWire")
    return False, "manual scroll only — missing " + " and ".join(missing)
