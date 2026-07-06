"""Tests for Settings get/set/save round-trip (no GTK needed).

Run:  python3 tests/test_settings.py
"""

import importlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def fresh_settings(config_home):
    os.environ["XDG_CONFIG_HOME"] = config_home
    import wayland_feather_shot.settings as settings
    return importlib.reload(settings)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = {k: os.environ.get(k) for k in ("XDG_CONFIG_HOME", "HOME")}
        os.environ["HOME"] = self._tmp.name
        self.mod = fresh_settings(self._tmp.name)

    def tearDown(self):
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def test_set_coerces_types(self):
        s = self.mod.Settings()
        self.assertTrue(s.set("blur_factor", "12"))       # int from str
        self.assertEqual(s.get("blur_factor"), 12)
        self.assertTrue(s.set("pen_width", "4.5"))        # float from str
        self.assertEqual(s.get("pen_width"), 4.5)
        self.assertTrue(s.set("pen_color", "#00ff00"))    # str
        self.assertEqual(s.get("pen_color"), "#00ff00")

    def test_set_rejects_unknown_and_bad(self):
        s = self.mod.Settings()
        self.assertFalse(s.set("does_not_exist", 1))
        self.assertFalse(s.set("blur_factor", "not-a-number"))

    def test_save_and_reload_round_trip(self):
        s = self.mod.Settings()
        s.set("blur_factor", 20)
        s.set("save_dir", "/tmp/shots")
        s.save()
        with open(self.mod.CONFIG_PATH, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["blur_factor"], 20)
        s2 = self.mod.Settings()
        self.assertEqual(s2.get("blur_factor"), 20)
        self.assertEqual(s2.get("save_dir"), "/tmp/shots")

    def test_default_save_dir_follows_xdg_pictures(self):
        user_dirs = os.path.join(self._tmp.name, "user-dirs.dirs")
        with open(user_dirs, "w", encoding="utf-8") as f:
            f.write('XDG_PICTURES_DIR="$HOME/画像"\n')
        s = self.mod.Settings()
        self.assertEqual(s.get("save_dir"), "")
        self.assertEqual(s.save_dir_path,
                         os.path.join(self._tmp.name, "画像", "Screenshots"))
        self.assertTrue(os.path.isdir(s.save_dir_path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
