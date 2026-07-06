"""Tests for the OCR/QR command builders (no GTK, no external tools needed).

Run:  python3 tests/test_recognize.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot import recognize  # noqa: E402


class CommandTests(unittest.TestCase):
    def test_tesseract_command(self):
        self.assertEqual(recognize.tesseract_command("/tmp/a.png"),
                         ["tesseract", "/tmp/a.png", "stdout"])

    def test_zbar_command(self):
        cmd = recognize.zbar_command("/tmp/a.png")
        self.assertEqual(cmd[0], "zbarimg")
        self.assertIn("--raw", cmd)
        self.assertEqual(cmd[-1], "/tmp/a.png")

    def test_availability_returns_bool(self):
        self.assertIsInstance(recognize.ocr_available(), bool)
        self.assertIsInstance(recognize.qr_available(), bool)


if __name__ == "__main__":
    unittest.main(verbosity=2)
