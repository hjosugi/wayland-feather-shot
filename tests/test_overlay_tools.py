"""The tools that came over from the editor window: numbered step arrows,
speech bubbles, spotlights and emoji stickers.

Needs a GTK display; skips otherwise.  Run:  python3 tests/test_overlay_tools.py
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
    from wayland_feather_shot.editor import render  # noqa: E402
    from wayland_feather_shot.editor.shapes import EMOJI_CHOICES  # noqa: E402
    from wayland_feather_shot.overlay.window import OverlayWindow  # noqa: E402
    from wayland_feather_shot.settings import Settings  # noqa: E402

CTRL = 1 << 2


class FakeDrag:
    def __init__(self, x, y):
        self.start = (x, y)

    def get_start_point(self):
        return (True, *self.start)


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.ToolTest")
        cls.app.register(None)

    def setUp(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8,
                                      400, 300)
        pixbuf.fill(0xffffffff)
        self.window = OverlayWindow(self.app, pixbuf, Settings())
        self.addCleanup(self.window.destroy)
        self.window.area.allocate(400, 300, -1, None)
        self.window.set_visible(True)
        self.window._mon_rects = [(0, 0, 400, 300)]
        self.window.sel = (50, 50, 300, 200)
        self.window._selection_made()

    def drag(self, x0, y0, x1, y1):
        gesture = FakeDrag(x0, y0)
        self.window._on_drag_begin(gesture, x0, y0)
        self.window._on_drag_update(gesture, x1 - x0, y1 - y0)
        self.window._on_drag_end(gesture, x1 - x0, y1 - y0)

    def click(self, x, y):
        self.window._on_click_pressed(None, 1, x, y)
        self.window._on_click(None, 1, x, y)

    def test_each_tool_joins_the_family_it_belongs_to(self):
        family_of = self.window._family_of
        for tool, sibling in (("steparrow", "arrow"), ("bubble", "text"),
                              ("spotlight", "blur"), ("emoji", "marker")):
            with self.subTest(tool=tool):
                self.assertEqual(family_of[tool], family_of[sibling])

    def test_tool_keys(self):
        for key, tool in ((Gdk.KEY_g, "steparrow"), (Gdk.KEY_u, "bubble"),
                          (Gdk.KEY_o, "spotlight"), (Gdk.KEY_j, "emoji")):
            with self.subTest(tool=tool):
                self.window._on_key(None, key, 0, 0)
                self.assertEqual(self.window.tool, tool)

    def test_step_arrows_and_markers_count_on_together(self):
        self.window.select_tool("steparrow")
        self.drag(80, 80, 200, 150)
        self.window.select_tool("marker")
        self.click(250, 100)
        self.window.select_tool("steparrow")
        self.drag(100, 200, 300, 220)
        arrow1, marker, arrow2 = self.window.shapes
        self.assertEqual(arrow1.kind, "arrow")
        self.assertEqual((arrow1.props.number, marker.props.number,
                          arrow2.props.number), (1, 2, 3))
        self.window.undo()
        self.assertEqual(len(self.window.shapes), 2)

    def test_a_spotlight_dims_the_rest_of_the_result(self):
        self.window.select_tool("spotlight")
        self.drag(100, 100, 200, 160)
        self.assertEqual(self.window.shapes[0].kind, "spotlight")
        result = self.window._export_cropped()
        pixels, stride = result.get_pixels(), result.get_rowstride()
        channels = result.get_n_channels()

        def red(ix, iy):
            # The result is the selection, which starts at (50, 50).
            return pixels[(iy - 50) * stride + (ix - 50) * channels]

        self.assertEqual(red(150, 130), 255)          # inside: untouched
        self.assertLess(red(70, 70), 160)             # outside: dimmed

    def test_a_bubble_is_typed_in_place_and_fits_its_text(self):
        self.window.select_tool("bubble")
        self.click(120, 90)
        edit = self.window._text_edit
        self.assertEqual(edit["kind"], "bubble")
        self.assertTrue(edit["view"].has_css_class("wfs-live-bubble"))
        edit["view"].get_buffer().set_text("Look here")
        self.window._on_text_key(None, Gdk.KEY_Return, 0, CTRL)
        (bubble,) = self.window.shapes
        self.assertEqual(bubble.kind, "bubble")
        self.assertEqual(bubble.props.text, "Look here")
        self.assertEqual((bubble.x, bubble.y), (120, 90))
        w, h = render.bubble_body("Look here", self.window.style)
        self.assertEqual((bubble.props.w, bubble.props.h), (w, h))

    def test_an_emoji_is_picked_where_the_click_was(self):
        self.window.select_tool("emoji")
        self.click(140, 110)
        popover = self.window.area.get_first_child()
        self.assertIsInstance(popover, Gtk.Popover)
        grid = popover.get_child()
        buttons = []
        child = grid.get_first_child()
        while child is not None:
            buttons.append(child.get_child())
            child = child.get_next_sibling()
        self.assertEqual([b.get_label() for b in buttons],
                         list(EMOJI_CHOICES))
        buttons[2].emit("clicked")
        (sticker,) = self.window.shapes
        self.assertEqual(sticker.kind, "emoji")
        self.assertEqual(sticker.props.char, EMOJI_CHOICES[2])
        self.assertEqual((sticker.x, sticker.y), (140, 110))

    def test_bubble_and_emoji_are_sized_like_text(self):
        for tool in ("bubble", "emoji"):
            with self.subTest(tool=tool):
                self.window.select_tool(tool)
                self.assertEqual(self.window._size_kind, "text")
                self.assertFalse(self.window._text_style_box.get_visible())


if __name__ == "__main__":
    unittest.main()
