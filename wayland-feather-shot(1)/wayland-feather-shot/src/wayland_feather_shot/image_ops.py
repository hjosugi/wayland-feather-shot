"""Pure image operations used by the GTK editor and tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, cos, sin, pi
from typing import Iterable, Literal

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ToolName = Literal["pen", "line", "arrow", "rect", "ellipse", "blur", "text", "crop"]
Color = tuple[int, int, int, int]
Point = tuple[float, float]


@dataclass(slots=True)
class DrawOp:
    kind: ToolName
    points: list[Point]
    color: Color = (255, 45, 45, 255)
    width: int = 4
    text: str = ""
    radius: int = 10
    fill: bool = False

    def normalized_rect(self) -> tuple[int, int, int, int]:
        if len(self.points) < 2:
            raise ValueError("rectangle operation needs at least two points")
        (x1, y1), (x2, y2) = self.points[0], self.points[-1]
        left, right = sorted((int(round(x1)), int(round(x2))))
        top, bottom = sorted((int(round(y1)), int(round(y2))))
        return left, top, right, bottom


@dataclass(slots=True)
class CanvasState:
    base: Image.Image
    ops: list[DrawOp] = field(default_factory=list)

    def render(self, include_ops: bool = True) -> Image.Image:
        image = self.base.convert("RGBA").copy()
        if include_ops:
            for op in self.ops:
                apply_op(image, op)
        return image


def _clamp_rect(rect: tuple[int, int, int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    w, h = size
    left, top, right, bottom = rect
    left = max(0, min(left, w))
    right = max(0, min(right, w))
    top = max(0, min(top, h))
    bottom = max(0, min(bottom, h))
    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top
    return left, top, right, bottom


def _draw_arrow_head(draw: ImageDraw.ImageDraw, start: Point, end: Point, color: Color, width: int) -> None:
    angle = atan2(end[1] - start[1], end[0] - start[0])
    size = max(12, width * 4)
    left = (end[0] - size * cos(angle - pi / 6), end[1] - size * sin(angle - pi / 6))
    right = (end[0] - size * cos(angle + pi / 6), end[1] - size * sin(angle + pi / 6))
    draw.polygon([end, left, right], fill=color)


def apply_op(image: Image.Image, op: DrawOp) -> None:
    """Apply one operation in-place."""
    draw = ImageDraw.Draw(image, "RGBA")

    if op.kind == "pen":
        if len(op.points) >= 2:
            draw.line(op.points, fill=op.color, width=op.width, joint="curve")
        elif op.points:
            x, y = op.points[0]
            r = max(1, op.width // 2)
            draw.ellipse((x - r, y - r, x + r, y + r), fill=op.color)
        return

    if op.kind in {"line", "arrow"}:
        if len(op.points) < 2:
            return
        start, end = op.points[0], op.points[-1]
        draw.line([start, end], fill=op.color, width=op.width)
        if op.kind == "arrow":
            _draw_arrow_head(draw, start, end, op.color, op.width)
        return

    if op.kind in {"rect", "ellipse"}:
        if len(op.points) < 2:
            return
        rect = op.normalized_rect()
        if op.kind == "rect":
            draw.rectangle(rect, outline=op.color, width=op.width)
        else:
            draw.ellipse(rect, outline=op.color, width=op.width)
        return

    if op.kind == "blur":
        if len(op.points) < 2:
            return
        rect = _clamp_rect(op.normalized_rect(), image.size)
        if rect[2] <= rect[0] or rect[3] <= rect[1]:
            return
        patch = image.crop(rect).filter(ImageFilter.GaussianBlur(radius=op.radius))
        image.paste(patch, rect)
        draw.rectangle(rect, outline=(255, 255, 255, 180), width=1)
        draw.rectangle((rect[0] + 1, rect[1] + 1, rect[2] - 1, rect[3] - 1), outline=(0, 0, 0, 160), width=1)
        return

    if op.kind == "text":
        if not op.points or not op.text:
            return
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", max(14, op.width * 6))
        except OSError:
            font = ImageFont.load_default()
        draw.text(op.points[0], op.text, fill=op.color, font=font)
        return

    if op.kind == "crop":
        raise ValueError("crop is handled by CanvasState users, not apply_op")

    raise ValueError(f"unknown tool: {op.kind}")


def crop_to_rect(image: Image.Image, rect: tuple[int, int, int, int]) -> Image.Image:
    rect = _clamp_rect(rect, image.size)
    if rect[2] <= rect[0] or rect[3] <= rect[1]:
        return image.copy()
    return image.crop(rect).copy()


def flatten(base: Image.Image, ops: Iterable[DrawOp]) -> Image.Image:
    state = CanvasState(base=base.convert("RGBA"), ops=list(ops))
    return state.render(include_ops=True)
