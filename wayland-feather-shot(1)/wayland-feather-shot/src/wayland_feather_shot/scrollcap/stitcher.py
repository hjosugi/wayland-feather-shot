"""Vertical scroll-stitching engine.

The algorithm is intentionally GUI-free and pure-Python with an optional numpy
fast path.  It aligns the bottom strip of the previous frame with the top strip
of the next frame, then appends only the newly revealed rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from PIL import Image, ImageChops, ImageStat

try:  # pragma: no cover - optional fast path
    import numpy as np
except Exception:  # pragma: no cover
    np = None


@dataclass(frozen=True, slots=True)
class MatchResult:
    overlap: int
    score: float
    accepted: bool


@dataclass(slots=True)
class StitchOptions:
    min_overlap: int = 40
    max_overlap_ratio: float = 0.90
    search_step: int = 2
    sample_stride: int = 3
    accept_score: float = 10.0
    edge_crop_ratio: float = 0.08


class ScrollStitcher:
    def __init__(self, options: StitchOptions | None = None):
        self.options = options or StitchOptions()

    def stitch(self, frames: Sequence[Image.Image]) -> tuple[Image.Image, list[MatchResult]]:
        if not frames:
            raise ValueError("at least one frame is required")
        normalized = [self._normalize(frame) for frame in frames]
        canvas = normalized[0]
        matches: list[MatchResult] = []
        for frame in normalized[1:]:
            match = self.find_overlap(canvas, frame)
            matches.append(match)
            append_from = match.overlap if match.accepted else 0
            if append_from >= frame.height:
                continue
            tail = frame.crop((0, append_from, frame.width, frame.height))
            new_canvas = Image.new("RGBA", (canvas.width, canvas.height + tail.height))
            new_canvas.paste(canvas, (0, 0))
            new_canvas.paste(tail, (0, canvas.height))
            canvas = new_canvas
        return canvas, matches

    def find_overlap(self, prev: Image.Image, nxt: Image.Image) -> MatchResult:
        prev = self._normalize(prev)
        nxt = self._normalize(nxt)
        if prev.width != nxt.width:
            nxt = nxt.resize((prev.width, int(nxt.height * prev.width / nxt.width)))
        max_overlap = max(self.options.min_overlap, int(min(prev.height, nxt.height) * self.options.max_overlap_ratio))
        max_overlap = min(max_overlap, prev.height, nxt.height)
        min_overlap = min(self.options.min_overlap, max_overlap)
        best_overlap = min_overlap
        best_score = float("inf")

        for overlap in range(min_overlap, max_overlap + 1, max(1, self.options.search_step)):
            score = self._strip_score(prev, nxt, overlap)
            if score < best_score:
                best_score = score
                best_overlap = overlap

        accepted = best_score <= self.options.accept_score
        return MatchResult(overlap=best_overlap, score=best_score, accepted=accepted)

    def _normalize(self, image: Image.Image) -> Image.Image:
        return image.convert("RGBA")

    def _strip_score(self, prev: Image.Image, nxt: Image.Image, overlap: int) -> float:
        margin = int(prev.width * self.options.edge_crop_ratio)
        box_prev = (margin, prev.height - overlap, prev.width - margin, prev.height)
        box_next = (margin, 0, nxt.width - margin, overlap)
        a = prev.crop(box_prev)
        b = nxt.crop(box_next)
        stride = max(1, self.options.sample_stride)
        if stride > 1:
            a = a.resize((max(1, a.width // stride), max(1, a.height // stride)))
            b = b.resize((max(1, b.width // stride), max(1, b.height // stride)))
        if np is not None:  # pragma: no cover - optional fast path
            aa = np.asarray(a, dtype=np.int16)
            bb = np.asarray(b, dtype=np.int16)
            return float(np.mean(np.abs(aa - bb)))
        diff = ImageChops.difference(a, b)
        stat = ImageStat.Stat(diff)
        return float(sum(stat.mean[:3]) / 3.0)


def stitch_images(frames: Iterable[Image.Image], options: StitchOptions | None = None) -> tuple[Image.Image, list[MatchResult]]:
    return ScrollStitcher(options).stitch(list(frames))
