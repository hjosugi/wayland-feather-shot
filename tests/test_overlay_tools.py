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


class OverlayCase:
    """An overlay with a selection made; for the test classes below."""

    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot." + cls.APP)
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


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayToolTests(OverlayCase, unittest.TestCase):
    APP = "ToolTest"

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


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayStyleMenuTests(OverlayCase, unittest.TestCase):
    """The style button's menu offers what the current tool uses."""

    APP = "StyleMenuTest"

    def visible_rows(self):
        return {name for name, row in self.window._style_rows.items()
                if row.get_visible()}

    def test_each_tool_shows_its_own_rows(self):
        for tool, rows in (
                ("pen", {"palette", "size"}),
                ("text", {"palette", "size", "text_style", "align", "font"}),
                ("bubble", {"palette", "size", "font"}),
                ("arrow", {"palette", "size", "heads"}),
                ("steparrow", {"palette", "size", "heads"}),
                ("blur", {"strength"}),
                ("spotlight", {"dim"}),
                ("emoji", {"size"})):
            with self.subTest(tool=tool):
                self.window.select_tool(tool)
                self.assertEqual(self.visible_rows(), rows)

    def test_arrowheads_apply_to_new_arrows(self):
        from wayland_feather_shot.editor import arrows
        self.window._head_choosers["head_start"].set_selected(
            arrows.HEADS.index("dot"))
        self.window._head_choosers["head_end"].set_selected(
            arrows.HEADS.index("none"))
        self.window.select_tool("arrow")
        self.drag(80, 80, 200, 150)
        props = self.window.shapes[-1].props
        self.assertEqual((props.head_start, props.head_end), ("dot", "none"))

    def test_alignment_applies_to_the_text_and_its_live_view(self):
        self.window.select_tool("text")
        self.window._align_buttons["center"].set_active(True)
        self.click(120, 90)
        view = self.window._text_edit["view"]
        self.assertEqual(view.get_justification(), Gtk.Justification.CENTER)
        view.get_buffer().set_text("one\nlonger line")
        self.window._on_text_key(None, Gdk.KEY_Return, 0, CTRL)
        self.assertEqual(self.window.shapes[-1].props.align, "center")

    def test_the_font_is_kept_when_the_colour_or_size_changes(self):
        gi.require_version("Pango", "1.0")
        from gi.repository import Pango
        desc = Pango.FontDescription()
        desc.set_family("Serif")
        self.window._font_button.set_font_desc(desc)
        self.assertEqual(self.window.style.font_family, "Serif")
        self.window._set_colour((0.1, 0.5, 0.9, 1.0))
        self.window.select_tool("text")
        self.window._size_spin.set_value(40)
        self.assertEqual(self.window.style.font_family, "Serif")

    def test_strength_and_dim_reach_new_shapes_and_the_button(self):
        self.window._strength_scale.set_value(0.9)
        self.window.select_tool("pixelate")
        self.assertEqual(self.window._style_size_label.get_text(), "90%")
        self.drag(80, 80, 160, 140)
        self.assertAlmostEqual(self.window.shapes[-1].props.density, 0.9)
        self.window._dim_scale.set_value(0.3)
        self.window.select_tool("spotlight")
        self.assertEqual(self.window._style_size_label.get_text(), "30%")
        self.drag(200, 100, 300, 200)
        self.assertAlmostEqual(self.window.shapes[-1].props.scrim, 0.3)


if __name__ == "__main__":
    unittest.main()
