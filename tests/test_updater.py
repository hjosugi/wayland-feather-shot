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

    def _gear_lever(self, name="feather_shot"):
        """What Gear Lever wrote for the AppImage of an older release."""
        appimages = self.home / "AppImages"
        appimage = appimages / f"{name}.appimage"
        icon = appimages / ".icons" / name
        self._touch(appimage)
        self._touch(icon)
        entry = (self.home / ".local" / "share" / "applications" /
                 f"{name}.desktop")
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Feather Shot\n"
            f"Icon={icon}\n"
            f"TryExec={appimage}\n"
            f"Exec=env DESKTOPINTEGRATION=1 {appimage} gui\n"
            "X-AppImage-Name=Feather Shot\n"
            "\n[Desktop Action full]\n"
            "Name=Capture full screen\n"
            f"Exec={appimage} full\n",
            encoding="utf-8")
        return entry, appimage, icon

    def test_remove_deletes_appimage_manager_integration(self):
        entry, appimage, icon = self._gear_lever()
        other = self.home / "AppImages" / "other.appimage"
        self._touch(other)

        result = updater.remove_installation(
            prefix=self.prefix, home=self.home, system=False,
            refresh_caches=False)

        for path in (entry, appimage, icon):
            self.assertFalse(path.exists(), path)
            self.assertIn(path, result.removed)
        self.assertTrue(other.exists())

    def test_appimage_entry_found_by_exec_without_marker(self):
        appimage = self.home / "Applications" / "Feather_Shot-x86_64.AppImage"
        self._touch(appimage)
        entry = (self.home / ".local" / "share" / "applications" /
                 "appimagekit_0123-Feather_Shot.desktop")
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(
            "[Desktop Entry]\nName=Feather Shot\n"
            f"Exec={appimage} gui\nIcon=appimagekit_0123_feather\n",
            encoding="utf-8")

        paths = updater.appimage_integration_paths(self.home)

        self.assertEqual(paths, [entry, appimage])

    def test_symlinked_entry_is_left_alone(self):
        """soar links the entry of the copy it manages into applications/."""
        package = self.root / "soar" / "packages" / "wfs-0.15.0"
        self._touch(package / "wayland-feather-shot.desktop")
        (package / "wayland-feather-shot.desktop").write_text(
            "[Desktop Entry]\nName=Feather Shot\n"
            "Exec=/x/soar/bin/wayland-feather-shot gui\n"
            "X-AppImage-Name=Feather Shot\n", encoding="utf-8")
        apps = self.home / ".local" / "share" / "applications"
        apps.mkdir(parents=True)
        link = apps / "wayland-feather-shot-soar.desktop"
        link.symlink_to(package / "wayland-feather-shot.desktop")

        self.assertEqual(updater.appimage_integration_paths(self.home), [])

    def test_unrelated_desktop_entries_are_kept(self):
        apps = self.home / ".local" / "share" / "applications"
        apps.mkdir(parents=True)
        (apps / "other.desktop").write_text(
            "[Desktop Entry]\nName=Other\nExec=/opt/Other.AppImage\n",
            encoding="utf-8")
        (apps / "feather-src.desktop").write_text(
            "[Desktop Entry]\nName=Feather Shot\n"
            "Exec=/src/wayland-feather-shot/bin/wayland-feather-shot gui\n",
            encoding="utf-8")

        self.assertEqual(updater.appimage_integration_paths(self.home), [])

    def test_hidden_autostart_override_is_kept(self):
        autostart = (self.home / ".config" / "autostart" /
                     f"{APP_ID}.Daemon.desktop")
        autostart.parent.mkdir(parents=True)
        autostart.write_text(
            "[Desktop Entry]\nType=Application\n"
            "Exec=wayland-feather-shot daemon\nHidden=true\n",
            encoding="utf-8")

        updater.remove_installation(
            prefix=self.prefix, home=self.home, system=False,
            refresh_caches=False)

        self.assertTrue(autostart.exists())

    def test_remove_reports_missing_paths(self):
        result = updater.remove_installation(
            prefix=self.prefix, home=self.home, system=False,
            refresh_caches=False)
        self.assertEqual(result.removed, [])
        self.assertTrue(result.missing)


if __name__ == "__main__":
    unittest.main(verbosity=2)
