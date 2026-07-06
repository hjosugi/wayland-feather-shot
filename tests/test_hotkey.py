"""Tests for the pure global-shortcut helpers (no GTK needed).

Run:  python3 tests/test_hotkey.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot import hotkey  # noqa: E402


class DetectDesktopTests(unittest.TestCase):
    def test_hyprland_by_signature(self):
        env = {"HYPRLAND_INSTANCE_SIGNATURE": "abc", "XDG_CURRENT_DESKTOP": "X"}
        self.assertEqual(hotkey.detect_desktop(env), "hyprland")

    def test_sway_by_swaysock(self):
        self.assertEqual(hotkey.detect_desktop({"SWAYSOCK": "/run/sway"}), "sway")

    def test_gnome(self):
        self.assertEqual(hotkey.detect_desktop({"XDG_CURRENT_DESKTOP": "GNOME"}),
                         "gnome")
        self.assertEqual(
            hotkey.detect_desktop({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}),
            "gnome")

    def test_kde(self):
        self.assertEqual(hotkey.detect_desktop({"XDG_CURRENT_DESKTOP": "KDE"}),
                         "kde")
        self.assertEqual(
            hotkey.detect_desktop({"XDG_SESSION_DESKTOP": "plasma"}), "kde")

    def test_other(self):
        self.assertEqual(hotkey.detect_desktop({}), "other")
        self.assertEqual(
            hotkey.detect_desktop({"XDG_CURRENT_DESKTOP": "weston"}), "other")


class SetupHintTests(unittest.TestCase):
    def test_each_desktop_mentions_ctrl_print_or_daemon(self):
        for d in ("gnome", "kde", "hyprland", "sway", "other"):
            hint = hotkey.setup_hint(d, cmd="wfs")
            self.assertTrue(hint)
            self.assertTrue("Print" in hint or "daemon" in hint)

    def test_uses_given_command_name(self):
        self.assertIn("myapp gui", hotkey.setup_hint("sway", cmd="myapp"))


class ValidTriggerTests(unittest.TestCase):
    def test_valid(self):
        for t in ("CTRL+Print", "SHIFT+CTRL+F12", "Print", "SUPER+s"):
            self.assertTrue(hotkey.valid_trigger(t), t)

    def test_invalid(self):
        for t in ("", "+Print", "CTRL+", "CTRL++Print"):
            self.assertFalse(hotkey.valid_trigger(t), t)


class CaptureCommandTests(unittest.TestCase):
    def test_executable_launcher_reused(self):
        cmd, extra = hotkey.capture_command(
            "gui", argv0="/usr/bin/wayland-feather-shot",
            executable="/usr/bin/python3", src_dir="/opt/app/src",
            is_executable=lambda p: True)
        self.assertEqual(cmd, ["/usr/bin/wayland-feather-shot", "gui"])
        self.assertEqual(extra, {})

    def test_py_entrypoint_falls_back_to_module(self):
        cmd, extra = hotkey.capture_command(
            "scroll", argv0="/opt/app/src/wayland_feather_shot/__main__.py",
            executable="/usr/bin/python3", src_dir="/opt/app/src",
            is_executable=lambda p: True)
        self.assertEqual(cmd, ["/usr/bin/python3", "-m",
                               "wayland_feather_shot", "scroll"])
        self.assertEqual(extra["PYTHONPATH"], "/opt/app/src")

    def test_non_executable_falls_back_to_module(self):
        cmd, extra = hotkey.capture_command(
            "full", argv0="/some/wrapper", executable="/usr/bin/python3",
            src_dir="/opt/app/src", is_executable=lambda p: False)
        self.assertEqual(cmd[:3], ["/usr/bin/python3", "-m",
                                   "wayland_feather_shot"])
        self.assertEqual(extra["PYTHONPATH"], "/opt/app/src")


if __name__ == "__main__":
    unittest.main(verbosity=2)
