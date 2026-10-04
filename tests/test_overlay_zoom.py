"""Zoom and pan in the region overlay.

Needs a GTK display; skips otherwise.  Run:  python3 tests/test_overlay_zoom.py
"""

import os
import sys
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
    from wayland_feather_shot.overlay.window import OverlayWindow, ZOOM_MAX  # noqa: E402
    from wayland_feather_shot.util.settings import Settings  # noqa: E402

CTRL = 1 << 2   # Gdk.ModifierType.CONTROL_MASK


class FakeScroll:
    def __init__(self, state=0):
        self.state = state

    def get_current_event_state(self):
        return self.state


class FakePinch:
    def __init__(self, cx, cy):
        self.center = (cx, cy)

    def get_bounding_box_center(self):
        return (True, *self.center)


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayZoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.ZoomTest")
        cls.app.register(None)

    def setUp(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 400, 300)
        pixbuf.fill(0xffffffff)
        self.window = OverlayWindow(self.app, pixbuf, Settings())
        self.addCleanup(self.window.destroy)
        self.window.area.allocate(400, 300, -1, None)
        self.window.set_visible(True)
        self.window._mon_rects = [(0, 0, 400, 300)]
        self.window.sel = (50, 50, 200, 150)
        self.window._selection_made()

    def test_the_whole_screen_fits_at_first(self):
        self.assertEqual(self.window._view_params(), (1.0, 0.0, 0.0))

    def test_zooming_keeps_the_point_under_the_anchor_in_place(self):
        before = self.window._to_image(100, 120)
        self.window.zoom_at(2.0, anchor=(100, 120))
        after = self.window._to_image(100, 120)
        self.assertAlmostEqual(before[0], after[0], places=6)
        self.assertAlmostEqual(before[1], after[1], places=6)
        scale, ox, oy = self.window._view_params()
        self.assertEqual(scale, 2.0)
        self.assertLessEqual(ox, 0)
        self.assertGreaterEqual(ox + 400 * scale, 400)

    def test_cannot_zoom_out_past_the_whole_screen_or_in_past_the_limit(self):
        self.window.zoom_at(0.5)
        self.assertEqual(self.window._zoom, 1.0)
        self.window.zoom_at(100.0)
        self.assertEqual(self.window._zoom, ZOOM_MAX)

    def test_reset_returns_to_the_whole_screen(self):
        self.window.zoom_at(3.0, anchor=(300, 200))
        self.window.zoom_reset()
        self.assertEqual(self.window._view_params(), (1.0, 0.0, 0.0))

    def test_zoom_to_selection_fills_the_window_with_it(self):
        self.window.zoom_to_selection()
        self.assertGreater(self.window._zoom, 1.0)
        x, y, w, h = self.window.sel
        x0, y0 = self.window._to_widget(x, y)
        x1, y1 = self.window._to_widget(x + w, y + h)
        self.assertGreaterEqual(x0, 0)
        self.assertGreaterEqual(y0, 0)
        self.assertLessEqual(x1, 400)
        self.assertLessEqual(y1, 300)
        self.assertAlmostEqual((x0 + x1) / 2, 200, delta=1)
        self.assertAlmostEqual((y0 + y1) / 2, 150, delta=1)

    def test_handles_follow_the_zoomed_selection(self):
        self.window.zoom_at(2.0, anchor=(0, 0))
        self.assertEqual(self.window._handles()["se"], self.window._to_widget(250, 200))

    def test_keys_zoom_reset_and_fit(self):
        self.window._on_key(None, Gdk.KEY_plus, 0, CTRL)
        self.assertEqual(self.window._zoom, 1.25)
        self.window._on_key(None, Gdk.KEY_minus, 0, CTRL)
        self.assertEqual(self.window._zoom, 1.0)
        self.window._on_key(None, Gdk.KEY_1, 0, CTRL)
        self.assertGreater(self.window._zoom, 1.0)
        self.window._on_key(None, Gdk.KEY_0, 0, CTRL)
        self.assertEqual(self.window._zoom, 1.0)

    def test_a_touchpad_pinch_zooms_around_its_centre(self):
        pinch = FakePinch(100, 120)
        before = self.window._to_image(100, 120)
        self.window._on_pinch_begin(pinch, None)
        self.window._on_pinch_scale(pinch, 1.5)
        self.window._on_pinch_scale(pinch, 2.0)      # relative to the start
        self.assertEqual(self.window._zoom, 2.0)
        after = self.window._to_image(100, 120)
        self.assertAlmostEqual(before[0], after[0], places=6)
        self.assertAlmostEqual(before[1], after[1], places=6)
        self.window._on_pinch_begin(pinch, None)
        self.window._on_pinch_scale(pinch, 0.25)     # pinching in never goes below 1
        self.assertEqual(self.window._zoom, 1.0)

    def test_a_small_touchpad_scroll_step_zooms_gradually_with_ctrl(self):
        self.window._on_scroll(FakeScroll(CTRL), 0, -0.2)
        self.assertGreater(self.window._zoom, 1.0)
        self.assertLess(self.window._zoom, 1.05)

    def test_ctrl_wheel_zooms_and_plain_wheel_pans_only_when_zoomed(self):
        self.assertFalse(self.window._on_scroll(FakeScroll(0), 0, 1))
        self.assertEqual(self.window._pan, (0.0, 0.0))
        self.window._on_scroll(FakeScroll(CTRL), 0, -1)
        self.assertGreater(self.window._zoom, 1.0)
        self.window.zoom_at(4.0, anchor=(200, 150))
        before = self.window._pan
        self.window._on_scroll(FakeScroll(0), 0, 1)
        self.assertNotEqual(self.window._pan, before)
        scale, ox, oy = self.window._view_params()
        self.assertLessEqual(ox, 0)
        self.assertGreaterEqual(ox + 400 * scale, 400)


if __name__ == "__main__":
    unittest.main()
