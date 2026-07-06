"""Tests for the pure GIF encoder — LZW round-trips through a decoder here.

Run:  python3 tests/test_gifenc.py
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot import gifenc  # noqa: E402


def lzw_decode(data: bytes, min_code_size: int) -> bytes:
    """Reference GIF LZW decoder, mirroring gifenc.lzw_encode."""
    clear = 1 << min_code_size
    end = clear + 1
    code_size = min_code_size + 1
    acc = 0
    nbits = 0
    pos = 0

    def read():
        nonlocal acc, nbits, pos
        while nbits < code_size:
            if pos >= len(data):
                acc |= 0 << nbits
            else:
                acc |= data[pos] << nbits
            pos += 1
            nbits += 8
        code = acc & ((1 << code_size) - 1)
        acc >>= code_size
        nbits -= code_size
        return code

    def init_table():
        return [[i] for i in range(clear)] + [None, None]

    table = init_table()
    out = []
    prev = None
    while True:
        code = read()
        if code == clear:
            table = init_table()
            code_size = min_code_size + 1
            prev = None
            continue
        if code == end:
            break
        if prev is None:
            entry = list(table[code])
            out += entry
            prev = entry
            continue
        if code < len(table) and table[code] is not None:
            entry = list(table[code])
        elif code == len(table):
            entry = prev + [prev[0]]
        else:
            raise ValueError(f"bad LZW code {code}")
        out += entry
        table.append(prev + [entry[0]])
        prev = entry
        # The decoder assigns codes one step behind the encoder, so it must
        # widen one entry earlier — the GIF LZW off-by-one.
        if len(table) == (1 << code_size) - 1 and code_size < 12:
            code_size += 1
    return bytes(out)


class LzwRoundTripTests(unittest.TestCase):
    def _roundtrip(self, seq, mcs):
        enc = gifenc.lzw_encode(bytes(seq), mcs)
        self.assertEqual(lzw_decode(enc, mcs), bytes(seq))

    def test_simple(self):
        self._roundtrip([1, 2, 3, 1, 2, 3, 1, 2, 3], 8)

    def test_run(self):
        self._roundtrip([5] * 500, 8)

    def test_grows_code_size(self):
        seq = [(i * 7 + (i // 3)) & 0xFF for i in range(3000)]
        self._roundtrip(seq, 8)

    def test_small_min_code_size(self):
        self._roundtrip([0, 1, 2, 3, 3, 2, 1, 0, 1, 1, 2], 2)

    def test_empty(self):
        self._roundtrip([], 8)


class QuantizeTests(unittest.TestCase):
    def test_pure_colors_map_to_palette(self):
        rgb = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255])  # red, green, blue
        idx = gifenc.quantize_rgb(rgb, 3)
        self.assertEqual(len(idx), 3)
        for i in idx:
            r, g, b = gifenc.PALETTE[i]
            self.assertIn(255, (r, g, b))

    def test_black_and_white(self):
        idx = gifenc.quantize_rgb(bytes([0, 0, 0, 255, 255, 255]), 2)
        self.assertEqual(gifenc.PALETTE[idx[0]], (0, 0, 0))
        self.assertEqual(gifenc.PALETTE[idx[1]], (255, 255, 255))


class GifStructureTests(unittest.TestCase):
    def test_animated_gif_structure(self):
        w, h = 2, 2
        frames = [bytes([0, 1, 2, 3]), bytes([3, 2, 1, 0])]
        gif = gifenc.write_gif(frames, w, h, delay_cs=10, loop=True)
        self.assertTrue(gif.startswith(b"GIF89a"))
        self.assertEqual(gif[-1], 0x3B)                 # trailer
        self.assertEqual(struct.unpack("<HH", gif[6:10]), (w, h))
        self.assertIn(b"NETSCAPE2.0", gif)              # loop extension
        self.assertEqual(gif.count(b"\x21\xF9\x04"), 2)  # one GCE per frame


if __name__ == "__main__":
    unittest.main(verbosity=2)
