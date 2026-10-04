"""The overlay starts from the style the last session ended with and saves
its own when it closes (editor/preset.py), as the editor window does.

Needs a GTK display; skips otherwise.
Run:  python3 tests/test_overlay_preset.py
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

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
    from wayland_feather_shot.editor import preset as preset_mod  # noqa: E402
    from wayland_feather_shot.overlay.window import OverlayWindow  # noqa: E402
    from wayland_feather_shot.util.settings import Settings  # noqa: E402

SAVED = {
    "tool": "select", "rgba": [0.1, 0.5, 0.9, 1.0], "width": 8.0,
    "font_size": 30.0, "font_family": "Serif", "redaction_density": 0.8,
    "spotlight_scrim": 0.3, "text_align": "center", "text_style": "box",
    "head_start": "dot", "head_end": "none",
}


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.PresetTest")
        cls.app.register(None)

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "editor-preset.json")
        patcher = patch.object(preset_mod, "PRESET_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def overlay(self, **kwargs):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8,
                                      400, 300)
        window = OverlayWindow(self.app, pixbuf, Settings(), **kwargs)
        self.addCleanup(window.destroy)
        window.realize()            # close() acts on realized windows only
        return window

    def test_the_last_sessions_style_is_where_it_starts(self):
        with open(self.path, "w") as f:
            json.dump(SAVED, f)
        window = self.overlay(remember_style=True)
        self.assertEqual(window.style.rgba, (0.1, 0.5, 0.9, 1.0))
        self.assertEqual(window._size_spin.get_value(), 8.0)
        self.assertEqual(window.style.font_family, "Serif")
        self.assertEqual(window.style.font_size, 30.0)
        self.assertEqual(window.redaction_density, 0.8)
        self.assertEqual(window.spotlight_scrim, 0.3)
        self.assertEqual((window.text_align, window.text_style),
                         ("center", "box"))
        self.assertEqual(window.arrow_heads,
                         {"head_start": "dot", "head_end": "none"})

    def test_a_changed_style_is_saved_on_closing_and_the_tool_kept(self):
        with open(self.path, "w") as f:
            json.dump(SAVED, f)
        window = self.overlay(remember_style=True)
        window._set_colour((1.0, 1.0, 0.0, 1.0))
        window.close()
        with open(self.path) as f:
            saved = json.load(f)
        self.assertEqual(saved["rgba"], [1.0, 1.0, 0.0, 1.0])
        self.assertEqual(saved["tool"], "select")     # the editor's own

    def test_an_unchanged_style_is_not_written(self):
        window = self.overlay(remember_style=True)
        window.close()
        self.assertFalse(os.path.exists(self.path))

    def test_without_remember_style_nothing_is_read_or_written(self):
        with open(self.path, "w") as f:
            json.dump(SAVED, f)
        window = self.overlay()
        self.assertNotEqual(window.style.font_family, "Serif")
        window._set_colour((1.0, 1.0, 0.0, 1.0))
        window.close()
        with open(self.path) as f:
            self.assertEqual(json.load(f), SAVED)

    def test_the_width_presets_set_the_line_width(self):
        window = self.overlay()
        window.select_tool("pen")
        widths = window._style_rows["widths"]
        eight = widths.get_first_child().get_next_sibling().get_next_sibling()
        eight.emit("clicked")
        self.assertEqual(window._size_spin.get_value(), 8.0)
        self.assertEqual(window._pen_width, 8.0)


if __name__ == "__main__":
    unittest.main()
