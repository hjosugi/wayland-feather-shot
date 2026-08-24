"""The working annotation style, remembered between sessions.

Every editor session started from the configured defaults, and anything
adjusted while annotating was lost when the window closed — so someone who
always annotates in yellow at width 8 re-picked it on every single capture.

This is deliberately **separate from `config.json`**: those are the defaults a
user chose, and overwriting them with whatever the last session happened to end
on would make "reset to defaults" meaningless.  This file is just where the
editor left off.

Decoding is per-field with fallbacks, so a preset written by a different
version — or a hand-edited one with a typo in it — degrades to the default for
that field instead of throwing the whole thing away.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Optional, Tuple

from ..settings import CONFIG_DIR

PRESET_PATH = os.path.join(CONFIG_DIR, "editor-preset.json")

TOOLS = ("pen", "line", "arrow", "steparrow", "bubble", "emoji", "rect",
         "ellipse", "highlight", "spotlight", "text", "blur", "pixelate",
         "marker", "crop", "select")
ALIGNMENTS = ("left", "center", "right")


@dataclass
class EditorPreset:
    """Where the editor left off last time."""

    tool: str = "pen"
    rgba: Tuple[float, float, float, float] = (1.0, 0.23, 0.19, 1.0)
    width: float = 3.0
    font_size: float = 22.0
    font_family: str = "Sans"
    redaction_density: float = 0.55
    spotlight_scrim: float = 0.55
    text_align: str = "left"
    head_start: str = "none"
    head_end: str = "arrow"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["rgba"] = list(self.rgba)
        return data


def _clamped(value: Any, low: float, high: float,
             fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number:  # NaN
        return fallback
    return min(max(number, low), high)


def _decode(data: Any) -> EditorPreset:
    preset = EditorPreset()
    if not isinstance(data, dict):
        return preset

    from . import arrows

    if data.get("tool") in TOOLS:
        # Never come back in a modal tool: reopening straight into crop mode
        # would be a surprise rather than a convenience.
        preset.tool = data["tool"] if data["tool"] != "crop" else "pen"

    rgba = data.get("rgba")
    if isinstance(rgba, (list, tuple)) and len(rgba) == 4:
        try:
            preset.rgba = tuple(min(max(float(c), 0.0), 1.0) for c in rgba)
        except (TypeError, ValueError):
            pass

    preset.width = _clamped(data.get("width"), 0.5, 200.0, preset.width)
    preset.font_size = _clamped(data.get("font_size"), 4.0, 400.0,
                                preset.font_size)
    preset.redaction_density = _clamped(data.get("redaction_density"), 0.0, 1.0,
                                        preset.redaction_density)
    preset.spotlight_scrim = _clamped(data.get("spotlight_scrim"), 0.0, 1.0,
                                      preset.spotlight_scrim)

    if isinstance(data.get("font_family"), str) and data["font_family"].strip():
        preset.font_family = data["font_family"]
    if data.get("text_align") in ALIGNMENTS:
        preset.text_align = data["text_align"]
    for key in ("head_start", "head_end"):
        if data.get(key) in arrows.HEADS:
            setattr(preset, key, data[key])
    return preset


def load(path: str = PRESET_PATH) -> EditorPreset:
    """The last session's style, or the defaults when there isn't one."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return _decode(json.load(fh))
    except (OSError, ValueError):
        return EditorPreset()


def save(preset: EditorPreset, path: str = PRESET_PATH) -> bool:
    """Best effort — failing to remember a colour must never surface as an
    error in front of someone who just wanted to save a screenshot."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as fh:
            json.dump(preset.to_dict(), fh, indent=2, ensure_ascii=False)
        os.replace(temporary, path)
        return True
    except (OSError, ValueError, TypeError):
        # ValueError covers a path the OS cannot even be asked about (an
        # embedded NUL); "best effort" has to mean it.
        return False


def from_settings(settings) -> EditorPreset:
    """The configured defaults, as a preset — the starting point on a machine
    that has never opened the editor."""
    preset = EditorPreset()
    preset.width = _clamped(settings.get("pen_width"), 0.5, 200.0, preset.width)
    preset.font_size = _clamped(settings.get("font_size"), 4.0, 400.0,
                                preset.font_size)
    return preset


def field_names() -> Tuple[str, ...]:
    return tuple(f.name for f in fields(EditorPreset))
