"""With several monitors each gets its own overlay window, showing its own
part of the screenshot; the selection, shapes and history are shared.

Needs a GTK display; skips otherwise.  Run:  python3 tests/test_overlay_monitors.py
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
    from wayland_feather_shot.overlay.window import OverlayWindow  # noqa: E402
    from wayland_feather_shot.util.settings import Settings  # noqa: E402


class FakeDrag:
    def __init__(self, x, y):
        self.start = (x, y)

    def get_start_point(self):
        return (True, *self.start)


# Two 400x300 monitors, one above the other, in a 400x600 screenshot.
TOP, BOTTOM = (0, 0, 400, 300), (0, 300, 400, 300)


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.MonitorTest")
        cls.app.register(None)

    def setUp(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 400, 600)
        pixbuf.fill(0xffffffff)
        self.window = OverlayWindow(self.app, pixbuf, Settings(),
                                    monitor_layout=[(None, TOP), (None, BOTTOM)])
        self.addCleanup(self.window.destroy)
        self.window._mon_rects = [TOP, BOTTOM]
        self.top, self.bottom = self.window._views
        for view in self.window._views:
            view.area.allocate(400, 300, -1, None)

    def on(self, view):
        """Act as the input controllers do: make *view* current."""
        self.window._view = view
        return self.window

    def drag(self, view, x0, y0, x1, y1):
        window, gesture = self.on(view), FakeDrag(x0, y0)
        window._on_drag_begin(gesture, x0, y0)
        window._on_drag_update(gesture, x1 - x0, y1 - y0)
        window._on_drag_end(gesture, x1 - x0, y1 - y0)

    def test_each_window_shows_its_own_monitor_at_full_size(self):
        self.assertEqual(self.on(self.top)._to_image(10, 20), (10, 20))
        self.assertEqual(self.on(self.bottom)._to_image(10, 20), (10, 320))
        self.assertEqual(self.on(self.bottom)._view_params()[0], 1.0)

    def test_a_selection_on_the_lower_monitor_takes_the_bars_there(self):
        self.drag(self.bottom, 50, 50, 250, 200)
        self.assertEqual(self.window.sel, (50, 350, 200, 150))
        self.assertIs(self.window._toolbar.get_parent(), self.bottom.root)
        self.assertIs(self.window._action_bar.get_parent(), self.bottom.root)
        # A new selection on the upper monitor brings them back.
        self.window.undo()
        self.drag(self.top, 60, 60, 260, 210)
        self.assertEqual(self.window.sel, (60, 60, 200, 150))
        self.assertIs(self.window._toolbar.get_parent(), self.top.root)

    def test_text_is_typed_on_the_monitor_it_was_placed_on(self):
        self.drag(self.bottom, 20, 20, 380, 280)
        self.on(self.bottom).select_tool("text")
        self.window._begin_text(*self.window._to_image(100, 100))
        self.assertIs(self.window._text_layer.get_parent(), self.bottom.root)
        layout = self.window._text_layer.get_layout_manager()
        view = self.window._text_edit["view"]
        position = layout.get_layout_child(view).get_transform().to_translate()
        self.assertEqual(position, (100, 100))

    def test_history_and_drawing_are_shared(self):
        self.drag(self.top, 10, 10, 390, 290)
        self.on(self.top).select_tool("rect")
        self.drag(self.top, 50, 50, 150, 120)
        self.assertEqual(len(self.window.shapes), 1)
        for view in self.window._views:
            self.window._draw_view(view.area, Gtk.Snapshot.new(), 400, 300)
        self.on(self.bottom).undo()
        self.assertEqual(self.window.shapes, [])

    def test_closing_the_overlay_closes_every_monitor_window(self):
        # close() only acts on realized windows, as they are once shown.
        self.window.realize()
        self.bottom.window.realize()
        self.assertIn(self.bottom.window, Gtk.Window.list_toplevels())
        self.window.close()
        self.assertNotIn(self.bottom.window, Gtk.Window.list_toplevels())

    def test_full_screen_shows_everything_in_one_window(self):
        # Ctrl+PrtSc: the whole screenshot at once on the active monitor,
        # not split over the monitors.
        from unittest.mock import patch
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8,
                                      400, 600)
        with patch.object(OverlayWindow, "_monitor_layout",
                          return_value=[(None, TOP), (None, BOTTOM)]):
            window = OverlayWindow(self.app, pixbuf, Settings(),
                                   select_all=True)
        self.addCleanup(window.destroy)
        (view,) = window._views
        self.assertEqual(view.rect, (0, 0, 400, 600))
        self.assertEqual(window.sel, (0, 0, 400, 600))

    def full_screen_window(self):
        """A Ctrl+PrtSc overlay of the two monitors, not shown: present and
        fullscreen_on_monitor are recorded instead."""
        from unittest.mock import Mock, patch
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8,
                                      400, 600)
        with patch.object(OverlayWindow, "_monitor_layout",
                          return_value=[("upper", TOP), ("lower", BOTTOM)]):
            window = OverlayWindow(self.app, pixbuf, Settings(),
                                   select_all=True)
        self.addCleanup(window.destroy)
        window.present = Mock()
        window.fullscreen_on_monitor = Mock()
        return window

    def probe(self, window):
        from wayland_feather_shot.overlay.pointer import PointerProbe
        probe = PointerProbe(window, window._scene.background,
                             [("upper", TOP), ("lower", BOTTOM)])
        for frozen in probe._windows:
            self.addCleanup(frozen.destroy)
        return probe

    def test_full_screen_opens_on_the_monitor_the_pointer_enters(self):
        window = self.full_screen_window()
        probe = self.probe(window)
        upper, lower = probe._windows
        probe._found(1)
        window.fullscreen_on_monitor.assert_called_once_with("lower")
        window.present.assert_called_once_with()
        # The upper monitor's frozen window goes now; the lower one stays
        # under the overlay until it has appeared.
        self.assertNotIn(upper, Gtk.Window.list_toplevels())
        self.assertIn(lower, Gtk.Window.list_toplevels())
        # Entering another one later changes nothing.
        probe._found(0)
        window.fullscreen_on_monitor.assert_called_once_with("lower")
        window.present.assert_called_once_with()

    def test_without_the_pointer_the_compositor_places_the_overlay(self):
        window = self.full_screen_window()
        probe = self.probe(window)
        probe._timed_out()
        window.fullscreen_on_monitor.assert_not_called()
        window.present.assert_called_once_with()
        for frozen in probe._windows:
            self.assertIn(frozen, Gtk.Window.list_toplevels())

    def test_full_screen_looks_for_the_pointer_before_opening(self):
        from unittest.mock import patch
        window = self.full_screen_window()
        layout = [("upper", TOP), ("lower", BOTTOM)]
        with patch.object(OverlayWindow, "_monitor_layout",
                          return_value=layout), \
                patch("wayland_feather_shot.overlay.window.PointerProbe") \
                as probe:
            window.present_on_pointer_monitor()
        probe.assert_called_once_with(window, window._scene.background,
                                      layout)
        probe.return_value.start.assert_called_once_with()
        window.present.assert_not_called()

    def test_a_region_capture_opens_on_every_monitor_without_a_probe(self):
        from unittest.mock import Mock, patch
        self.window.present = Mock()
        with patch("wayland_feather_shot.overlay.window.PointerProbe") as probe:
            self.window.present_on_pointer_monitor()
        probe.assert_not_called()
        self.window.present.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
