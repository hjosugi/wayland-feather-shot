"""Typing text in place on the region overlay.

A TextView on a layer over the canvas shows the words at the size, colour
and style the annotation will have; they become a Text shape, or a speech
bubble around them, when the text is finished. A mixin of
overlay.window.OverlayWindow.
"""

from __future__ import annotations

from dataclasses import replace

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gtk, Pango  # noqa: E402

from ..editor import render
from ..editor import shapes as shape_model
from ..editor.shapes import SpeechBubble, Text
from ..i18n import _
from ..theme import style_live_bubble, style_live_text


JUSTIFICATIONS = {"left": Gtk.Justification.LEFT,
                  "center": Gtk.Justification.CENTER,
                  "right": Gtk.Justification.RIGHT}


class TextLayer(Gtk.Fixed):
    """Hosts the in-place text editor over the canvas.

    It spans the whole window, so it must not own its empty space: a press
    beside the text has to reach the canvas, where it finishes the text and
    can grab the selection, instead of landing on the layer and doing nothing.
    """

    def do_contains(self, x, y):
        return False


class OverlayTextMixin:
    """One text at a time: ``_text_edit`` holds its view, image position,
    kind ("text" or "bubble") and, when a placed one is edited again, its
    place and original, from _begin_text until _end_text turns it into a
    shape (or drops it)."""

    def _begin_text(self, ix, iy, kind="text"):
        """Type the text on the canvas, at the size and colour it will have.

        The editor window does the same (#31); a popover showed the words but
        not how big they would come out. A bubble is typed inside a live
        bubble whose top-left corner is at (ix, iy).
        """
        self._end_text(commit=True)
        self._open_text_view(ix, iy, kind)

    def _edit_placed_text(self, index):
        """Type into the placed text or bubble at *index* again.

        It leaves the composite while it is typed into, and its style
        becomes the current one, so the controls show it and can change it.
        """
        self._end_text(commit=True)
        shape = self.shapes[index]
        style = shape.props.style
        self.style = replace(self.style, rgba=style.rgba,
                             font_size=style.font_size,
                             font_family=style.font_family)
        if shape.kind == "text":
            self.text_style = shape_model.text_style_of(shape.props)
            self.text_align = shape.props.align
        self._show_style()
        del self.shapes[index]
        self._open_text_view(shape.x, shape.y, shape.kind,
                             original=(index, shape))
        self._text_edit["view"].get_buffer().set_text(shape.props.text)
        self._redraw()

    def _open_text_view(self, ix, iy, kind, original=None):
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
        self._text_edit = {"view": view, "pos": (ix, iy), "kind": kind,
                           "original": original}
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
        text = buffer.get_text(start, end, False)
        with self._looking_through(self._text_host):
            scale = self._view_params()[0]
        bubble = self._text_edit["kind"] == "bubble"
        if bubble:
            # Dark, regular-weight words inside a padded white body, as
            # render._draw_bubble draws them.
            font = render.bubble_text_size(self.style)
            rgba = render.BUBBLE_TEXT_RGBA
            w, h = render.bubble_body(text, self.style)
            border = max(1.5, self.style.width) * scale
            # The CSS border sits inside the view and pushes the words in;
            # take it off the padding so they land where they will be drawn.
            pad = max(0, int(round(render.BUBBLE_PAD * scale - border)))
            for side in ("left", "right", "top", "bottom"):
                getattr(view, f"set_{side}_margin")(pad)
            view.set_size_request(
                int(max(w, font * 3 + 2 * render.BUBBLE_PAD) * scale),
                int(max(h, font * 1.3 + 2 * render.BUBBLE_PAD) * scale))
            style_live_bubble(view, self.style.rgba, border,
                              min(14.0, w / 3, h / 3) * scale)
        else:
            font = self.style.font_size
            rgba = self.style.rgba
            w, h = shape_model.measure_text(text, self.style)
            view.set_size_request(int(max(w, font * 3) * scale) + 12,
                                  int(max(h, font * 1.3) * scale) + 6)
            style_live_text(view, self.text_style, rgba, font * scale)
            view.set_justification(JUSTIFICATIONS[self.text_align])
        tag = buffer.get_tag_table().lookup("wfs-live")
        if tag is None:
            tag = buffer.create_tag("wfs-live")
        desc = Pango.FontDescription()
        desc.set_family(self.style.font_family)
        desc.set_weight(Pango.Weight.NORMAL if bubble else Pango.Weight.BOLD)
        desc.set_absolute_size(max(6.0, font * scale) * Pango.SCALE)
        tag.set_property("font-desc", desc)
        colour = Gdk.RGBA()
        colour.red, colour.green, colour.blue, colour.alpha = rgba
        tag.set_property("foreground-rgba", colour)
        buffer.apply_tag(tag, start, end)

    def _refocus_text(self):
        """Back to typing after a toolbar control took the focus."""
        if self._text_edit:
            self._text_edit["view"].grab_focus()

    def _end_text(self, commit: bool):
        """Finish the text being typed, if any: with *commit* (and some
        non-blank text) it becomes a Text shape or a bubble, and an undo
        step; either way the view goes. A placed text typed into again
        takes its place back, changed, removed when emptied, or as it was
        when cancelled. Safe to call when nothing is being typed."""
        edit, self._text_edit = self._text_edit, None
        if not edit:
            return
        view = edit["view"]
        start, end = view.get_buffer().get_bounds()
        text = view.get_buffer().get_text(start, end, False)
        self._text_layer.remove(view)
        self._text_layer.set_visible(False)
        original = edit["original"]
        if original is not None:
            index, shape = original
            self.shapes.insert(index, shape)
            if commit:
                changed = self._retexted(shape, text)
                if changed != shape:
                    self._push_history()
                    if changed is None:
                        del self.shapes[index]
                    else:
                        self.shapes[index] = changed
        elif commit and text.strip():
            self._push_history()
            if edit["kind"] == "bubble":
                w, h = render.bubble_body(text, self.style)
                self.shapes.append(
                    SpeechBubble((*edit["pos"], w, h), text, self.style))
            else:
                self.shapes.append(Text(edit["pos"], text, self.style,
                                        align=self.text_align,
                                        **shape_model.text_style_flags(
                                            self.text_style)))
        self._redraw()

    def _retexted(self, shape, text):
        """*shape* with new words and the current style, or None when the
        words are gone. Its place, turn and identity stay."""
        if not text.strip():
            return None
        style = replace(shape.props.style, rgba=self.style.rgba,
                        font_size=self.style.font_size,
                        font_family=self.style.font_family)
        if shape.kind == "bubble":
            w, h = render.bubble_body(text, style)
            return replace(shape, props=replace(shape.props, text=text,
                                                style=style, w=w, h=h))
        shape = shape.retexted(text)
        return replace(shape, props=replace(
            shape.props, style=style, align=self.text_align,
            **shape_model.text_style_flags(self.text_style)).remeasured())

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
