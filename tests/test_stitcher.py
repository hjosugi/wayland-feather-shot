"""Unit tests for the scroll stitcher (pure-Python path, no GTK needed).

Run:  python3 tests/test_stitcher.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.scrollcap.stitcher import (  # noqa: E402
    Frame, stitch, frame_signature, signature_diff, detect_static_margins,
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
