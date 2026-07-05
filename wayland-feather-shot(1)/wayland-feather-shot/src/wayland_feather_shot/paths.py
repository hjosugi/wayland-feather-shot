"""Filesystem helpers.

All paths are local. This project intentionally has no upload, sync, account,
or telemetry paths.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

APP_DIR_NAME = "wayland-feather-shot"


def xdg_pictures_dir() -> Path:
    """Return the best local Pictures directory without calling external tools."""
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "user-dirs.dirs"
    if config.exists():
        for line in config.read_text(errors="ignore").splitlines():
            if line.startswith("XDG_PICTURES_DIR="):
                raw = line.split("=", 1)[1].strip().strip('"')
                raw = raw.replace("$HOME", str(Path.home()))
                return Path(raw).expanduser()
    return Path.home() / "Pictures"


def screenshots_dir() -> Path:
    path = xdg_pictures_dir() / "Screenshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_screenshot_path(prefix: str = "wfs") -> Path:
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return screenshots_dir() / f"{prefix}_{now}.png"


def state_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    path = base / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    path = base / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path
