"""XDG filesystem helpers.

All paths are local. This project intentionally has no upload, sync,
account or telemetry paths.
"""

from __future__ import annotations

import os
from pathlib import Path


def xdg_pictures_dir() -> Path:
    """Best local Pictures directory, honouring localized XDG user dirs
    (e.g. ~/画像 on Japanese desktops) without calling external tools."""
    config = Path(os.environ.get("XDG_CONFIG_HOME",
                                 Path.home() / ".config")) / "user-dirs.dirs"
    try:
        lines = config.read_text(errors="ignore").splitlines()
    except OSError:
        lines = []
    for line in lines:
        if line.startswith("XDG_PICTURES_DIR="):
            raw = line.split("=", 1)[1].strip().strip('"')
            raw = raw.replace("$HOME", str(Path.home()))
            if raw:
                return Path(raw).expanduser()
    return Path.home() / "Pictures"


def default_screenshots_dir() -> Path:
    """Default quick-save directory (not created here)."""
    return xdg_pictures_dir() / "Screenshots"
