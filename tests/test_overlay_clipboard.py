"""Leaving the overlay after a copy or a save: the overlay goes off the
screen before the slow part, and on GNOME it sets the clipboard itself
instead of making wl-copy map a window for the focus.

Needs a GTK display; skips otherwise.
Run:  python3 tests/test_overlay_clipboard.py
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
    from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402
    HAVE_GTK_DISPLAY = Gdk.Display.get_default() is not None
except (ImportError, ValueError):
    HAVE_GTK_DISPLAY = False
if HAVE_GTK_DISPLAY:
    from wayland_feather_shot import save as save_mod  # noqa: E402
    from wayland_feather_shot.overlay.window import OverlayWindow  # noqa: E402
    from wayland_feather_shot.settings import Settings  # noqa: E402


def run_until(condition, seconds=5.0):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayLeavingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.ClipTest")
        cls.app.register(None)

    def setUp(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8,
                                      400, 300)
        pixbuf.fill(0x336699ff)
        self.window = OverlayWindow(self.app, pixbuf, Settings())
        self.addCleanup(self.window.destroy)
        self.window.area.allocate(400, 300, -1, None)
        self.window._mon_rects = [(0, 0, 400, 300)]
        self.window.set_visible(True)
        self.window.sel = (100, 50, 120, 80)
        self.window._selection_made()

    def test_on_gnome_the_overlay_owns_the_clipboard_and_closes_at_once(self):
        exported = []
        real_export = self.window._export_result

        def export():
            exported.append(True)
            return real_export()

        self.window._export_result = export
        with patch.object(save_mod, "compositor_keeps_clipboard",
                          return_value=True), \
                patch.object(self.app, "hold") as hold, \
                patch.object(self.app, "release") as release:
            self.window.copy_and_close()
            self.assertFalse(self.window.get_visible())
            hold.assert_called_once()
            # Nothing is made until somebody asks for it.
            self.assertEqual(exported, [])
            clipboard = self.window.get_clipboard()
            self.assertTrue(clipboard.get_property("local"))
            self.assertTrue(clipboard.get_formats().contain_mime_type(
                "image/png"))

            got = {}
            sink = Gio.MemoryOutputStream.new_resizable()

            def spliced(out, result):
                out.splice_finish(result)
                got["png"] = bytes(out.steal_as_bytes().get_data())

            def read(cb, result):
                # Asynchronously: the content is written by this same main
                # loop, so a blocking read here would wait forever.
                stream, _mime = cb.read_finish(result)
                sink.splice_async(
                    stream, Gio.OutputStreamSpliceFlags.CLOSE_SOURCE
                    | Gio.OutputStreamSpliceFlags.CLOSE_TARGET,
                    GLib.PRIORITY_DEFAULT, None, spliced)

            clipboard.read_async(["image/png"], GLib.PRIORITY_DEFAULT, None,
                                 read)
            run_until(lambda: "png" in got and release.called)
        image = save_mod.pixbuf_from_png_bytes(got["png"])
        self.assertEqual((image.get_width(), image.get_height()), (120, 80))
        self.assertEqual(exported, [True])
        release.assert_called_once()

    def test_with_wl_copy_the_overlay_goes_before_the_encoding(self):
        seen = {}

        def copy(pixbuf):
            seen["visible"] = self.window.get_visible()
            return "wl-copy"

        with patch.object(save_mod, "compositor_keeps_clipboard",
                          return_value=False), \
                patch("shutil.which", return_value="/usr/bin/wl-copy"), \
                patch.object(save_mod, "copy_pixbuf", side_effect=copy):
            self.window.copy_and_close()
        self.assertEqual(seen, {"visible": False})

    def test_a_save_happens_off_the_screen_and_a_failure_comes_back(self):
        seen = []

        def save(pixbuf, path):
            seen.append(self.window.get_visible())
            raise OSError("disk full")

        with patch.object(save_mod, "save_pixbuf", side_effect=save):
            self.window.save_and_close()
        self.assertEqual(seen, [False])
        self.assertTrue(self.window.get_visible())     # back, to say why
        self.assertIn("disk full", self.window._toast.get_text())

    def test_on_gnome_text_goes_to_the_clipboard_from_here(self):
        with patch.object(save_mod, "compositor_keeps_clipboard",
                          return_value=True), \
                patch("subprocess.Popen") as popen:
            how = save_mod.copy_text("hello")
        popen.assert_not_called()
        self.assertEqual(how, "clipboard")
        got = {}
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.read_text_async(
            None, lambda cb, res: got.setdefault("text",
                                                 cb.read_text_finish(res)))
        run_until(lambda: "text" in got)
        self.assertEqual(got["text"], "hello")


if __name__ == "__main__":
    unittest.main()
