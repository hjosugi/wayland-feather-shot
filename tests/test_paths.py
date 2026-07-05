"""Tests for the XDG path helpers (no GTK needed)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot import paths  # noqa: E402


class XdgPicturesDirTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self._old = {k: os.environ.get(k) for k in ("HOME", "XDG_CONFIG_HOME")}
        os.environ["HOME"] = str(self.home)
        os.environ.pop("XDG_CONFIG_HOME", None)

    def tearDown(self):
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def _write_user_dirs(self, line: str):
        config = self.home / ".config"
        config.mkdir(parents=True, exist_ok=True)
        (config / "user-dirs.dirs").write_text(line + "\n")

    def test_defaults_to_home_pictures(self):
        self.assertEqual(paths.xdg_pictures_dir(), self.home / "Pictures")

    def test_reads_localized_user_dirs(self):
        self._write_user_dirs('XDG_PICTURES_DIR="$HOME/画像"')
        self.assertEqual(paths.xdg_pictures_dir(), self.home / "画像")

    def test_ignores_empty_value(self):
        self._write_user_dirs('XDG_PICTURES_DIR=""')
        self.assertEqual(paths.xdg_pictures_dir(), self.home / "Pictures")

    def test_screenshots_dir_appends_subdir(self):
        self._write_user_dirs('XDG_PICTURES_DIR="$HOME/Bilder"')
        self.assertEqual(paths.default_screenshots_dir(),
                         self.home / "Bilder" / "Screenshots")


class DiagnosticsSmokeTests(unittest.TestCase):
    def test_run_checks_is_headless_safe(self):
        from wayland_feather_shot import diagnostics
        checks = diagnostics.run_checks()
        self.assertTrue(checks)
        for check in checks:
            self.assertIsInstance(check.name, str)
            self.assertIsInstance(check.ok, bool)
            self.assertIsInstance(check.detail, str)


if __name__ == "__main__":
    unittest.main()
