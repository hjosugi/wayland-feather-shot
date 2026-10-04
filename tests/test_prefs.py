"""The settings window leads to the desktop's keyboard settings, where the
capture keys are changed.

Needs a GTK display; skips otherwise.
Run:  python3 tests/test_prefs.py
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import gi  # noqa: E402
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gtk  # noqa: E402
    HAVE_GTK_DISPLAY = Gdk.Display.get_default() is not None
except (ImportError, ValueError):
    HAVE_GTK_DISPLAY = False
if HAVE_GTK_DISPLAY:
    from wayland_feather_shot.util import hotkey  # noqa: E402
    from wayland_feather_shot.prefs import SettingsWindow  # noqa: E402
    from wayland_feather_shot.util.settings import Settings  # noqa: E402


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class CaptureKeysTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.PrefsTest")
        cls.app.register(None)

    def setUp(self):
        self.window = SettingsWindow(self.app, Settings())
        self.addCleanup(self.window.destroy)

    def test_the_desktops_keyboard_settings_open(self):
        with patch.object(hotkey, "detect_desktop", return_value="gnome"), \
                patch.object(hotkey, "shortcut_settings_command",
                             return_value=["gnome-control-center",
                                           "keyboard"]), \
                patch("subprocess.Popen") as popen, \
                patch.object(Gtk.AlertDialog, "show") as shown:
            self.window.open_shortcut_settings()
        self.assertEqual(popen.call_args[0][0],
                         ["gnome-control-center", "keyboard"])
        shown.assert_not_called()

    def test_without_a_settings_app_it_says_how_to_bind_them(self):
        with patch.object(hotkey, "detect_desktop", return_value="sway"), \
                patch.object(hotkey, "shortcut_settings_command",
                             return_value=None), \
                patch("subprocess.Popen") as popen, \
                patch.object(Gtk.AlertDialog, "show") as shown:
            self.window.open_shortcut_settings()
        popen.assert_not_called()
        shown.assert_called_once()


if __name__ == "__main__":
    unittest.main()
