"""Vertical scroll-stitching engine.

Pure-Python implementation with an optional numpy fast path.  This module is
deliberately GUI-free so it can be unit-tested without GTK.

Frames are raw RGBA/RGBx byte buffers described by :class:`Frame`.  The
stitcher aligns consecutive frames by matching a horizontal strip taken from
the bottom of the previous frame inside the next frame, then appends only the
newly revealed rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

try:  # optional acceleration
    import numpy as _np
except ImportError:  # pragma: no cover - depends on environment
    _np = None

# Number of gray samples taken per row for the pure-Python signature path.
ROW_SAMPLES = 24
# Rows compared per candidate shift (sampled evenly over the overlap).
OVERLAP_SAMPLES = 24
# Mean-absolute-difference threshold (0..255) above which a match is rejected.
MATCH_THRESHOLD = 9.0


@dataclass
class Frame:
    """One captured frame of raw pixel data (4 bytes per pixel)."""

    data: bytes
    width: int
    height: int
    stride: int  # bytes per row (>= width * 4)

    def row(self, y: int) -> bytes:
        off = y * self.stride
        return self.data[off : off + self.width * 4]


@dataclass
class StitchResult:
    data: bytearray  # tightly packed RGBA, alpha forced opaque
    width: int
    height: int
    frames_used: int
    frames_dropped: int


def _row_signature(frame: Frame, y: int) -> List[int]:
    """Gray value sampled at ROW_SAMPLES evenly spaced columns of row *y*."""
    sig = []
    base = y * frame.stride
    step = max(1, frame.width // ROW_SAMPLES)
    data = frame.data
    for i in range(ROW_SAMPLES):
        x = min(i * step, frame.width - 1)
        o = base + x * 4
        sig.append((data[o] + data[o + 1] + data[o + 2]) // 3)
    return sig


def frame_signature(frame: Frame, rows: int = 36) -> List[List[int]]:
    """Coarse whole-frame signature used by the frame selector (motion/still
    detection). Returns *rows* row-signatures evenly spread over the frame."""
    step = max(1, frame.height // rows)
    return [_row_signature(frame, min(y * step, frame.height - 1)) for y in range(rows)]


def signature_diff(a: Sequence[Sequence[int]], b: Sequence[Sequence[int]]) -> float:
    """Mean absolute difference between two frame signatures (0..255)."""
    total = 0
    n = 0
    for ra, rb in zip(a, b):
        for va, vb in zip(ra, rb):
            total += abs(va - vb)
            n += 1
    return total / max(1, n)


def _gray_matrix(frame: Frame):
    """numpy (H, ROW_SAMPLES) gray matrix of sampled columns."""
    arr = _np.frombuffer(frame.data, dtype=_np.uint8)
    arr = arr[: frame.height * frame.stride].reshape(frame.height, frame.stride)
    step = max(1, frame.width // ROW_SAMPLES)
    cols = [min(i * step, frame.width - 1) * 4 for i in range(ROW_SAMPLES)]
    r = arr[:, [c + 0 for c in cols]].astype(_np.int16)
    g = arr[:, [c + 1 for c in cols]].astype(_np.int16)
    b = arr[:, [c + 2 for c in cols]].astype(_np.int16)
    return (r + g + b) // 3


def _all_signatures(frame: Frame) -> "list":
    if _np is not None:
        return _gray_matrix(frame)
    return [_row_signature(frame, y) for y in range(frame.height)]


def _best_shift(prev_sigs, cur_sigs, top: int, usable_h: int) -> Optional[int]:
    """Find the vertical scroll amount between two frames.

    The content that was at row ``j + s`` of the previous frame appears at
    row ``j`` of the current frame after scrolling down by *s* rows.  We scan
    all shifts and score each by the mean absolute difference over rows
    sampled from the overlapping region ``[top, usable_h - s)``.

    Returns the best shift (0 = identical frames) or None when even the best
    candidate scores worse than MATCH_THRESHOLD (unrelated frames).
    """
    band = usable_h - top
    if band <= 0:
        return None
    min_overlap = max(10, band // 8)
    best_s, best_score = None, None
    for s in range(0, band - min_overlap + 1):
        lo, hi = top, usable_h - s
        n = min(OVERLAP_SAMPLES, hi - lo)
        step = max(1, (hi - lo) // n)
        if _np is not None:
            rows = _np.arange(lo, hi, step)
            score = float(_np.mean(_np.abs(cur_sigs[rows] - prev_sigs[rows + s])))
        else:
            total = 0
            cnt = 0
            for j in range(lo, hi, step):
                ra = cur_sigs[j]
                rb = prev_sigs[j + s]
                for va, vb in zip(ra, rb):
                    total += abs(va - vb)
                    cnt += 1
            score = total / max(1, cnt)
        if best_score is None or score < best_score:
            best_score, best_s = score, s
    if best_score is not None and best_score <= MATCH_THRESHOLD:
        return best_s
    return None


def detect_static_margins(frames: List[Frame], max_frac: float = 0.35) -> tuple:
    """Detect fixed headers/footers (rows identical across all frames), e.g.
    a browser toolbar or a sticky page header.  Returns (top, bottom) row
    counts to exclude, each capped at *max_frac* of the frame height."""
    if len(frames) < 3:
        return (0, 0)
    sigs = [_all_signatures(f) for f in frames]
    h = frames[0].height
    cap = int(h * max_frac)

    def rows_equal(y: int) -> bool:
        first = sigs[0][y]
        for s in sigs[1:]:
            row = s[y]
            if _np is not None:
                if int(_np.max(_np.abs(row - first))) > 4:
                    return False
            else:
                if any(abs(a - b) > 4 for a, b in zip(row, first)):
                    return False
        return True

    top = 0
    while top < cap and rows_equal(top):
        top += 1
    bottom = 0
    while bottom < cap and rows_equal(h - 1 - bottom):
        bottom += 1
    # A margin of a few rows is noise, not a real header/footer.
    if top < 8:
        top = 0
    if bottom < 8:
        bottom = 0
    return (top, bottom)


def _append_rows(out: bytearray, frame: Frame, y0: int, y1: int) -> int:
    """Append rows [y0, y1) of *frame* to *out* as tightly packed RGBA."""
    rowlen = frame.width * 4
    for y in range(y0, y1):
        off = y * frame.stride
        out += frame.data[off : off + rowlen]
    return max(0, y1 - y0)


def stitch(frames: List[Frame], top_margin: int = -1, bottom_margin: int = -1,
           progress=None) -> Optional[StitchResult]:
    """Stitch *frames* (top-to-bottom scroll) into one tall image.

    top_margin / bottom_margin: rows to exclude from every frame (static
    header/footer). Pass -1 to auto-detect.
    """
    frames = [f for f in frames if f.width > 0 and f.height > 0]
    if not frames:
        return None
    width = frames[0].width
    frames = [f for f in frames if f.width == width]

    if top_margin < 0 or bottom_margin < 0:
        auto_top, auto_bottom = detect_static_margins(frames)
        if top_margin < 0:
            top_margin = auto_top
        if bottom_margin < 0:
            bottom_margin = auto_bottom

    first = frames[0]
    usable_h = first.height - bottom_margin
    out = bytearray()
    height = _append_rows(out, first, 0, usable_h)  # keep the header once

    prev = first
    prev_sigs = _all_signatures(prev)
    used, dropped = 1, 0

    for idx, cur in enumerate(frames[1:], start=1):
        if progress:
            progress(idx, len(frames) - 1)
        cur_sigs = _all_signatures(cur)
        s = _best_shift(prev_sigs, cur_sigs, top_margin, usable_h)
        if s is None:
            dropped += 1
            continue
        if s > 0:  # bottom s rows of the current frame are new content
            height += _append_rows(out, cur, usable_h - s, usable_h)
        prev, prev_sigs = cur, cur_sigs
        used += 1

    if bottom_margin > 0:  # re-attach the fixed footer once, at the bottom
        height += _append_rows(out, prev, prev.height - bottom_margin, prev.height)

    # Force alpha opaque (frames may be RGBx with undefined alpha bytes).
    out[3::4] = b"\xff" * (len(out) // 4)
    return StitchResult(data=out, width=width, height=height,
                        frames_used=used, frames_dropped=dropped)
