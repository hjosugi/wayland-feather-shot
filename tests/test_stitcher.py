"""Unit tests for the scroll stitcher (pure-Python path, no GTK needed).

Run:  python3 tests/test_stitcher.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.scrollcap.stitcher import (  # noqa: E402
    Frame, stitch, frame_signature, signature_diff, detect_static_margins,
    _match, _score_shift, _all_signatures,
)

W, H = 96, 120


def make_document(doc_h: int) -> bytearray:
    """A tall synthetic RGBA document with per-row unique-ish content."""
    buf = bytearray(W * doc_h * 4)
    for y in range(doc_h):
        for x in range(W):
            o = (y * W + x) * 4
            buf[o + 0] = (y * 7 + x * 3) % 256
            buf[o + 1] = (y * 13 + x) % 256
            buf[o + 2] = (y * 3 + x * 5) % 256
            buf[o + 3] = 255
    return buf


def viewport(doc: bytearray, doc_h: int, scroll: int,
             header: bytes = b"", footer: bytes = b"") -> Frame:
    """Extract a WxH viewport at *scroll*, optionally overlaying a fixed
    header/footer band (simulating sticky toolbars)."""
    scroll = max(0, min(scroll, doc_h - H))
    rows = bytearray()
    for y in range(H):
        o = ((scroll + y) * W) * 4
        rows += doc[o : o + W * 4]
    if header:
        rows[0 : len(header)] = header
    if footer:
        rows[len(rows) - len(footer) :] = footer
    return Frame(data=bytes(rows), width=W, height=H, stride=W * 4)


class StitchTest(unittest.TestCase):
    def test_basic_scroll(self):
        doc_h = 500
        doc = make_document(doc_h)
        frames = [viewport(doc, doc_h, s) for s in (0, 70, 140, 210, 280, 350, 380)]
        result = stitch(frames, top_margin=0, bottom_margin=0)
        self.assertIsNotNone(result)
        self.assertEqual(result.width, W)
        # 0..380+120 = 500 rows of unique content expected.
        self.assertAlmostEqual(result.height, doc_h, delta=3)
        self.assertEqual(result.frames_dropped, 0)
        # Content check: stitched row 300 equals document row 300.
        row = result.data[300 * W * 4 : 300 * W * 4 + 12]
        expect = doc[300 * W * 4 : 300 * W * 4 + 12]
        self.assertEqual(bytes(row), bytes(expect))

    def test_duplicate_frames_add_nothing(self):
        doc_h = 400
        doc = make_document(doc_h)
        frames = [viewport(doc, doc_h, 0)] * 3 + [viewport(doc, doc_h, 90)] * 2
        result = stitch(frames, top_margin=0, bottom_margin=0)
        self.assertAlmostEqual(result.height, 90 + H, delta=3)

    def test_static_margin_detection(self):
        doc_h = 600
        doc = make_document(doc_h)
        header = bytes([200, 200, 200, 255]) * (W * 20)   # 20 fixed rows
        footer = bytes([30, 30, 30, 255]) * (W * 16)      # 16 fixed rows
        frames = [viewport(doc, doc_h, s, header, footer)
                  for s in (0, 60, 120, 180, 240)]
        top, bottom = detect_static_margins(frames)
        self.assertGreaterEqual(top, 12)
        self.assertLessEqual(top, 28)
        self.assertGreaterEqual(bottom, 10)
        self.assertLessEqual(bottom, 24)
        result = stitch(frames)  # auto margins
        self.assertIsNotNone(result)
        self.assertGreater(result.height, H)

    def test_unrelated_frame_dropped(self):
        doc_h = 400
        doc = make_document(doc_h)
        noise = Frame(data=bytes(W * H * 4), width=W, height=H, stride=W * 4)
        frames = [viewport(doc, doc_h, 0), noise, viewport(doc, doc_h, 60)]
        result = stitch(frames, top_margin=0, bottom_margin=0)
        self.assertEqual(result.frames_dropped, 1)
        self.assertAlmostEqual(result.height, 60 + H, delta=3)

    def test_alpha_forced_opaque(self):
        doc_h = 300
        doc = make_document(doc_h)
        raw = bytearray(viewport(doc, doc_h, 0).data)
        raw[3::4] = b"\x00" * (len(raw) // 4)  # RGBx-style undefined alpha
        frames = [Frame(bytes(raw), W, H, W * 4), viewport(doc, doc_h, 50)]
        result = stitch(frames, top_margin=0, bottom_margin=0)
        self.assertTrue(all(b == 255 for b in result.data[3::4]))

    def test_coarse_to_fine_finds_exact_shift(self):
        # A tall frame + large scroll step is where coarse-to-fine matters.
        # make_document() is byte-periodic (period 256), so a 900-row scroll
        # would alias with 900-3*256; build a document whose row signature is
        # unique over the whole height instead (coarse band + fine index).
        doc_h = 4000
        tall_h = 1400
        doc = bytearray(W * doc_h * 4)
        for y in range(doc_h):
            coarse = (y // 16) & 0xFF   # unique block index over 0..4095
            fine = y & 0xFF
            for x in range(W):
                v = coarse if x < W // 2 else fine
                o = (y * W + x) * 4
                doc[o + 0] = v
                doc[o + 1] = v
                doc[o + 2] = v
                doc[o + 3] = 255

        def big_viewport(scroll):
            scroll = max(0, min(scroll, doc_h - tall_h))
            rows = bytearray()
            for y in range(tall_h):
                o = ((scroll + y) * W) * 4
                rows += doc[o:o + W * 4]
            return Frame(bytes(rows), W, tall_h, W * 4)

        prev, cur = big_viewport(0), big_viewport(900)
        m = _match(_all_signatures(prev), _all_signatures(cur), 0, tall_h)
        self.assertIsNotNone(m)
        shift, score = m
        self.assertEqual(shift, 900)
        self.assertLess(score, 1.0)

    def test_coarse_pass_matches_bruteforce(self):
        # Guard: the coarse-to-fine winner equals an exhaustive scan's winner.
        doc_h = 800
        doc = make_document(doc_h)
        prev, cur = viewport(doc, doc_h, 0), viewport(doc, doc_h, 55)
        ps, cs = _all_signatures(prev), _all_signatures(cur)
        usable_h, top = H, 0
        band = usable_h - top
        max_s = band - max(10, band // 8)
        brute = min(range(0, max_s + 1),
                    key=lambda s: _score_shift(ps, cs, top, usable_h, s))
        m = _match(ps, cs, top, usable_h)
        self.assertIsNotNone(m)
        self.assertEqual(m[0], brute)
        self.assertEqual(m[0], 55)

    def test_overshoot_frame_dropped_not_duplicated(self):
        # User scrolled 0->60->120, the page rubber-banded back to 90, then
        # settled at 150. The 90 frame must be dropped (backwards), not append
        # a duplicated strip.
        doc_h = 600
        doc = make_document(doc_h)
        frames = [viewport(doc, doc_h, s) for s in (0, 60, 120, 90, 150)]
        result = stitch(frames, top_margin=0, bottom_margin=0)
        self.assertAlmostEqual(result.height, 150 + H, delta=3)
        self.assertEqual(result.frames_dropped, 1)
        dropped = result.warnings
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0].index, 3)  # the 90-scroll frame
        self.assertIn("back", dropped[0].reason)

    def test_horizontal_shift_dropped_with_reason(self):
        doc_h = 400
        doc = make_document(doc_h)
        base = viewport(doc, doc_h, 60)

        def roll_columns(frame, dx):
            rows = bytearray()
            for y in range(frame.height):
                row = bytearray(frame.row(y))
                shift = dx * 4
                rows += row[shift:] + row[:shift]
            return Frame(bytes(rows), frame.width, frame.height, frame.width * 4)

        frames = [viewport(doc, doc_h, 0), roll_columns(base, 20)]
        result = stitch(frames, top_margin=0, bottom_margin=0)
        self.assertEqual(result.frames_dropped, 1)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("horizontal", result.warnings[0].reason)

    def test_notes_cover_every_frame(self):
        doc_h = 400
        doc = make_document(doc_h)
        frames = [viewport(doc, doc_h, 0), viewport(doc, doc_h, 0),
                  viewport(doc, doc_h, 60)]
        result = stitch(frames, top_margin=0, bottom_margin=0)
        # one note per non-base frame
        self.assertEqual(len(result.notes), 2)
        actions = [n.action for n in result.notes]
        self.assertEqual(actions, ["duplicate", "kept"])

    def test_signatures(self):
        doc_h = 300
        doc = make_document(doc_h)
        f1 = viewport(doc, doc_h, 0)
        f2 = viewport(doc, doc_h, 0)
        f3 = viewport(doc, doc_h, 120)
        s1, s2, s3 = (frame_signature(f) for f in (f1, f2, f3))
        self.assertEqual(signature_diff(s1, s2), 0.0)
        self.assertGreater(signature_diff(s1, s3), 3.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
