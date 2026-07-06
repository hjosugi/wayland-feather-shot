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
