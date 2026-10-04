"""The renderer starts while the screenshot portal works, not after.

Needs a GTK display; skips otherwise.  Run:  python3 tests/test_warm_up.py
"""

import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import gi  # noqa: E402
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk  # noqa: E402,F401
    HAVE_GTK_DISPLAY = Gdk.Display.get_default() is not None
except (ImportError, ValueError):
    HAVE_GTK_DISPLAY = False
if HAVE_GTK_DISPLAY:
    from wayland_feather_shot.app import FeatherShotApp  # noqa: E402


class FakePending:
    """A portal request cli sent early, answered or not yet."""

    def __init__(self, result=None):
        self.started = time.time()
        self.result = result

    def then(self, callback):
        if self.result is not None:
            callback(*self.result)


def run_idle():
    context = GLib.MainContext.default()
    while context.iteration(False):
        pass


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class WarmUpTests(unittest.TestCase):
    def start(self, pending):
        app = FeatherShotApp(mode="gui", delay=0, pending_shot=pending)
        with patch("wayland_feather_shot.app.warm_up_renderer") as warm_up, \
                patch.object(app, "_open_capture"):
            app._start_screenshot()
            run_idle()
        return warm_up

    def test_the_renderer_warms_up_while_the_portal_works(self):
        self.start(FakePending()).assert_called_once_with()

    def test_an_answer_already_in_goes_straight_to_the_overlay(self):
        self.start(FakePending(("/tmp/shot.png", None))).assert_not_called()


if __name__ == "__main__":
    unittest.main()
