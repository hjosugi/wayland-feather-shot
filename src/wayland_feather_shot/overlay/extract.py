"""Reading the selection on the region overlay.

Copy the text in it (OCR) or a QR code or barcode, and propose blur regions
over text that looks sensitive. Everything runs on this machine (tesseract,
zbarimg; see editor/recognize.py) and off the UI thread, since OCR on a big
selection takes seconds. A mixin of overlay.window.OverlayWindow.
"""

from __future__ import annotations

import os
import tempfile
import threading

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from .. import save as save_mod
from ..editor import recognize, sensitive
from ..editor.shapes import Obscure
from ..util.i18n import _, tr


class OverlayExtractMixin:
    """Adds the recognition entries of the "…" menu; _recognizing is True
    while one runs."""

    def _recognition_entries(self):
        """(icon, label, callback) for each recognition the installed tools
        allow; none without tesseract and zbarimg."""
        entries = []
        if recognize.ocr_available():
            entries.append(("wfs-ocr-symbolic", "Copy text (OCR)",
                            lambda: self.extract_text("ocr")))
        if recognize.qr_available():
            entries.append(("wfs-qr-symbolic", "Copy QR / barcode",
                            lambda: self.extract_text("qr")))
        if recognize.ocr_available():
            entries.append(("wfs-redact-auto-symbolic", "Smart redaction…",
                            self.smart_redact))
        return entries

    def _recognize(self, job, done, busy_message):
        """Run job(png_path) on the selection as it looks now, with its
        annotations (a blurred word stays unread), then done(result) back
        on the UI thread. One at a time."""
        if self._recognizing or self.sel is None:
            return
        image = self._export_cropped()
        self._recognizing = True
        self.toast(busy_message, 30.0)

        def work():
            fd, path = tempfile.mkstemp(prefix="wfs-ocr-", suffix=".png")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(save_mod.pixbuf_to_png_bytes(image, fast=True))
                result, error = job(path), None
            except Exception as exc:  # the tool failed, timed out, or worse
                result, error = None, exc
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            GLib.idle_add(finish, result, error)

        def finish(result, error):
            self._recognizing = False
            if error is not None:
                self.toast(tr("Recognition failed: {error}", error=error))
            else:
                done(result)
            return False

        threading.Thread(target=work, daemon=True).start()

    def extract_text(self, kind):
        """Copy the selection's text ("ocr") or QR code ("qr")."""
        def done(text):
            if not text:
                self.toast(_("Nothing recognized."))
                return
            save_mod.copy_text(text)
            self.toast(_("Recognized text copied to clipboard."))

        self._recognize(recognize.run_ocr if kind == "ocr"
                        else recognize.run_qr,
                        done, _("Reading the selection…"))

    def smart_redact(self):
        """Propose blur regions over text that looks sensitive.

        Never applied silently: they arrive as one undo step, picked with
        the hand so they can be moved together, and a run that finds
        nothing says so plainly; a false negative must not read as "this
        image is clean".
        """
        if self.sel is None:
            return
        x0, y0, w, h = self.sel

        def done(rows):
            words = [sensitive.Word(*row) for row in rows]
            regions = sensitive.regions_from_words(words, (float(w), float(h)))
            density = max(self.redaction_density, 0.7)
            shapes = []
            for region in regions:
                rx, ry, rw, rh = region.rect
                if rw > 0 and rh > 0:
                    shapes.append(Obscure((x0 + rx * w, y0 + ry * h,
                                           rw * w, rh * h), density))
            if not shapes:
                self.toast(_("Nothing recognised as sensitive. Check the "
                             "image yourself before sharing it."), 6.0)
                return
            self._push_history()
            self.shapes.extend(shapes)
            self.select_tool("hand")
            self._picked = {shape.sid for shape in shapes}
            self._redraw()
            self.toast(tr("Proposed {count} redactions — adjust them, or "
                          "Ctrl+Z to drop them.", count=len(shapes)), 6.0)

        self._recognize(recognize.run_ocr_words, done,
                        _("Scanning for sensitive text…"))
