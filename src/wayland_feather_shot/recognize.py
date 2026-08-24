"""Local-only OCR (tesseract) and QR decoding (zbarimg) of an image file.

Both shell out to external CLIs that run entirely on the machine — no network.
The command builders and availability checks are gi-free and unit-tested; the
`run_*` helpers invoke the tools.
"""

from __future__ import annotations

import shutil
import subprocess


def tesseract_command(image_path: str):
    """OCR command printing recognized text to stdout (default language)."""
    return ["tesseract", image_path, "stdout"]


def zbar_command(image_path: str):
    """QR/barcode command printing raw decoded contents to stdout."""
    return ["zbarimg", "-q", "--raw", image_path]


def tesseract_tsv_command(image_path: str):
    """OCR command printing one row per recognised word, with its box.

    ``--psm 11`` is sparse text: a screenshot is scattered labels and fields,
    not a page of prose, and the page-layout modes mis-group it badly.
    """
    return ["tesseract", image_path, "stdout", "--psm", "11", "tsv"]


def parse_tsv_words(output: str):
    """Word boxes from tesseract's TSV, as plain tuples.

    Returns ``(text, x, y, w, h, (block, paragraph, line))``.  Rows without a
    word, and rows tesseract itself has no confidence in, are dropped — a box
    around noise is worse than no box, because it trains people to ignore the
    suggestions.
    """
    words = []
    lines = output.splitlines()
    if not lines:
        return words
    header = lines[0].split("\t")
    try:
        index = {name: header.index(name) for name in
                 ("level", "block_num", "par_num", "line_num", "left", "top",
                  "width", "height", "conf", "text")}
    except ValueError:
        return words

    for row in lines[1:]:
        cells = row.split("\t")
        if len(cells) <= index["text"]:
            continue
        text = cells[index["text"]].strip()
        if not text:
            continue
        try:
            if int(cells[index["level"]]) != 5:      # 5 is a word
                continue
            confidence = float(cells[index["conf"]])
            box = tuple(float(cells[index[name]])
                        for name in ("left", "top", "width", "height"))
            group = tuple(int(cells[index[name]])
                          for name in ("block_num", "par_num", "line_num"))
        except (ValueError, IndexError):
            continue
        if confidence < 0 or box[2] <= 0 or box[3] <= 0:
            continue
        words.append((text,) + box + (group,))
    return words


def run_ocr_words(image_path: str, timeout: float = 60.0):
    """Recognised words with their boxes, for smart redaction."""
    proc = subprocess.run(tesseract_tsv_command(image_path),
                          capture_output=True, text=True, timeout=timeout)
    return parse_tsv_words(proc.stdout)


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def qr_available() -> bool:
    return shutil.which("zbarimg") is not None


def run_ocr(image_path: str, timeout: float = 30.0) -> str:
    proc = subprocess.run(tesseract_command(image_path), capture_output=True,
                          text=True, timeout=timeout)
    return proc.stdout.strip()


def run_qr(image_path: str, timeout: float = 15.0) -> str:
    # zbarimg exits non-zero (4) when nothing is found; that's not an error.
    proc = subprocess.run(zbar_command(image_path), capture_output=True,
                          text=True, timeout=timeout)
    return proc.stdout.strip()
