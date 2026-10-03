"""A screen cast the user declines ends quietly, not as a portal failure.

Run:  python3 tests/test_portal_screencast.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import gi
    gi.require_version("Gtk", "4.0")
    from wayland_feather_shot.portal import ScreenCastSession
    HAVE_GI = True
except (ImportError, ValueError):
    HAVE_GI = False


class FakePortal:
    """Answers each request with the next response code in *codes*."""

    def __init__(self, codes):
        self.codes = list(codes)

    def _token(self):
        return "t"

    def request(self, _iface, _method, _build, _options, callback):
        callback(self.codes.pop(0), {"session_handle": "/session"})

    def close_session(self, _handle):
        pass


@unittest.skipUnless(HAVE_GI, "PyGObject unavailable")
class ScreenCastCancelTests(unittest.TestCase):
    def outcome(self, *codes):
        got = []
        ScreenCastSession(FakePortal(codes)).start(
            lambda node, fd, error: got.append(error))
        return got[0]

    def test_declining_the_share_dialog_is_a_cancel(self):
        # GNOME asks in Start; other backends may ask in SelectSources.
        self.assertEqual(self.outcome(0, 0, 1), "cancelled")
        self.assertEqual(self.outcome(0, 1), "cancelled")

    def test_a_portal_error_is_still_an_error(self):
        self.assertNotEqual(self.outcome(0, 0, 2), "cancelled")
        self.assertNotEqual(self.outcome(0, 2), "cancelled")


if __name__ == "__main__":
    unittest.main()
