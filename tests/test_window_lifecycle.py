"""Window removal must release the application's matching manual hold."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.util.lifecycle import release_on_window_removed


class SignalApp:
    def __init__(self):
        self.handlers = {}
        self.next_handler = 1
        self.manual_holds = 0

    def hold(self):
        self.manual_holds += 1

    def connect(self, signal_name, callback):
        if signal_name != "window-removed":
            raise AssertionError(f"unexpected signal: {signal_name}")
        handler = self.next_handler
        self.next_handler += 1
        self.handlers[handler] = callback
        return handler

    def disconnect(self, handler):
        del self.handlers[handler]

    def release(self):
        self.manual_holds -= 1
        if self.manual_holds < 0:
            raise AssertionError("manual hold released more than once")

    def remove_window(self, window):
        for handler, callback in list(self.handlers.items()):
            if handler in self.handlers:
                callback(self, window)


class WindowLifecycleTests(unittest.TestCase):
    def test_removal_releases_only_matching_hold_once(self):
        app = SignalApp()
        overlay = object()
        editor = object()
        app.hold()
        release_on_window_removed(app, overlay)
        app.hold()
        release_on_window_removed(app, editor)

        app.remove_window(object())
        self.assertEqual(app.manual_holds, 2)

        app.remove_window(overlay)
        self.assertEqual(app.manual_holds, 1)
        self.assertEqual(len(app.handlers), 1)

        app.remove_window(overlay)
        self.assertEqual(app.manual_holds, 1)

        app.remove_window(editor)
        self.assertEqual(app.manual_holds, 0)
        self.assertEqual(app.handlers, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
