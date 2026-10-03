"""Text is typed on the canvas at its final size; one size control follows the tool.

Needs a GTK display; skips otherwise.  Run:  python3 tests/test_overlay_text.py
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
    gi.require_version("Pango", "1.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402
    HAVE_GTK_DISPLAY = Gdk.Display.get_default() is not None
except (ImportError, ValueError):
    HAVE_GTK_DISPLAY = False
if HAVE_GTK_DISPLAY:
    from wayland_feather_shot.overlay.window import OverlayWindow  # noqa: E402
    from wayland_feather_shot.settings import Settings  # noqa: E402

CTRL = 1 << 2


class FakeDrag:
    def __init__(self, x, y):
        self.start = (x, y)

    def get_start_point(self):
        return (True, *self.start)

    def get_current_event_state(self):
        return 0


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class OverlayTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.hjosugi.WaylandFeatherShot.TextTest")
        cls.app.register(None)

    def setUp(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 400, 300)
        pixbuf.fill(0xffffffff)
        self.window = OverlayWindow(self.app, pixbuf, Settings())
        self.addCleanup(self.window.destroy)
        self.window.area.allocate(400, 300, -1, None)
        self.window.set_visible(True)
        self.window._mon_rects = [(0, 0, 400, 300)]
        self.window.sel = (50, 50, 300, 200)
        self.window._selection_made()
        self.window.select_tool("text")

    def child_pos(self, view):
        # Gtk.Fixed.get_child_position misreports through PyGObject; the
        # layout child's transform is what Gtk.Fixed.move actually sets.
        layout = self.window._text_layer.get_layout_manager()
        return layout.get_layout_child(view).get_transform().to_translate()

    def live_font_px(self):
        buffer = self.window._text_edit["view"].get_buffer()
        tag = buffer.get_tag_table().lookup("wfs-live")
        return tag.get_property("font-desc").get_size() / Pango.SCALE

    def test_typing_happens_on_the_canvas_at_the_final_size(self):
        self.window._begin_text(100, 100)
        view = self.window._text_edit["view"]
        self.assertTrue(self.window._text_layer.get_visible())
        self.assertEqual(self.child_pos(view), (100, 100))
        self.assertEqual(self.live_font_px(), self.window.style.font_size)

    def test_the_live_text_has_room_and_grows_as_it_is_typed(self):
        # Gtk.Fixed gives a TextView its minimum width, zero: the words were
        # typed into the buffer but nothing showed.
        self.window._begin_text(100, 100)
        view = self.window._text_edit["view"]
        empty = view.get_size_request()[0]
        self.assertGreater(empty, self.window.style.font_size)
        view.get_buffer().set_text("a much longer line of text")
        self.assertGreater(view.get_size_request()[0], empty)

    def test_a_press_beside_the_live_text_reaches_the_canvas(self):
        # The layer spans the window; its empty space must not swallow the
        # press that finishes the text or grabs the selection.
        self.window._begin_text(100, 100)
        view = self.window._text_edit["view"]
        self.window._set_bars_visible(False)
        self.window._toast.set_visible(False)
        root = self.window._root
        root.allocate(400, 300, -1, None)
        picked = root.pick(110, 110, Gtk.PickFlags.DEFAULT)
        self.assertTrue(picked is view or picked.is_ancestor(view))
        self.assertIs(root.pick(320, 120, Gtk.PickFlags.DEFAULT),
                      self.window.area)

    def test_ctrl_enter_commits_a_text_shape_and_escape_discards(self):
        self.window._begin_text(100, 100)
        self.window._text_edit["view"].get_buffer().set_text("hello")
        history = len(self.window._undo)
        self.window._on_text_key(None, Gdk.KEY_Return, 0, CTRL)
        self.assertIsNone(self.window._text_edit)
        shape = self.window.shapes[-1]
        self.assertEqual((shape.kind, shape.props.text, shape.x, shape.y),
                         ("text", "hello", 100, 100))
        self.assertEqual(len(self.window._undo), history + 1)
        self.window._begin_text(120, 120)
        self.window._text_edit["view"].get_buffer().set_text("nope")
        self.window._on_text_key(None, Gdk.KEY_Escape, 0, 0)
        self.assertEqual(len(self.window.shapes), 1)

    def test_empty_text_is_dropped_and_a_press_elsewhere_commits(self):
        self.window._begin_text(100, 100)
        self.window._on_text_key(None, Gdk.KEY_Return, 0, CTRL)
        self.assertEqual(self.window.shapes, [])
        self.window._begin_text(100, 100)
        self.window._text_edit["view"].get_buffer().set_text("done")
        self.window._on_click_pressed(None, 1, 300, 250)
        self.assertEqual(self.window.shapes[-1].props.text, "done")

    def test_picking_another_tool_finishes_the_text(self):
        self.window._begin_text(100, 100)
        self.window._text_edit["view"].get_buffer().set_text("done")
        self.window.select_tool("move")
        self.assertIsNone(self.window._text_edit)
        self.assertEqual(self.window.shapes[-1].props.text, "done")

    def test_the_action_bar_keeps_the_text_being_typed(self):
        # Copy, Save, Pin and the editor hand-off take the press that would
        # have finished the text; the text belongs in what they produce.
        self.window._begin_text(100, 100)
        self.window._text_edit["view"].get_buffer().set_text("kept")
        self.window._export_cropped()
        self.assertIsNone(self.window._text_edit)
        self.assertEqual(self.window.shapes[-1].props.text, "kept")

        handed = []
        self.window.open_editor = lambda base, shapes: handed.extend(shapes)
        self.window._begin_text(120, 120)
        self.window._text_edit["view"].get_buffer().set_text("also")
        self.window._to_editor()
        self.assertEqual([s.props.text for s in handed], ["kept", "also"])

    def test_typing_goes_on_after_the_size_control_is_used(self):
        self.window._begin_text(100, 100)
        view = self.window._text_edit["view"]
        self.window._size_spin.grab_focus()
        self.window._size_spin.set_value(30)
        self.assertIs(self.window.get_focus(), view)

    def test_escape_cancels_the_text_even_from_a_toolbar_control(self):
        self.window._begin_text(100, 100)
        self.window._text_edit["view"].get_buffer().set_text("nope")
        self.assertTrue(self.window._on_key(None, Gdk.KEY_Escape, 0, 0))
        self.assertIsNone(self.window._text_edit)
        self.assertEqual(self.window.shapes, [])
        self.assertTrue(self.window.get_visible())

    def test_text_is_plain_by_default_and_the_style_can_be_picked(self):
        self.window._begin_text(100, 100)
        self.window._text_edit["view"].get_buffer().set_text("plain")
        self.window._end_text(commit=True)
        props = self.window.shapes[-1].props
        self.assertEqual((props.outline, props.background), (False, False))

        self.window._text_style_buttons["box"].set_active(True)
        self.window._begin_text(120, 120)
        view = self.window._text_edit["view"]
        self.assertTrue(view.has_css_class("wfs-live-box"))
        view.get_buffer().set_text("boxed")
        self.window._text_style_buttons["outline"].set_active(True)
        self.assertTrue(view.has_css_class("wfs-live-outline"))
        self.assertFalse(view.has_css_class("wfs-live-box"))
        self.window._end_text(commit=True)
        props = self.window.shapes[-1].props
        self.assertEqual((props.outline, props.background), (True, False))

    def test_the_style_buttons_show_only_with_the_text_tool(self):
        self.assertTrue(self.window._text_style_box.get_visible())
        self.window.select_tool("pen")
        self.assertFalse(self.window._text_style_box.get_visible())

    def test_zoom_moves_and_rescales_the_live_text(self):
        self.window._begin_text(100, 100)
        self.window.zoom_at(2.0, anchor=(0, 0))
        view = self.window._text_edit["view"]
        self.assertEqual(self.child_pos(view), (200, 200))
        self.assertEqual(self.live_font_px(), self.window.style.font_size * 2)

    def test_one_size_control_follows_the_tool(self):
        spin = self.window._size_spin
        self.assertEqual(self.window._size_kind, "text")
        self.assertEqual(spin.get_value(), self.window.style.font_size)
        spin.set_value(30)
        self.assertEqual(self.window.style.font_size, 30.0)
        self.window.select_tool("pen")
        self.assertEqual(self.window._size_kind, "width")
        self.assertEqual(spin.get_value(), 3.0)
        spin.set_value(5)
        self.assertEqual(self.window.style.width, self.window._page_width(5))
        self.assertEqual(self.window.style.font_size, 30.0)

    def test_brackets_step_the_current_size_and_restyle_live_text(self):
        self.window._begin_text(100, 100)
        before = self.live_font_px()
        self.window.step_size(+1)
        self.assertEqual(self.live_font_px(), before + 2)
        self.window._on_text_key(None, Gdk.KEY_Escape, 0, 0)
        self.window.select_tool("pen")
        self.window._on_key(None, Gdk.KEY_bracketright, 0, 0)
        self.assertEqual(self.window._size_spin.get_value(), 4.0)
        self.window._on_key(None, Gdk.KEY_bracketleft, 0, 0)
        self.assertEqual(self.window._size_spin.get_value(), 3.0)

    def test_window_keys_stay_out_of_the_way_while_typing(self):
        self.window._begin_text(100, 100)
        self.assertFalse(self.window._on_key(None, Gdk.KEY_p, 0, 0))
        self.assertEqual(self.window.tool, "text")

    # -- typing into a placed text again --

    def place(self, text, at=(100, 100)):
        self.window._begin_text(*at)
        self.window._text_edit["view"].get_buffer().set_text(text)
        self.window._end_text(commit=True)
        return self.window.shapes[-1]

    def click(self, x, y, n_press=1):
        self.window._on_click_pressed(None, n_press, x, y)
        self.window._on_click(None, n_press, x, y)

    def test_a_click_with_the_text_tool_types_into_the_text_there(self):
        placed = self.place("hello")
        self.click(placed.x + 5, placed.y + 5)
        edit = self.window._text_edit
        buffer = edit["view"].get_buffer()
        self.assertEqual(buffer.get_text(*buffer.get_bounds(), False),
                         "hello")
        self.assertEqual(self.window.shapes, [])        # lifted while typed
        buffer.set_text("hello again")
        history_before = len(self.window._undo)
        self.window._on_text_key(None, Gdk.KEY_Return, 0, CTRL)
        (changed,) = self.window.shapes
        self.assertEqual(changed.props.text, "hello again")
        self.assertEqual(changed.sid, placed.sid)
        self.assertEqual((changed.x, changed.y), (placed.x, placed.y))
        self.assertEqual(len(self.window._undo), history_before + 1)
        self.window.undo()
        self.assertEqual(self.window.shapes[0].props.text, "hello")

    def test_a_double_click_with_the_hand_types_into_a_placed_text(self):
        placed = self.place("hand me")
        self.window.select_tool("hand")
        self.click(placed.x + 5, placed.y + 5)
        # As GTK does it: the click's release before the drag's end, which
        # puts the lifted text back.
        gesture = FakeDrag(placed.x + 5, placed.y + 5)
        self.window._on_click_pressed(None, 2, placed.x + 5, placed.y + 5)
        self.window._on_drag_begin(gesture, placed.x + 5, placed.y + 5)
        self.window._on_click(None, 2, placed.x + 5, placed.y + 5)
        self.window._on_drag_end(gesture, 0, 0)
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)
        self.assertIsNotNone(self.window._text_edit)
        self.assertEqual(self.window._text_edit["original"][1], placed)

    def test_it_takes_the_texts_style_and_escape_puts_it_back(self):
        self.window._text_style_buttons["box"].set_active(True)
        self.window._align_buttons["right"].set_active(True)
        placed = self.place("styled")
        self.window._text_style_buttons["plain"].set_active(True)
        self.window._align_buttons["left"].set_active(True)
        self.click(placed.x + 5, placed.y + 5)
        self.assertEqual(self.window.text_style, "box")
        self.assertTrue(self.window._text_style_buttons["box"].get_active())
        self.assertEqual(self.window.text_align, "right")
        self.window._on_text_key(None, Gdk.KEY_Escape, 0, 0)
        self.assertEqual(self.window.shapes, [placed])

    def test_emptying_a_placed_text_removes_it_as_one_step(self):
        placed = self.place("gone soon")
        self.click(placed.x + 5, placed.y + 5)
        self.window._text_edit["view"].get_buffer().set_text("")
        self.window._on_text_key(None, Gdk.KEY_Return, 0, CTRL)
        self.assertEqual(self.window.shapes, [])
        self.window.undo()
        self.assertEqual(self.window.shapes, [placed])

    def test_a_bubble_is_typed_into_again_with_the_bubble_tool(self):
        self.window.select_tool("bubble")
        self.window._begin_text(150, 120, kind="bubble")
        self.window._text_edit["view"].get_buffer().set_text("Hi")
        self.window._end_text(commit=True)
        bubble = self.window.shapes[-1]
        self.click(bubble.x + 10, bubble.y + 10)
        self.assertEqual(self.window._text_edit["kind"], "bubble")
        self.window._text_edit["view"].get_buffer().set_text("Hi there")
        self.window._on_text_key(None, Gdk.KEY_Return, 0, CTRL)
        (changed,) = self.window.shapes
        self.assertEqual(changed.props.text, "Hi there")
        self.assertGreater(changed.props.w, bubble.props.w)


if __name__ == "__main__":
    unittest.main()
