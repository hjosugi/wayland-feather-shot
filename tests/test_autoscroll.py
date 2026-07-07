"""Tests for the pure auto-scroll control logic (no GTK / portal needed).

Run:  python3 tests/test_autoscroll.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.scrollcap import autoscroll  # noqa: E402
from wayland_feather_shot.scrollcap.autoscroll import (  # noqa: E402
    AutoScrollController, auto_scroll_availability, clamp_delta, sane_steps)


class ClampTests(unittest.TestCase):
    def test_delta_positive_passthrough(self):
        self.assertEqual(clamp_delta(500), 500.0)

    def test_delta_zero_and_negative_become_positive(self):
        self.assertEqual(clamp_delta(0), 1.0)
        self.assertEqual(clamp_delta(-40), 1.0)

    def test_delta_garbage_is_safe(self):
        self.assertEqual(clamp_delta("nope"), 1.0)
        self.assertEqual(clamp_delta(None), 1.0)
        self.assertEqual(clamp_delta(float("nan")), 1.0)

    def test_delta_capped(self):
        self.assertEqual(clamp_delta(10 ** 9), autoscroll.MAX_DELTA)

    def test_steps_clamped(self):
        self.assertEqual(sane_steps(24), 24)
        self.assertEqual(sane_steps(0), 1)
        self.assertEqual(sane_steps(-3), 1)
        self.assertEqual(sane_steps(10 ** 9), autoscroll.MAX_STEPS)
        self.assertEqual(sane_steps("bad"), 1)


class ControllerScrollTests(unittest.TestCase):
    def test_scrolls_while_progressing(self):
        ctl = AutoScrollController(max_steps=5, delta=500)
        # Each tick shows a new kept frame, so it should keep scrolling.
        for kept in range(1, 5):
            d = ctl.tick(kept)
            self.assertTrue(d.scroll)
            self.assertEqual(d.delta, 500.0)
        self.assertFalse(ctl.stopped)

    def test_stops_at_step_limit(self):
        ctl = AutoScrollController(max_steps=3, delta=100)
        kept = 0
        scrolls = 0
        for _ in range(20):
            kept += 1                       # always making progress
            d = ctl.tick(kept)
            if d.scroll:
                scrolls += 1
            else:
                break
        self.assertEqual(scrolls, 3)        # exactly the step budget
        self.assertTrue(ctl.stopped)
        self.assertIn("step limit", ctl.tick(kept).reason)

    def test_stops_when_stalled(self):
        ctl = AutoScrollController(max_steps=100, delta=100, stall_limit=3)
        # Frame count never advances -> three stalled ticks -> stop.
        d1 = ctl.tick(0)
        d2 = ctl.tick(0)
        d3 = ctl.tick(0)
        self.assertTrue(d1.scroll)
        self.assertTrue(d2.scroll)
        self.assertFalse(d3.scroll)
        self.assertIn("bottom", d3.reason)

    def test_progress_resets_stall(self):
        ctl = AutoScrollController(max_steps=100, delta=100, stall_limit=3)
        ctl.tick(0)          # stall 1
        ctl.tick(0)          # stall 2
        d = ctl.tick(1)      # progress -> stall resets, keep going
        self.assertTrue(d.scroll)
        self.assertEqual(ctl.stall_count, 0)

    def test_stopped_is_idempotent(self):
        ctl = AutoScrollController(max_steps=1, delta=100)
        self.assertTrue(ctl.tick(1).scroll)     # step 1
        stop = ctl.tick(2)                       # over budget -> stop
        self.assertFalse(stop.scroll)
        again = ctl.tick(3)
        self.assertFalse(again.scroll)
        self.assertEqual(again.reason, stop.reason)

    def test_bad_config_never_loops_forever(self):
        # delta=0 and steps=0 would be a footgun; the controller sanitizes both.
        ctl = AutoScrollController(max_steps=0, delta=0)
        d = ctl.tick(1)
        self.assertTrue(d.scroll)
        self.assertEqual(d.delta, 1.0)
        self.assertFalse(ctl.tick(2).scroll)     # max_steps clamped to 1


class AvailabilityTests(unittest.TestCase):
    def test_needs_both(self):
        ok, msg = auto_scroll_availability(remote_desktop=True, gstreamer=True)
        self.assertTrue(ok)
        self.assertIn("available", msg)

    def test_missing_remote_desktop(self):
        ok, msg = auto_scroll_availability(remote_desktop=False, gstreamer=True)
        self.assertFalse(ok)
        self.assertIn("RemoteDesktop", msg)

    def test_missing_gstreamer(self):
        ok, msg = auto_scroll_availability(remote_desktop=True, gstreamer=False)
        self.assertFalse(ok)
        self.assertIn("GStreamer", msg)

    def test_missing_both(self):
        ok, msg = auto_scroll_availability(remote_desktop=False, gstreamer=False)
        self.assertFalse(ok)
        self.assertIn("RemoteDesktop", msg)
        self.assertIn("GStreamer", msg)


if __name__ == "__main__":
    unittest.main()
