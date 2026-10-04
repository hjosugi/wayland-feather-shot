"""Pictures that are not a fresh screenshot open in the overlay too: a file
(`edit`), one reopened from the history with its annotations, a window or
scripted capture, and a scrolling capture's tall result.

Needs a GTK display; skips otherwise.
Run:  python3 tests/test_overlay_document.py
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import gi  # noqa: E402
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402
    HAVE_GTK_DISPLAY = Gdk.Display.get_default() is not None
except (ImportError, ValueError):
    HAVE_GTK_DISPLAY = False
if HAVE_GTK_DISPLAY:
    from wayland_feather_shot.app import FeatherShotApp  # noqa: E402
    from wayland_feather_shot.editor import sidecar  # noqa: E402
    from wayland_feather_shot.editor.shapes import (  # noqa: E402
        RectShape, Style)
    from wayland_feather_shot.overlay.window import OverlayWindow  # noqa: E402
    from wayland_feather_shot.util.settings import Settings  # noqa: E402


def picture(width, height, colour=0x336699ff):
    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8,
                                  width, height)
    pixbuf.fill(colour)
    return pixbuf


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = FeatherShotApp(mode="edit", delay=0)
        cls.app.set_application_id(
            "io.github.hjosugi.WaylandFeatherShot.DocumentTest")
        cls.app.register(None)

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.settings = Settings()
        self.settings.set("save_sidecar", True)
        self.app.settings = self.settings

    def opened(self, app, open_it):
        """The window *open_it* opens in *app*."""
        before = set(app.get_windows())
        open_it()
        (window,) = [w for w in app.get_windows() if w not in before]
        self.addCleanup(window.destroy)
        return window

    def test_a_saved_annotation_reopens_where_it_was(self):
        path = os.path.join(self.dir.name, "shot.png")
        overlay = OverlayWindow(self.app, picture(400, 300), self.settings,
                                selection=(50, 40, 200, 150), save_path=path)
        self.addCleanup(overlay.destroy)
        rect = RectShape((80, 70, 60, 40), overlay.style)
        overlay.shapes.append(rect)
        overlay.save_and_close()
        self.assertTrue(os.path.exists(path))
        document = sidecar.load(path)
        self.assertEqual(len(document.shapes), 1)
        # The sidecar keeps the selection's pixels and its coordinates.
        self.assertEqual((document.shapes[0].x, document.shapes[0].y),
                         (30, 30))

        reopened = self.opened(self.app,
                               lambda: self.app._open_existing(path))
        self.assertEqual(reopened.sel, (0, 0, 200, 150))
        (shape,) = reopened.shapes
        self.assertEqual((shape.x, shape.y), (30, 30))
        self.assertEqual(shape.props.w, rect.props.w)

    def test_without_annotations_no_sidecar_is_left(self):
        path = os.path.join(self.dir.name, "plain.png")
        overlay = OverlayWindow(self.app, picture(100, 80), self.settings,
                                select_all=True, save_path=path)
        self.addCleanup(overlay.destroy)
        overlay.save_and_close()
        self.assertTrue(os.path.exists(path))
        self.assertFalse(os.path.exists(sidecar.sidecar_path(path)))

    def test_a_sidecar_crop_becomes_the_selection(self):
        base = picture(400, 200)
        shapes = [RectShape((10, 10, 20, 20), Style())]
        overlay = self.opened(self.app, lambda: self.app._open_picture(
            base, shapes, crop=(0.25, 0.5, 0.5, 0.5)))
        self.assertEqual(overlay.sel, (100, 100, 200, 100))
        self.assertEqual((overlay.shapes[0].x, overlay.shapes[0].y),
                         (110, 110))

    def test_a_tall_picture_starts_at_the_windows_width(self):
        overlay = OverlayWindow(self.app, picture(400, 4000), self.settings,
                                select_all=True)
        self.addCleanup(overlay.destroy)
        overlay.area.allocate(400, 300, -1, None)
        overlay._on_canvas_resized(400, 300)
        scale, ox, oy = overlay._view_params()
        self.assertAlmostEqual(scale, 1.0)
        self.assertAlmostEqual(oy, 0.0)
        # And it can still zoom in past a pixel per screen pixel.
        self.assertGreater(overlay._zoom_max(), overlay._zoom)

    def test_a_window_capture_starts_with_all_of_it_selected(self):
        app = FeatherShotApp(mode="window", delay=0)
        app.set_application_id(
            "io.github.hjosugi.WaylandFeatherShot.WindowDocTest")
        app.register(None)
        fd, path = tempfile.mkstemp(suffix=".png", dir=self.dir.name)
        os.close(fd)
        picture(120, 90).savev(path, "png", [], [])
        overlay = self.opened(app, lambda: app._open_capture(path))
        self.assertEqual(overlay.sel, (0, 0, 120, 90))


if __name__ == "__main__":
    unittest.main()
