"""The overlay reads its selection: OCR and QR text to the clipboard, and
proposed blur regions over text that looks sensitive. The tools are mocked.

Needs a GTK display; skips otherwise.
Run:  python3 tests/test_overlay_extract.py
"""

import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import gi  # noqa: E402
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402
    HAVE_GTK_DISPLAY = Gdk.Display.get_default() is not None
except (ImportError, ValueError):
    HAVE_GTK_DISPLAY = False
if HAVE_GTK_DISPLAY:
    from wayland_feather_shot.editor import recognize  # noqa: E402
    from wayland_feather_shot.i18n import _  # noqa: E402
    from wayland_feather_shot.overlay.window import OverlayWindow  # noqa: E402
    from wayland_feather_shot.settings import Settings  # noqa: E402


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayExtractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.ExtractTest")
        cls.app.register(None)

    def make(self, ocr=True, qr=True):
        with patch.object(recognize, "ocr_available", return_value=ocr), \
                patch.object(recognize, "qr_available", return_value=qr):
            pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8,
                                          400, 300)
            pixbuf.fill(0xffffffff)
            window = OverlayWindow(self.app, pixbuf, Settings())
        self.addCleanup(window.destroy)
        window.area.allocate(400, 300, -1, None)
        window._mon_rects = [(0, 0, 400, 300)]
        window.sel = (100, 50, 200, 100)
        window._selection_made()
        return window

    @staticmethod
    def menu_labels(window):
        more = window._action_bar.get_last_child().get_prev_sibling()
        labels = []
        child = more.get_popover().get_child().get_first_child()
        while child is not None:
            if isinstance(child, Gtk.Button):
                labels.append(child.get_child().get_last_child().get_label())
            child = child.get_next_sibling()
        return labels

    @staticmethod
    def wait(window):
        context = GLib.MainContext.default()
        deadline = time.monotonic() + 5
        while window._recognizing and time.monotonic() < deadline:
            context.iteration(False)
            time.sleep(0.01)
        while context.pending():
            context.iteration(False)

    def test_the_menu_offers_what_the_installed_tools_can_do(self):
        ocr, qr = _("Copy text (OCR)"), _("Copy QR / barcode")
        redact = _("Smart redaction…")
        labels = self.menu_labels(self.make(ocr=True, qr=True))
        for label in (ocr, qr, redact):
            self.assertIn(label, labels)
        labels = self.menu_labels(self.make(ocr=False, qr=True))
        self.assertIn(qr, labels)
        self.assertNotIn(ocr, labels)
        self.assertNotIn(redact, labels)
        labels = self.menu_labels(self.make(ocr=False, qr=False))
        self.assertNotIn(qr, labels)

    def test_ocr_copies_the_text_of_the_selection(self):
        window = self.make()
        seen = {}

        def run_ocr(path):
            from gi.repository import GdkPixbuf as P
            image = P.Pixbuf.new_from_file(path)
            seen["size"] = (image.get_width(), image.get_height())
            return "hello"

        with patch.object(recognize, "run_ocr", side_effect=run_ocr), \
                patch("wayland_feather_shot.save.copy_text") as copy:
            window.extract_text("ocr")
            self.wait(window)
        self.assertEqual(seen["size"], (200, 100))     # the selection only
        copy.assert_called_once_with("hello")

    def test_nothing_found_copies_nothing(self):
        window = self.make()
        with patch.object(recognize, "run_qr", return_value=""), \
                patch("wayland_feather_shot.save.copy_text") as copy:
            window.extract_text("qr")
            self.wait(window)
        copy.assert_not_called()

    def test_a_failing_tool_is_reported_not_raised(self):
        window = self.make()
        with patch.object(recognize, "run_ocr",
                          side_effect=OSError("no tesseract")):
            window.extract_text("ocr")
            self.wait(window)
        self.assertIn("no tesseract", window._toast.get_text())
        self.assertFalse(window._recognizing)

    def test_smart_redaction_proposes_picked_blurs_in_one_undo_step(self):
        window = self.make()
        # An e-mail address at (20, 30) inside the selection's own image.
        rows = [("mail:", 5.0, 30.0, 12.0, 10.0, (1, 1, 1)),
                ("someone@example.com", 20.0, 30.0, 80.0, 10.0, (1, 1, 1))]
        with patch.object(recognize, "run_ocr_words", return_value=rows):
            window.smart_redact()
            self.wait(window)
        (blur,) = window.shapes
        self.assertEqual(blur.kind, "obscure")
        box = blur.page_bounds
        # Placed over the word, shifted by the selection's corner.
        self.assertLessEqual(box.x, 120)
        self.assertGreaterEqual(box.x + box.w, 200)
        self.assertLessEqual(box.y, 80)
        self.assertEqual(window.tool, "hand")
        self.assertEqual(window._picked, {blur.sid})
        window.undo()
        self.assertEqual(window.shapes, [])

    def test_smart_redaction_says_so_when_it_finds_nothing(self):
        window = self.make()
        with patch.object(recognize, "run_ocr_words",
                          return_value=[("hello", 5.0, 5.0, 30.0, 10.0,
                                         (1, 1, 1))]):
            window.smart_redact()
            self.wait(window)
        self.assertEqual(window.shapes, [])
        self.assertEqual(window._toast.get_text(), _(
            "Nothing recognised as sensitive. Check the image yourself "
            "before sharing it."))


if __name__ == "__main__":
    unittest.main()
