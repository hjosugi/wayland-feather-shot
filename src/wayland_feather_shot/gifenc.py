"""Minimal pure-Python animated GIF89a encoder (no dependencies).

Used to export a short region recording without pulling in an image library.
Colours are quantized to a fixed 6x6x6 cube (216 colours); frames share one
global colour table.  The GIF LZW compressor is the standard variable-width
encoder.  Both the quantizer and the LZW encoder are unit-tested (the test
round-trips through a decoder).
"""

from __future__ import annotations

import struct
from typing import List


def _build_palette():
    """216-colour 6x6x6 cube, padded to 256 entries."""
    levels = [0, 51, 102, 153, 204, 255]
    pal = []
    for r in levels:
        for g in levels:
            for b in levels:
                pal.append((r, g, b))
    pal += [(0, 0, 0)] * (256 - len(pal))
    return pal


PALETTE = _build_palette()


def _cube_index(r: int, g: int, b: int) -> int:
    ri = (r * 5 + 127) // 255
    gi = (g * 5 + 127) // 255
    bi = (b * 5 + 127) // 255
    return ri * 36 + gi * 6 + bi


def quantize_rgb(rgb: bytes, npixels: int) -> bytes:
    """Map packed RGB bytes (3 per pixel) to palette indices (1 per pixel)."""
    out = bytearray(npixels)
    for i in range(npixels):
        o = i * 3
        out[i] = _cube_index(rgb[o], rgb[o + 1], rgb[o + 2])
    return bytes(out)


class _BitWriter:
    def __init__(self):
        self.bytes = bytearray()
        self._acc = 0
        self._nbits = 0

    def write(self, code: int, width: int):
        self._acc |= (code << self._nbits)
        self._nbits += width
        while self._nbits >= 8:
            self.bytes.append(self._acc & 0xFF)
            self._acc >>= 8
            self._nbits -= 8

    def flush(self):
        if self._nbits > 0:
            self.bytes.append(self._acc & 0xFF)
            self._acc = 0
            self._nbits = 0


def lzw_encode(indices: bytes, min_code_size: int) -> bytes:
    """GIF variable-width LZW. Returns the raw code stream (not sub-blocked)."""
    clear_code = 1 << min_code_size
    end_code = clear_code + 1
    code_size = min_code_size + 1
    writer = _BitWriter()

    table = {(i,): i for i in range(clear_code)}
    next_code = end_code + 1
    writer.write(clear_code, code_size)

    if not indices:
        writer.write(end_code, code_size)
        writer.flush()
        return bytes(writer.bytes)

    prev = (indices[0],)
    for k in indices[1:]:
        cur = prev + (k,)
        if cur in table:
            prev = cur
        else:
            writer.write(table[prev], code_size)
            table[cur] = next_code
            next_code += 1
            if next_code == (1 << code_size) and code_size < 12:
                code_size += 1
            if next_code == 4096:
                writer.write(clear_code, code_size)
                table = {(i,): i for i in range(clear_code)}
                next_code = end_code + 1
                code_size = min_code_size + 1
            prev = (k,)
    writer.write(table[prev], code_size)
    writer.write(end_code, code_size)
    writer.flush()
    return bytes(writer.bytes)


def _sub_blocks(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), 255):
        chunk = data[i:i + 255]
        out.append(len(chunk))
        out += chunk
    out.append(0)  # block terminator
    return bytes(out)


def write_gif(frames: List[bytes], width: int, height: int,
              delay_cs: int = 20, loop: bool = True) -> bytes:
    """Assemble an animated GIF from *frames* (each a palette-index bytes of
    length width*height).  delay_cs is per-frame delay in centiseconds."""
    min_code_size = 8
    out = bytearray()
    out += b"GIF89a"
    out += struct.pack("<HH", width, height)
    # Global colour table: 256 entries, sorted flag off, resolution 8.
    out.append(0xF7)   # global table, 8 bits/pixel, 256 entries
    out.append(0)      # background colour index
    out.append(0)      # pixel aspect ratio
    for (r, g, b) in PALETTE:
        out += bytes((r, g, b))

    if loop:
        out += b"\x21\xFF\x0B" + b"NETSCAPE2.0" + b"\x03\x01" \
               + struct.pack("<H", 0) + b"\x00"

    for frame in frames:
        # Graphic control extension (delay).
        out += b"\x21\xF9\x04\x00" + struct.pack("<H", delay_cs) + b"\x00\x00"
        # Image descriptor.
        out += b"\x2C" + struct.pack("<HHHH", 0, 0, width, height) + b"\x00"
        out.append(min_code_size)
        out += _sub_blocks(lzw_encode(frame, min_code_size))

    out += b"\x3B"  # trailer
    return bytes(out)
