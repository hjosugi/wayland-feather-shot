"""Tests for GTK-free updater maintenance commands."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot import APP_ID, updater  # noqa: E402


class UpdaterRemoveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.prefix = self.root / ".local"
        self.home = self.root / "home"
        self.home.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _touch(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    def test_remove_installation_deletes_install_sh_paths(self):
        appdir = self.prefix / "share" / "wayland-feather-shot"
        appdir.mkdir(parents=True)
        self._touch(appdir / "src" / "placeholder.py")
        self._touch(self.prefix / "bin" / "wayland-feather-shot")
        self._touch(self.prefix / "share" / "applications" /
                    f"{APP_ID}.desktop")
        self._touch(self.prefix / "share" / "icons" / "hicolor" /
                    "scalable" / "apps" / f"{APP_ID}.svg")
        self._touch(self.prefix / "share" / "metainfo" /
                    f"{APP_ID}.metainfo.xml")
        self._touch(self.home / ".config" / "autostart" /
                    f"{APP_ID}.Daemon.desktop")

        config = self.home / ".config" / "wayland-feather-shot"
        self._touch(config / "config.json")

        result = updater.remove_installation(
            prefix=self.prefix, home=self.home, system=False,
            refresh_caches=False)

        self.assertFalse(appdir.exists())
        self.assertFalse((self.prefix / "bin" /
                          "wayland-feather-shot").exists())
        self.assertFalse((self.home / ".config" / "autostart" /
                          f"{APP_ID}.Daemon.desktop").exists())
        self.assertTrue((config / "config.json").exists())
        self.assertEqual(result.config_dir, config)
        self.assertGreaterEqual(len(result.removed), 6)

    def test_installed_paths_omits_autostart_for_system_install(self):
        paths = updater.installed_paths(
            prefix=Path("/usr/local"), home=self.home, system=True)
        self.assertFalse(any(".config/autostart" in str(path)
                             for path in paths))

    def test_remove_reports_missing_paths(self):
        result = updater.remove_installation(
            prefix=self.prefix, home=self.home, system=False,
            refresh_caches=False)
        self.assertEqual(result.removed, [])
        self.assertTrue(result.missing)


if __name__ == "__main__":
    unittest.main(verbosity=2)
