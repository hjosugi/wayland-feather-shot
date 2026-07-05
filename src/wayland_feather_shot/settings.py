"""User settings, stored as JSON at ~/.config/wayland-feather-shot/config.json."""

from __future__ import annotations

import json
import os

from .paths import default_screenshots_dir

CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "wayland-feather-shot")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    # Where Ctrl+S drops files. Created on demand. Empty = auto: the XDG
    # Pictures directory (localized, e.g. ~/画像) + "/Screenshots".
    "save_dir": "",
    # strftime pattern for quick-save filenames.
    "filename_pattern": "feather-%Y-%m-%d_%H-%M-%S.png",
    # Default annotation style.
    "pen_color": "#ff3b30",
    "pen_width": 3.0,
    "font_size": 22.0,
    # Blur strength (higher = stronger). Pixelate block size derives from it.
    "blur_factor": 8,
    # Scroll capture: rows to exclude from every frame (-1 = auto-detect
    # sticky headers/footers).
    "scroll_top_margin": -1,
    "scroll_bottom_margin": -1,
    # Hard cap for stitched image height, in pixels.
    "scroll_max_height": 24000,
    # Seconds between "scene became still" and the frame being kept.
    "scroll_settle_seconds": 0.35,
}


class Settings:
    def __init__(self):
        self._data = dict(DEFAULTS)
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                for key in DEFAULTS:
                    if key in stored:
                        self._data[key] = stored[key]
        except (OSError, ValueError):
            pass

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name)

    @property
    def save_dir_path(self) -> str:
        configured = str(self._data["save_dir"]).strip()
        if configured:
            path = os.path.expanduser(configured)
        else:
            path = str(default_screenshots_dir())
        os.makedirs(path, exist_ok=True)
        return path

    def save(self) -> None:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def write_default_config_if_missing(self) -> None:
        if not os.path.exists(CONFIG_PATH):
            self.save()
