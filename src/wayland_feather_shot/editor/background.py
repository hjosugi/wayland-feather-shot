"""The stage a screenshot sits on: padding, fill, shadow, border, watermark.

Pure Python — no GTK — so the layout arithmetic is unit-testable.  Drawing is
in :mod:`.render`.

Turning a screenshot into something presentable is otherwise a trip through
another tool, and it is entirely local compositing work: a padded card on a
gradient with a soft shadow under it.  Everything here is expressed as a
**fraction** of the screenshot rather than in pixels, so one setting looks the
same on a 1080p capture and a 4K one, and a saved document reopens looking
identical whatever it was captured on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import List, Optional, Sequence, Tuple

Size = Tuple[float, float]
Rect = Tuple[float, float, float, float]
RGBA = Tuple[float, float, float, float]

FILLS = ("none", "solid", "gradient", "image")
ASPECTS = ("auto", "1:1", "4:3", "3:2", "16:9", "9:16")
ALIGNMENTS = ("top-left", "top", "top-right",
              "left", "center", "right",
              "bottom-left", "bottom", "bottom-right")
SHADOW_STYLES = ("soft", "long", "glow", "crisp")

ASPECT_RATIOS = {
    "1:1": 1.0,
    "4:3": 4 / 3,
    "3:2": 3 / 2,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
}

#: A few gradients that read well behind a screenshot.
GRADIENT_PRESETS = {
    "sunset": ((0.98, 0.42, 0.32, 1.0), (0.61, 0.15, 0.69, 1.0)),
    "ocean": ((0.16, 0.50, 0.95, 1.0), (0.05, 0.75, 0.72, 1.0)),
    "dusk": ((0.18, 0.20, 0.35, 1.0), (0.45, 0.24, 0.52, 1.0)),
    "mint": ((0.55, 0.90, 0.72, 1.0), (0.20, 0.62, 0.86, 1.0)),
    "ash": ((0.92, 0.92, 0.94, 1.0), (0.72, 0.74, 0.79, 1.0)),
}


@dataclass(frozen=True)
class ShadowLayer:
    """A resolved drop shadow, in pixels."""

    offset_y: float
    radius: float
    alpha: float


@dataclass(frozen=True)
class Watermark:
    enabled: bool = False
    text: str = ""
    #: Type size as a fraction of the canvas's shorter edge.
    size: float = 0.035
    opacity: float = 0.35
    rotation_degrees: float = -30.0
    #: 0 places a single mark in the corner; higher tiles it that many times
    #: across the canvas.
    density: float = 0.0

    @property
    def visible(self) -> bool:
        return self.enabled and bool(self.text.strip()) and self.opacity > 0.001


@dataclass(frozen=True)
class Border:
    enabled: bool = False
    color: RGBA = (1.0, 1.0, 1.0, 1.0)
    #: Thickness as a fraction of the screenshot's shorter edge.
    thickness: float = 0.012
    opacity: float = 1.0

    @property
    def visible(self) -> bool:
        return self.enabled and self.thickness > 0.0001 and self.opacity > 0.001

    def pixels(self, content: Size) -> float:
        if not self.visible:
            return 0.0
        return max(0.0, self.thickness) * min(content)


@dataclass(frozen=True)
class BackgroundSettings:
    fill: str = "none"
    color: RGBA = (0.11, 0.12, 0.16, 1.0)
    gradient: str = "dusk"
    image_path: Optional[str] = None
    #: Padding as a fraction of the screenshot's longer edge.
    padding: float = 0.08
    #: Corner rounding as a fraction of its shorter edge.
    corner_radius: float = 0.018
    shadow: float = 0.36
    shadow_style: str = "soft"
    aspect: str = "auto"
    alignment: str = "center"
    border: Border = field(default_factory=Border)
    watermark: Watermark = field(default_factory=Watermark)

    @property
    def enabled(self) -> bool:
        """Whether there is a stage to draw at all."""
        return (self.fill != "none" or self.border.visible
                or self.watermark.visible)

    @property
    def has_shadow(self) -> bool:
        return self.fill != "none" and self.shadow > 0.001


def gradient_colors(name: str) -> Tuple[RGBA, RGBA]:
    return GRADIENT_PRESETS.get(name, GRADIENT_PRESETS["dusk"])


def shadow_layer(strength: float, reference_edge: float,
                 style: str = "soft") -> Optional[ShadowLayer]:
    """Resolve the drop shadow.

    The slider mostly grows the *radius* and lets opacity saturate early —
    which is what keeps a large shadow from turning into a black smear rather
    than a soft one.  Ported from the reference's curve.
    """
    strength = min(max(strength, 0.0), 1.0)
    if strength <= 0 or reference_edge <= 0:
        return None

    radius_scale, y_scale, opacity_scale = {
        "soft": (1.0, 0.30, 1.0),
        "long": (1.2, 0.90, 0.85),
        "glow": (1.6, 0.0, 0.7),
        "crisp": (0.8, 0.20, 1.1),
    }.get(style, (1.0, 0.30, 1.0))

    radius = reference_edge * 0.17 * strength * radius_scale
    alpha = min(0.5, min(0.35, 0.08 + strength * 1.35) * opacity_scale)
    return ShadowLayer(offset_y=radius * y_scale, radius=radius, alpha=alpha)


@dataclass(frozen=True)
class Layout:
    """Where everything lands, in canvas pixels."""

    canvas: Size
    #: The screenshot's rect inside the canvas.
    card: Rect
    corner_radius: float
    border_width: float

    @property
    def card_center(self) -> Tuple[float, float]:
        return (self.card[0] + self.card[2] / 2, self.card[1] + self.card[3] / 2)


def _align_offsets(alignment: str, free_x: float,
                   free_y: float) -> Tuple[float, float]:
    horizontal = {"left": 0.0, "right": 1.0}.get(
        alignment.split("-")[-1] if "-" in alignment else alignment, 0.5)
    if alignment in ("top", "bottom", "center"):
        horizontal = 0.5
    vertical = 0.5
    if alignment.startswith("top"):
        vertical = 0.0
    elif alignment.startswith("bottom"):
        vertical = 1.0
    return (free_x * horizontal, free_y * vertical)


def layout(content: Size, settings: BackgroundSettings) -> Layout:
    """Where the screenshot sits on its stage, in canvas pixels.

    With no stage the canvas *is* the screenshot, so every downstream drawing
    path can treat the two the same way instead of branching.
    """
    width, height = max(content[0], 1.0), max(content[1], 1.0)
    border = settings.border.pixels((width, height))
    radius = max(0.0, settings.corner_radius) * min(width, height)

    if not settings.enabled:
        return Layout(canvas=(width, height), card=(0.0, 0.0, width, height),
                      corner_radius=0.0, border_width=0.0)

    pad = max(0.0, settings.padding) * max(width, height)
    card_w = width + border * 2
    card_h = height + border * 2
    canvas_w = card_w + pad * 2
    canvas_h = card_h + pad * 2

    ratio = ASPECT_RATIOS.get(settings.aspect)
    if ratio:
        # Grow the short side to reach the ratio; never crop the card to fit.
        if canvas_w / canvas_h < ratio:
            canvas_w = canvas_h * ratio
        else:
            canvas_h = canvas_w / ratio

    offset_x, offset_y = _align_offsets(settings.alignment,
                                        canvas_w - card_w, canvas_h - card_h)
    return Layout(
        canvas=(canvas_w, canvas_h),
        card=(offset_x + border, offset_y + border, width, height),
        corner_radius=radius,
        border_width=border,
    )


def watermark_positions(canvas: Size, settings: Watermark) -> List[Tuple[float, float]]:
    """Where to stamp the watermark, in canvas pixels.

    Density 0 is a single mark in the bottom-right corner — the usual "this is
    mine" case.  Above that it tiles, for the "do not circulate" case.
    """
    width, height = canvas
    if not settings.visible or width <= 0 or height <= 0:
        return []
    if settings.density < 0.5:
        margin = min(width, height) * 0.04
        return [(width - margin, height - margin)]

    columns = max(1, int(round(settings.density)))
    step_x = width / columns
    rows = max(1, int(round(height / step_x))) if step_x > 0 else 1
    step_y = height / rows
    return [(step_x * (column + 0.5), step_y * (row + 0.5))
            for row in range(rows) for column in range(columns)]


def rounded_rect_path(rect: Rect, radius: float) -> List[Tuple[str, tuple]]:
    """The card outline as drawing instructions, so the shape is defined once.

    Returned as data rather than drawn, to keep this module free of cairo:
    the renderer replays it, and the tests can check the geometry.
    """
    x, y, w, h = rect
    r = max(0.0, min(radius, w / 2, h / 2))
    if r <= 0:
        return [("rect", (x, y, w, h))]
    return [
        ("move", (x + r, y)),
        ("line", (x + w - r, y)),
        ("arc", (x + w - r, y + r, r, -math.pi / 2, 0.0)),
        ("line", (x + w, y + h - r)),
        ("arc", (x + w - r, y + h - r, r, 0.0, math.pi / 2)),
        ("line", (x + r, y + h)),
        ("arc", (x + r, y + h - r, r, math.pi / 2, math.pi)),
        ("line", (x, y + r)),
        ("arc", (x + r, y + r, r, math.pi, 1.5 * math.pi)),
        ("close", ()),
    ]
