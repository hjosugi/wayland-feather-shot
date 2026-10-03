"""A screenshot request sent early hands its answer over whenever it arrives.

Run:  python3 tests/test_portal_pending.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import gi
    gi.require_version("Gtk", "4.0")
    from wayland_feather_shot.portal import PendingScreenshot
    HAVE_GI = True
except (ImportError, ValueError):
    HAVE_GI = False


class FakePortal:
    def __init__(self):
        self.callback = None
        self.interactive = None

    def screenshot(self, callback, interactive=False):
        self.callback = callback
        self.interactive = interactive


@unittest.skipUnless(HAVE_GI, "PyGObject unavailable")
class PendingScreenshotTests(unittest.TestCase):
    def test_the_request_goes_out_at_once_and_the_answer_waits(self):
        portal = FakePortal()
        pending = PendingScreenshot(portal)
        self.assertIsNotNone(portal.callback)
        self.assertFalse(portal.interactive)
        got = []
        pending.then(lambda path, error: got.append((path, error)))
        self.assertEqual(got, [])
        portal.callback("/tmp/shot.png", None)
        self.assertEqual(got, [("/tmp/shot.png", None)])

    def test_an_answer_that_arrived_first_is_delivered_immediately(self):
        portal = FakePortal()
        pending = PendingScreenshot(portal)
        portal.callback(None, "cancelled")
        got = []
        pending.then(lambda path, error: got.append((path, error)))
        self.assertEqual(got, [(None, "cancelled")])

    def test_started_records_when_the_request_was_made(self):
        import time
        before = time.time()
        pending = PendingScreenshot(FakePortal())
        self.assertGreaterEqual(pending.started, before)


if __name__ == "__main__":
    unittest.main()
