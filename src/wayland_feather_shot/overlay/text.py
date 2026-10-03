"""Typing text in place on the region overlay.

A TextView on a layer over the canvas shows the words at the size, colour
and style the annotation will have; they become a Text shape when the text
is finished. A mixin of overlay.window.OverlayWindow.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gtk, Pango  # noqa: E402

from ..editor import shapes as shape_model
from ..editor.shapes import Text
from ..i18n import _
from ..theme import style_live_text


class TextLayer(Gtk.Fixed):
    """Hosts the in-place text editor over the canvas.

    It spans the whole window, so it must not own its empty space: a press
    beside the text has to reach the canvas, where it finishes the text and
    can grab the selection, instead of landing on the layer and doing nothing.
    """

    def do_contains(self, x, y):
        return False


class OverlayTextMixin:
    """One text at a time: ``_text_edit`` holds its view and image position
    from _begin_text until _end_text turns it into a shape (or drops it)."""

    def _begin_text(self, ix, iy):
        """Type the text on the canvas, at the size and colour it will have.

        The editor window does the same (#31); a popover showed the words but
        not how big they would come out.
        """
        self._end_text(commit=True)
        view = Gtk.TextView()
        view.set_wrap_mode(Gtk.WrapMode.NONE)
        view.add_css_class("wfs-text-edit")
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_text_key)
        view.add_controller(keys)
        view.get_buffer().connect("changed",
                                  lambda *_: self._style_text_view())
        # The text is typed in the window of the monitor it was placed on.
        self._text_host = self._view
        self._place(self._text_layer, self._text_host)
        self._text_layer.put(view, 0, 0)
        self._text_layer.set_visible(True)
        self._text_edit = {"view": view, "pos": (ix, iy)}
        self._position_text_view()
        self._style_text_view()
        view.grab_focus()
        self.toast(_("Ctrl+Enter to finish, Esc to cancel"))

    def _position_text_view(self):
        """Keep the view on its image point; called again on zoom and pan."""
        if not self._text_edit:
            return
        with self._looking_through(self._text_host):
            wx, wy = self._to_widget(*self._text_edit["pos"])
        self._text_layer.move(self._text_edit["view"], int(wx), int(wy))

    def _style_text_view(self):
        """Match the typed text to the annotation: bold Sans at the current
        size times the view scale, in the current colour. A text tag rather
        than CSS, so zoom and the size spinner can change it per keystroke.

        The view is sized to the text too: Gtk.Fixed gives a child only its
        minimum size, which for a TextView is zero wide, so without this the
        words went into the buffer but never showed."""
        if not self._text_edit:
            return
        view = self._text_edit["view"]
        buffer = view.get_buffer()
        start, end = buffer.get_bounds()
        with self._looking_through(self._text_host):
            scale = self._view_params()[0]
        font = self.style.font_size
        w, h = shape_model.measure_text(buffer.get_text(start, end, False),
                                        self.style)
        view.set_size_request(int(max(w, font * 3) * scale) + 12,
                              int(max(h, font * 1.3) * scale) + 6)
        tag = buffer.get_tag_table().lookup("wfs-live")
        if tag is None:
            tag = buffer.create_tag("wfs-live")
        desc = Pango.FontDescription()
        desc.set_family(self.style.font_family)
        desc.set_weight(Pango.Weight.BOLD)
        desc.set_absolute_size(max(6.0, font * scale) * Pango.SCALE)
        tag.set_property("font-desc", desc)
        colour = Gdk.RGBA()
        colour.red, colour.green, colour.blue, colour.alpha = self.style.rgba
        tag.set_property("foreground-rgba", colour)
        buffer.apply_tag(tag, start, end)
        style_live_text(view, self.text_style, self.style.rgba, font * scale)

    def _refocus_text(self):
        """Back to typing after a toolbar control took the focus."""
        if self._text_edit:
            self._text_edit["view"].grab_focus()

    def _end_text(self, commit: bool):
        """Finish the text being typed, if any: with *commit* (and some
        non-blank text) it becomes a Text shape and an undo step; either
        way the view goes. Safe to call when nothing is being typed."""
        edit, self._text_edit = self._text_edit, None
        if not edit:
            return
        view = edit["view"]
        start, end = view.get_buffer().get_bounds()
        text = view.get_buffer().get_text(start, end, False)
        self._text_layer.remove(view)
        self._text_layer.set_visible(False)
        if commit and text.strip():
            self._push_history()
            self.shapes.append(Text(edit["pos"], text, self.style,
                                    **shape_model.text_style_flags(
                                        self.text_style)))
        self._redraw()

    def _on_text_key(self, _controller, keyval, _keycode, state):
        """The text view's own keys, ahead of its default handling."""
        if keyval == Gdk.KEY_Escape:
            self._end_text(commit=False)
            return True
        # Enter is a newline; Ctrl+Enter finishes, as in the editor window.
        if (keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter)
                and state & Gdk.ModifierType.CONTROL_MASK):
            self._end_text(commit=True)
            return True
        return False
