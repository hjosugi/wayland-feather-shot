"""Maintenance commands for source/install.sh managed installs."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from . import APP_ID


OLD_APP_ID = "wayland-feather-shot"


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
    for path in installed_paths(prefix, home_path, system):
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


def run_updater(command: str | None, stdout: TextIO | None = None,
                stderr: TextIO | None = None) -> int:
    """Run an updater subcommand. Returns a process exit code."""
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr

    if command != "remove":
        print("usage: wayland-feather-shot updater remove", file=stderr)
        return 2

    result = remove_installation()
    if result.removed:
        print(f"Removed {len(result.removed)} install path(s) from "
              f"{result.prefix}.", file=stdout)
    else:
        print(f"No install files found under {result.prefix}.", file=stdout)
    print(f"Config kept: {result.config_dir}", file=stdout)
    return 0
