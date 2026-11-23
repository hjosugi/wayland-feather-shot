"""Maintenance commands: remove copies installed outside a package manager.

``updater remove`` takes out what ``install.sh`` put under a prefix, and
what an AppImage manager (Gear Lever, AppImageLauncher) integrated from an
older AppImage: its desktop entry, the AppImage and the icon it extracted.
Those copies are invisible to the package manager that later installs the
app -- soar, pacman, flatpak -- so they stay in the app grid as a second
"Feather Shot" that never updates. A desktop entry that is a symlink is
left alone: that is how soar links the entry of the copy it manages.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import APP_ID


OLD_APP_ID = "wayland-feather-shot"
APP_NAME = "Feather Shot"


@dataclass(frozen=True)
class RemovalResult:
    prefix: Path
    removed: list[Path]
    missing: list[Path]
    config_dir: Path


def default_prefix(system: bool | None = None) -> Path:
    """Return the prefix used by ``install.sh`` for the current privilege."""
    if system is None:
        system = (os.geteuid() == 0)
    return Path("/usr/local") if system else Path.home() / ".local"


def config_dir(home: Path | None = None) -> Path:
    """Return the app config directory kept by removal."""
    if home is None:
        base = Path(os.environ.get("XDG_CONFIG_HOME",
                                   os.path.expanduser("~/.config")))
    else:
        base = home / ".config"
    return base / "wayland-feather-shot"


def installed_paths(prefix: Path | None = None, home: Path | None = None,
                    system: bool | None = None) -> list[Path]:
    """Paths installed by ``install.sh`` and older pre-0.2 names."""
    if system is None:
        system = (os.geteuid() == 0)
    prefix = Path(prefix) if prefix is not None else default_prefix(system)
    home = Path(home) if home is not None else Path.home()

    paths = [
        prefix / "share" / "wayland-feather-shot",
        prefix / "bin" / "wayland-feather-shot",
        prefix / "share" / "applications" / f"{APP_ID}.desktop",
        prefix / "share" / "applications" / f"{OLD_APP_ID}.desktop",
        prefix / "share" / "icons" / "hicolor" / "scalable" / "apps" /
        f"{APP_ID}.svg",
        prefix / "share" / "icons" / "hicolor" / "scalable" / "apps" /
        f"{OLD_APP_ID}.svg",
        prefix / "share" / "metainfo" / f"{APP_ID}.metainfo.xml",
    ]
    if not system:
        autostart = home / ".config" / "autostart"
        paths.extend([
            autostart / f"{APP_ID}.Daemon.desktop",
            autostart / f"{OLD_APP_ID}-daemon.desktop",
        ])
    return paths


def _data_home(home: Path | None) -> Path:
    if home is None:
        return Path(os.environ.get("XDG_DATA_HOME",
                                   os.path.expanduser("~/.local/share")))
    return home / ".local" / "share"


def _desktop_entry(path: Path) -> dict[str, str]:
    """The keys of a desktop file's [Desktop Entry] group."""
    keys: dict[str, str] = {}
    group = None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return keys
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            group = line[1:-1]
        elif group == "Desktop Entry" and "=" in line:
            key, value = line.split("=", 1)
            keys.setdefault(key.strip(), value.strip())
    return keys


def _exec_target(keys: dict[str, str]) -> Path | None:
    """The program a desktop entry runs, skipping an ``env VAR=value`` prefix."""
    if keys.get("TryExec"):
        return Path(keys["TryExec"])
    try:
        argv = shlex.split(keys.get("Exec", ""))
    except ValueError:
        return None
    if argv and argv[0] == "env":
        argv = argv[1:]
        while argv and "=" in argv[0]:
            argv = argv[1:]
    return Path(argv[0]) if argv else None


def appimage_integration_paths(home: Path | None = None) -> list[Path]:
    """Desktop entries an AppImage manager wrote for this app, with the
    AppImage and icon they point at.

    Gear Lever names them after the app (``feather_shot.desktop`` running
    ``~/AppImages/feather_shot.appimage``, icon in ``~/AppImages/.icons``),
    AppImageLauncher after a hash, so entries are matched on what they say
    rather than on their name: ``X-AppImage-Name``, or the app's name with an
    ``.AppImage`` to run.
    """
    apps = _data_home(home) / "applications"
    paths: list[Path] = []
    if not apps.is_dir():
        return paths
    for entry in sorted(apps.glob("*.desktop")):
        if entry.is_symlink():
            continue
        keys = _desktop_entry(entry)
        target = _exec_target(keys)
        runs_appimage = (target is not None and
                         target.suffix.lower() == ".appimage")
        if keys.get("X-AppImage-Name") != APP_NAME and not (
                keys.get("Name") == APP_NAME and runs_appimage):
            continue
        paths.append(entry)
        if runs_appimage and target.is_absolute():
            paths.append(target)
            icon = Path(keys.get("Icon", ""))
            if icon.is_absolute() and target.parent in icon.parents:
                paths.append(icon)
    return paths


def _is_user_override(path: Path) -> bool:
    """An autostart entry with Hidden=true switches another one off; it was
    written by the user, not by install.sh."""
    return _desktop_entry(path).get("Hidden", "").lower() == "true"


def _remove_path(path: Path) -> bool:
    """Remove a path like ``rm -rf`` without following directory symlinks."""
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            return False
    except FileNotFoundError:
        return False
    return True


def _refresh_desktop_caches(prefix: Path) -> None:
    deskdir = prefix / "share" / "applications"
    icondir = prefix / "share" / "icons" / "hicolor"
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(deskdir)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)
    if shutil.which("gtk-update-icon-cache"):
        subprocess.run(["gtk-update-icon-cache", "-q", str(icondir)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)


def remove_installation(prefix: Path | None = None, home: Path | None = None,
                        system: bool | None = None,
                        refresh_caches: bool = True) -> RemovalResult:
    """Remove files installed by ``install.sh`` and keep user config."""
    if system is None:
        system = (os.geteuid() == 0)
    prefix = Path(prefix) if prefix is not None else default_prefix(system)
    explicit_home = Path(home) if home is not None else None
    home_path = explicit_home or Path.home()

    removed: list[Path] = []
    missing: list[Path] = []
    paths = installed_paths(prefix, home_path, system)
    if not system:
        paths += appimage_integration_paths(explicit_home)
    for path in paths:
        if path.parent.name == "autostart" and _is_user_override(path):
            continue
        if _remove_path(path):
            removed.append(path)
        else:
            missing.append(path)

    if refresh_caches and removed:
        _refresh_desktop_caches(prefix)

    return RemovalResult(
        prefix=prefix,
        removed=removed,
        missing=missing,
        config_dir=config_dir(explicit_home),
    )


def run_updater(command: str | None) -> int:
    """Run an updater subcommand. Returns a process exit code."""
    if command != "remove":
        print("usage: wayland-feather-shot updater remove", file=sys.stderr)
        return 2

    result = remove_installation()
    if result.removed:
        print(f"Removed {len(result.removed)} path(s):")
        for path in result.removed:
            print(f"  {path}")
    else:
        print(f"No install files found under {result.prefix}, "
              "and no AppImage integration.")
    print(f"Config kept: {result.config_dir}")
    return 0
