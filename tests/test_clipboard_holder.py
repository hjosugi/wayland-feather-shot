"""Tests for the clipboard holder's pure helpers (no GTK needed).

Run:  python3 tests/test_clipboard_holder.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot import clipboard_holder as ch  # noqa: E402


class HolderCommandTests(unittest.TestCase):
    def test_command_targets_the_module_and_path(self):
        cmd, env = ch.holder_command("/tmp/x.png", python="/usr/bin/python3")
        self.assertEqual(cmd[:3],
                         ["/usr/bin/python3", "-m",
                          "wayland_feather_shot.clipboard_holder"])
        self.assertEqual(cmd[3], "/tmp/x.png")

    def test_pythonpath_includes_package_src_root(self):
        cmd, env = ch.holder_command("/tmp/x.png")
        src = env["PYTHONPATH"].split(os.pathsep)[0]
        # the child must be able to import wayland_feather_shot from there
        self.assertTrue(os.path.isdir(os.path.join(src, "wayland_feather_shot")))

    def test_pythonpath_preserves_existing(self):
        old = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = "/some/where"
        try:
            _, env = ch.holder_command("/tmp/x.png")
            self.assertTrue(env["PYTHONPATH"].endswith(
                os.pathsep + "/some/where"))
        finally:
            if old is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = old

    def test_timeout_added_when_positive(self):
        cmd, _ = ch.holder_command("/tmp/x.png", timeout=30)
        self.assertIn("--timeout", cmd)
        self.assertEqual(cmd[cmd.index("--timeout") + 1], "30")
        cmd0, _ = ch.holder_command("/tmp/x.png", timeout=0)
        self.assertNotIn("--timeout", cmd0)


class ParseArgsTests(unittest.TestCase):
    def test_path_only(self):
        self.assertEqual(ch.parse_args(["a.png"]), ("a.png", 0))

    def test_path_and_timeout(self):
        self.assertEqual(ch.parse_args(["a.png", "--timeout", "60"]),
                         ("a.png", 60))
        self.assertEqual(ch.parse_args(["--timeout", "60", "a.png"]),
                         ("a.png", 60))

    def test_missing_path_raises(self):
        with self.assertRaises(SystemExit):
            ch.parse_args(["--timeout", "60"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
