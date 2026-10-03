"""The region overlay's controls.

The toolbar (tools, colour, the size control, text styles, undo/redo), the
action bar, the toast, and where the bars sit around the selection. A mixin of
overlay.window.OverlayWindow.
"""

from __future__ import annotations

from dataclasses import replace

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from ..editor import arrows
from ..editor import shapes as shape_model
from ..i18n import _
from .hand import WIDTH_KINDS, restyled, with_props
from .layout import layout_controls

OVERLAY_TOOLS = [
    ("move", "wfs-tool-move-symbolic", "Move / resize selection (V)"),
    ("hand", "wfs-tool-hand-symbolic",
     "Grab and move shapes; Shift or Ctrl+click picks several (S)"),
    ("pen", "wfs-tool-pen-symbolic", "Freehand pen (P)"),
    ("line", "wfs-tool-line-symbolic", "Straight line (L)"),
    ("arrow", "wfs-tool-arrow-symbolic", "Arrow (A)"),
    ("steparrow", "wfs-tool-steparrow-symbolic", "Numbered step arrow (G)"),
    ("rect", "wfs-tool-rect-symbolic", "Rectangle (R)"),
    ("ellipse", "wfs-tool-ellipse-symbolic", "Ellipse (E)"),
    ("highlight", "wfs-tool-highlight-symbolic", "Highlighter (H)"),
    ("text", "wfs-tool-text-symbolic", "Text — click to place (T)"),
    ("bubble", "wfs-tool-bubble-symbolic",
     "Speech bubble — click to type (U)"),
    ("blur", "wfs-tool-blur-symbolic", "Blur region (B)"),
    ("pixelate", "wfs-tool-pixelate-symbolic", "Pixelate region (X)"),
    ("spotlight", "wfs-tool-spotlight-symbolic",
     "Spotlight — dim everything outside (O)"),
    ("marker", "wfs-tool-marker-symbolic", "Numbered marker — click (M)"),
    ("emoji", "wfs-tool-emoji-symbolic", "Emoji sticker — click (J)"),
]
TOOL_INFO = {tid: (icon, tip) for tid, icon, tip in OVERLAY_TOOLS}

# Tools that do the same kind of thing share one button in the toolbar; its
# ▾ lists the others, and the button shows the one last picked. One-member
# families are plain buttons.
TOOL_FAMILIES = (
    ("move",), ("hand",), ("pen",), ("line",),
    ("arrow", "steparrow"),
    ("rect", "ellipse", "highlight"),
    ("text", "bubble"),
    ("blur", "pixelate", "spotlight"),
    ("marker", "emoji"),
)

# Tools whose size is a text size (the spinner shows it instead of the line
# width).
TEXT_SIZED_TOOLS = ("text", "bubble", "emoji")

# Which rows of the style menu each tool uses; the others are hidden. A row
# not listed here (the palette, the size) shows for every tool but those in
# its NOT_FOR entry.
STYLE_ROWS_FOR = {
    "text_style": ("text",),
    "align": ("text",),
    "font": ("text", "bubble"),
    "heads": ("arrow", "steparrow"),
    "strength": ("blur", "pixelate"),
    "dim": ("spotlight",),
}
STYLE_ROWS_NOT_FOR = {
    "palette": ("blur", "pixelate", "spotlight", "emoji"),
    "size": ("blur", "pixelate", "spotlight"),
    "widths": ("blur", "pixelate", "spotlight") + TEXT_SIZED_TOOLS,
}
WIDTH_PRESETS = (2, 4, 8, 12)
ALIGN_BUTTONS = (
    ("left", "format-justify-left-symbolic", "Align left"),
    ("center", "format-justify-center-symbolic", "Align centre"),
    ("right", "format-justify-right-symbolic", "Align right"),
)

# The style button's palette (the editor window's presets).
PALETTE = ((0.90, 0.15, 0.12), (0.95, 0.55, 0.10), (0.98, 0.85, 0.10),
           (0.20, 0.70, 0.25), (0.15, 0.50, 0.95), (0.60, 0.20, 0.80),
           (0.10, 0.10, 0.10), (1.0, 1.0, 1.0))


def _swatch(rgba, size=18):
    """A round colour sample; *rgba* is a callable, so it can follow the
    current colour."""
    area = Gtk.DrawingArea()
    area.set_content_width(size)
    area.set_content_height(size)

    def draw(_area, cr, width, height):
        r, g, b, a = rgba()
        radius = min(width, height) / 2 - 1
        cr.arc(width / 2, height / 2, radius, 0, 6.2832)
        cr.set_source_rgba(r, g, b, a)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.7)
        cr.set_line_width(1.5)
        cr.stroke()
    area.set_draw_func(draw)
    return area


def _round(menu_button):
    """A Gtk.MenuButton draws through an inner button; give that the round
    toolbar look the plain buttons have."""
    menu_button.get_first_child().add_css_class("wfs-round")
    return menu_button


def menu_popover(child):
    """A popover in the bars' dark style, holding *child*."""
    popover = Gtk.Popover()
    popover.add_css_class("wfs-popover")
    popover.set_child(child)
    return popover


class OverlayControlsMixin:
    """Builds the bars and reacts to them; see the module docstring."""

    # -- building ----------------------------------------------------------

    def _build_toolbar(self) -> Gtk.Widget:
        """Tools, the style button, undo and redo.

        Similar tools share a button with a ▾ menu (TOOL_FAMILIES), and the
        colour, size and text options sit behind one style button that
        shows only what the current tool uses, so the bar stays short.

        Hidden until there is a selection; _update_control_layout places it
        next to the selection with margins (the bars are overlay children
        aligned to the top-left corner).
        """
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.add_css_class("wfs-bar")
        bar.add_css_class("wfs-toolbar")
        bar.set_halign(Gtk.Align.START)
        bar.set_valign(Gtk.Align.START)
        bar.set_visible(False)

        # _tool_buttons: each tool's own button (in the bar, or in its
        # family's menu); _family_buttons: the toggles in the bar.
        self._tool_buttons = {}
        self._family_buttons = []
        self._family_of = {}
        self._family_current = []
        first = None
        for index, members in enumerate(TOOL_FAMILIES):
            toggle = Gtk.ToggleButton()
            toggle.add_css_class("wfs-round")
            if first is None:
                first = toggle
                toggle.set_active(True)
            else:
                toggle.set_group(first)
            self._family_buttons.append(toggle)
            self._family_current.append(members[0])
            self._show_tool_on(toggle, members[0])
            toggle.connect("toggled", self._on_family_toggled, index)
            for tid in members:
                self._family_of[tid] = index
            if len(members) == 1:
                self._tool_buttons[members[0]] = toggle
                bar.append(toggle)
                continue
            family = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            family.add_css_class("wfs-family")
            family.append(toggle)
            more = _round(Gtk.MenuButton())
            more.set_icon_name("pan-down-symbolic")
            more.add_css_class("wfs-more")
            more.set_tooltip_text(_("More tools like this"))
            menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            popover = menu_popover(menu)
            for tid in members:
                icon, tip = TOOL_INFO[tid]
                content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                  spacing=8)
                content.append(Gtk.Image.new_from_icon_name(icon))
                content.append(Gtk.Label(label=_(tip), xalign=0))
                item = Gtk.Button()
                item.set_child(content)
                item.add_css_class("wfs-menu-item")
                item.set_tooltip_text(_(tip))
                item.connect("clicked", self._on_family_item, tid, popover)
                menu.append(item)
                self._tool_buttons[tid] = item
            more.set_popover(popover)
            family.append(more)
            bar.append(family)

        bar.append(self._separator())
        bar.append(self._build_style_button())
        bar.append(self._separator())

        undo = Gtk.Button.new_from_icon_name("edit-undo-symbolic")
        undo.add_css_class("wfs-round")
        undo.set_tooltip_text(_("Undo (Ctrl+Z)"))
        undo.connect("clicked", lambda *_: self.undo())
        redo = Gtk.Button.new_from_icon_name("edit-redo-symbolic")
        redo.add_css_class("wfs-round")
        redo.set_tooltip_text(_("Redo (Ctrl+Shift+Z)"))
        redo.connect("clicked", lambda *_: self.redo())
        bar.append(undo)
        bar.append(redo)
        return bar

    @staticmethod
    def _separator():
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.add_css_class("wfs-sep")
        return sep

    @staticmethod
    def _show_tool_on(button, tool_id):
        icon, tip = TOOL_INFO[tool_id]
        button.set_icon_name(icon)
        button.set_tooltip_text(_(tip))
        button.update_property([Gtk.AccessibleProperty.LABEL], [_(tip)])

    def _build_style_button(self) -> Gtk.Widget:
        """Colour and size in one button; its menu holds what the current
        tool uses (STYLE_ROWS_FOR): the palette, the size, the text's style,
        alignment and font, an arrow's heads, a redaction's strength, a
        spotlight's dimming."""
        rgba = Gdk.RGBA()
        rgba.parse(self.settings.pen_color)
        self._custom_rgba = rgba

        face = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._style_swatch = _swatch(lambda: self.style.rgba)
        face.append(self._style_swatch)
        self._style_size_label = Gtk.Label()
        self._style_size_label.add_css_class("wfs-size-label")
        face.append(self._style_size_label)
        button = _round(Gtk.MenuButton())
        button.set_child(face)
        button.add_css_class("wfs-style")
        button.set_tooltip_text(_("Colour and size"))
        self._style_button = button

        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._style_rows = {}

        palette = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for r, g, b in PALETTE:
            chip = Gtk.Button()
            chip.add_css_class("wfs-chip")
            chip.set_child(_swatch(lambda c=(r, g, b): (*c, 1.0), size=20))
            chip.connect("clicked", lambda _b, c=(r, g, b):
                         self._set_colour((*c, 1.0)))
            palette.append(chip)
        custom = Gtk.Button.new_from_icon_name("color-select-symbolic")
        custom.add_css_class("wfs-chip")
        custom.set_tooltip_text(_("Annotation color"))
        custom.connect("clicked", lambda *_: self._choose_colour())
        palette.append(custom)
        menu.append(palette)
        self._style_rows["palette"] = palette

        # One size control that follows the tool: line width for the drawing
        # tools, text size for the text tool. The icon says which.
        size_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._size_icon = Gtk.Image.new_from_icon_name(
            "wfs-size-width-symbolic")
        size_row.append(self._size_icon)
        self._size_spin = Gtk.SpinButton.new_with_range(1, 24, 1)
        self._size_spin.set_value(self._pen_width)
        self._size_spin.set_tooltip_text(_("Line width ([ / ])"))
        self._size_spin.connect("value-changed", self._on_size_changed)
        size_row.append(self._size_spin)
        menu.append(size_row)
        self._style_rows["size"] = size_row

        # The editor window's width presets, one click each.
        widths = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for width in WIDTH_PRESETS:
            btn = Gtk.Button(label=str(width))
            btn.add_css_class("wfs-round")
            btn.connect("clicked", lambda _b, w=width:
                        self._size_spin.set_value(w))
            widths.append(btn)
        menu.append(widths)
        self._style_rows["widths"] = widths

        # Plain, outlined or boxed text; shown while the text tool is in use.
        self._text_style_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                       spacing=4)
        self._text_style_box.set_visible(False)
        self._text_style_buttons = {}
        first = None
        for name, icon, tip in shape_model.TEXT_STYLE_BUTTONS:
            btn = Gtk.ToggleButton()
            btn.set_icon_name(icon)
            btn.add_css_class("wfs-round")
            btn.set_tooltip_text(_(tip))
            btn.update_property([Gtk.AccessibleProperty.LABEL], [_(tip)])
            if first is None:
                first = btn
            else:
                btn.set_group(first)
            btn.set_active(name == self.text_style)
            btn.connect("toggled", self._on_text_style_toggled, name)
            self._text_style_box.append(btn)
            self._text_style_buttons[name] = btn
        menu.append(self._text_style_box)
        self._style_rows["text_style"] = self._text_style_box

        for name, row in (("align", self._build_align_row()),
                          ("font", self._build_font_row()),
                          ("heads", self._build_heads_row()),
                          ("strength", self._build_strength_row()),
                          ("dim", self._build_dim_row())):
            row.set_visible(False)
            menu.append(row)
            self._style_rows[name] = row

        popover = menu_popover(menu)
        # With the hand the rows follow the picked shapes, which change
        # with every click; look again each time the menu opens.
        popover.connect("show", lambda *_: self._refresh_style_menu())
        button.set_popover(popover)
        self._update_style_face()
        return button

    @staticmethod
    def _labelled(label, widget):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        caption = Gtk.Label(label=label, xalign=0)
        caption.add_css_class("wfs-caption")
        row.append(caption)
        widget.set_hexpand(True)
        row.append(widget)
        return row

    def _build_align_row(self):
        """Left, centre or right: how the lines of a text line up."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._align_buttons = {}
        first = None
        for name, icon, tip in ALIGN_BUTTONS:
            btn = Gtk.ToggleButton()
            btn.set_icon_name(icon)
            btn.add_css_class("wfs-round")
            btn.set_tooltip_text(_(tip))
            btn.update_property([Gtk.AccessibleProperty.LABEL], [_(tip)])
            if first is None:
                first = btn
            else:
                btn.set_group(first)
            btn.set_active(name == self.text_align)
            btn.connect("toggled", self._on_align_toggled, name)
            row.append(btn)
            self._align_buttons[name] = btn
        return row

    def _build_font_row(self):
        """The typeface of text and bubbles; their size is the spinner."""
        dialog = Gtk.FontDialog()
        button = Gtk.FontDialogButton(dialog=dialog)
        button.set_level(Gtk.FontLevel.FAMILY)
        desc = Pango.FontDescription()
        desc.set_family(self.style.font_family)
        button.set_font_desc(desc)
        button.set_tooltip_text(_("Text font"))
        button.connect("notify::font-desc", self._on_font_changed)
        self._font_button = button
        return self._labelled(_("Font"), button)

    def _build_heads_row(self):
        """Which head each end of a new arrow gets."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._head_choosers = {}
        titles = [_(arrows.HEAD_TITLES[name]) for name in arrows.HEADS]
        for end, label in (("head_start", _("Start")), ("head_end", _("End"))):
            chooser = Gtk.DropDown.new_from_strings(titles)
            chooser.set_selected(arrows.HEADS.index(self.arrow_heads[end]))
            chooser.set_tooltip_text(_("Arrowheads"))
            chooser.connect("notify::selected", self._on_head_changed, end)
            caption = Gtk.Label(label=label)
            caption.add_css_class("wfs-caption")
            row.append(caption)
            row.append(chooser)
            self._head_choosers[end] = chooser
        return row

    def _scale_row(self, label, tip, low, high, value, changed):
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,
                                         low, high, 0.05)
        scale.set_value(value)
        scale.set_draw_value(False)
        scale.set_size_request(140, -1)
        scale.set_tooltip_text(tip)
        scale.connect("value-changed", changed)
        return self._labelled(label, scale), scale

    def _build_strength_row(self):
        """How strongly blur and pixelate hide what is under them."""
        row, self._strength_scale = self._scale_row(
            _("Redaction strength"),
            _("Blur radius and mosaic block size"), 0.0, 1.0,
            self.redaction_density, self._on_strength_changed)
        return row

    def _build_dim_row(self):
        """How dark the area outside a spotlight goes."""
        row, self._dim_scale = self._scale_row(
            _("Spotlight dim"),
            _("How dark the area outside a spotlight goes"), 0.1, 0.9,
            self.spotlight_scrim, self._on_dim_changed)
        return row

    def _build_action_bar(self) -> Gtk.Widget:
        """Copy, save and pin, the rest under "…", and cancel.

        The "…" menu has a second page for the background frame
        (frame.py), which slides in over the list.

        Vertical beside the selection; _update_control_layout turns it
        horizontal when it has to sit under the toolbar instead.
        """
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        bar.add_css_class("wfs-bar")
        bar.set_halign(Gtk.Align.START)
        bar.set_valign(Gtk.Align.START)
        bar.set_visible(False)

        def button(icon, tip, cb):
            b = Gtk.Button.new_from_icon_name(icon)
            b.add_css_class("wfs-round")
            b.set_tooltip_text(_(tip))
            b.connect("clicked", lambda *_: cb())
            bar.append(b)
            return b

        # The tooltips are translated inside button().
        button("edit-copy-symbolic", "Copy to clipboard (Ctrl+C / Enter)",
               self.copy_and_close)
        button("document-save-symbolic", "Save (Ctrl+S)", self.save_and_close)
        button("view-pin-symbolic", "Pin to screen (frameless window)",
               self.pin_to_screen)

        more = _round(Gtk.MenuButton())
        more.set_icon_name("view-more-horizontal-symbolic")
        more.set_tooltip_text(_("More"))
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        pages = Gtk.Stack()
        pages.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        pages.set_hhomogeneous(False)
        pages.set_vhomogeneous(False)
        pages.add_named(menu, "menu")
        pages.add_named(self._build_frame_page(
            back=lambda: pages.set_visible_child_name("menu")), "frame")
        popover = menu_popover(pages)
        popover.connect("closed",
                        lambda *_: pages.set_visible_child_name("menu"))
        self._more_button, self._more_pages = more, pages

        def show_frame():
            pages.set_visible_child_name("frame")
            self._refresh_frame_preview()

        # (icon, label, callback, closes the menu); None: a separator.
        entries = [("document-save-as-symbolic", "Save as… (Ctrl+Shift+S)",
                    self.save_as, True),
                   ("folder-open-symbolic", "Open save folder (Ctrl+O)",
                    self.open_save_folder, True),
                   None,
                   ("wfs-frame-symbolic", "Background & framing…",
                    show_frame, False)]
        recognition = self._recognition_entries()
        if recognition:
            entries += [None] + [entry + (True,) for entry in recognition]
        if self.open_editor:
            entries += [None, ("window-new-symbolic",
                               "Open in editor window (W)", self._to_editor,
                               True)]
        for entry in entries:
            if entry is None:
                menu.append(Gtk.Separator(
                    orientation=Gtk.Orientation.HORIZONTAL))
                continue
            icon, tip, cb, closes = entry
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            content.append(Gtk.Image.new_from_icon_name(icon))
            content.append(Gtk.Label(label=_(tip), xalign=0))
            item = Gtk.Button()
            item.set_child(content)
            item.add_css_class("wfs-menu-item")
            item.connect("clicked", lambda _b, cb=cb, closes=closes: (
                popover.popdown() if closes else None, cb()))
            menu.append(item)
        more.set_popover(popover)
        bar.append(more)

        button("window-close-symbolic", "Cancel (Esc)", self.close)
        return bar

    @staticmethod
    def _keep_keys_on_the_overlay(bar):
        """Clicking a button in *bar* must not give it the keyboard focus:
        a focused button takes Enter (its own shortcut) away from the
        overlay's "Enter: copy". Tab can still reach the buttons."""
        stack = [bar]
        while stack:
            widget = stack.pop()
            if isinstance(widget, Gtk.Button):
                widget.set_focus_on_click(False)
            child = widget.get_first_child()
            while child is not None:
                stack.append(child)
                child = child.get_next_sibling()

    def toast(self, message: str, seconds: float = 2.2):
        """A short message at the bottom of the screen in use."""
        self._place(self._toast, self._view)
        self._toast.set_text(message)
        self._toast.set_visible(True)
        # A newer message gets its own time; the older one's timer goes.
        if self._toast_timer is not None:
            GLib.source_remove(self._toast_timer)

        def hide():
            self._toast_timer = None
            self._toast.set_visible(False)
            return False
        self._toast_timer = GLib.timeout_add(int(seconds * 1000), hide)

    # -- reacting ----------------------------------------------------------

    def _on_family_toggled(self, button, index):
        # Grouped toggle buttons: only the one becoming active matters.
        if button.get_active():
            self._use_tool(self._family_current[index])

    def _on_family_item(self, _item, tool_id, popover):
        popover.popdown()
        self.select_tool(tool_id)

    def _use_tool(self, tool_id):
        # Another tool finishes the text being typed, as a press does; the
        # size control is about to stop sizing it.
        self._end_text(commit=True)
        self.tool = tool_id
        if tool_id != "hand":
            self._picked.clear()
        cursor = "default" if tool_id in ("move", "hand") else "crosshair"
        for view in self._views:
            view.area.set_cursor(Gdk.Cursor.new_from_name(cursor))
        self._refresh_style_menu()

    def select_tool(self, tool_id):
        """Switch to *tool_id*: its family's button shows it and turns on."""
        index = self._family_of.get(tool_id)
        if index is None:
            return
        self._family_current[index] = tool_id
        toggle = self._family_buttons[index]
        self._show_tool_on(toggle, tool_id)
        if toggle.get_active():
            self._use_tool(tool_id)      # same family: no toggled signal
        else:
            toggle.set_active(True)

    def _page_width(self, slider_value: float) -> float:
        """An authored stroke width in image pixels."""
        longest = max(self.pixbuf.get_width(), self.pixbuf.get_height())
        return shape_model.page_stroke_width(slider_value, longest)

    def _set_colour(self, rgba):
        """The colour for new shapes, the text being typed and the picked
        shapes."""
        self.style = replace(self.style, rgba=tuple(rgba))
        self._restyle_picked("colour", lambda s: restyled(s, rgba=tuple(rgba)))
        self._update_style_face()
        self._style_text_view()
        self._refocus_text()

    def _choose_colour(self):
        """Any colour, from GTK's colour dialog."""
        self._style_button.popdown()
        current = Gdk.RGBA()
        current.red, current.green, current.blue, current.alpha = \
            self.style.rgba

        def chosen(dialog, result):
            try:
                rgba = dialog.choose_rgba_finish(result)
            except GLib.Error:
                return                        # cancelled
            self._set_colour((rgba.red, rgba.green, rgba.blue, rgba.alpha))
        Gtk.ColorDialog().choose_rgba(self._view.window, current, None, chosen)

    def _update_style_face(self):
        """The style button shows the colour and the current size, or for
        a redaction or a spotlight how strong it is."""
        if getattr(self, "_style_swatch", None) is None:
            return
        self._style_swatch.queue_draw()
        tools = self._style_tools()
        if tools and tools <= {"blur", "pixelate"}:
            self._style_size_label.set_text(
                f"{round(self.redaction_density * 100)}%")
        elif tools == {"spotlight"}:
            self._style_size_label.set_text(
                f"{round(self.spotlight_scrim * 100)}%")
        elif getattr(self, "_size_spin", None) is not None:
            self._style_size_label.set_text(
                f"{self._size_spin.get_value():g}")

    def _show_style(self):
        """Set the controls to the current style, after it was taken from
        a placed shape; the picked shapes keep theirs."""
        self._showing_style = True
        try:
            for name, button in self._text_style_buttons.items():
                button.set_active(name == self.text_style)
            for name, button in self._align_buttons.items():
                button.set_active(name == self.text_align)
            desc = Pango.FontDescription()
            desc.set_family(self.style.font_family)
            self._font_button.set_font_desc(desc)
            self._refresh_style_menu()
        finally:
            self._showing_style = False

    def _refresh_style_menu(self):
        """Show the style menu's rows for the current tool, and point the
        size spinner at what it sizes."""
        spin = getattr(self, "_size_spin", None)
        if spin is None:
            return
        tools = self._style_tools()
        for name, row in self._style_rows.items():
            if name in STYLE_ROWS_FOR:
                row.set_visible(bool(tools & set(STYLE_ROWS_FOR[name])))
            else:
                row.set_visible(bool(tools - set(STYLE_ROWS_NOT_FOR[name])))
        kind = ("text" if tools <= set(TEXT_SIZED_TOOLS) else "width")
        self._size_kind = kind
        self._size_syncing = True
        try:
            if kind == "text":
                spin.set_range(8, 96)
                spin.set_increments(2, 8)
                spin.set_value(self.style.font_size)
                spin.set_tooltip_text(_("Text size ([ / ])"))
                self._size_icon.set_from_icon_name("wfs-tool-text-symbolic")
            else:
                spin.set_range(1, 24)
                spin.set_increments(1, 4)
                spin.set_value(self._pen_width)
                spin.set_tooltip_text(_("Line width ([ / ])"))
                self._size_icon.set_from_icon_name("wfs-size-width-symbolic")
        finally:
            self._size_syncing = False
        self._update_style_face()

    def _on_size_changed(self, spin):
        self._update_style_face()
        if self._size_syncing:
            return
        if self._size_kind == "text":
            size = float(spin.get_value())
            self.style = replace(self.style, font_size=size)
            self._restyle_picked("size", lambda s: (
                with_props(s, ("emoji",), size=max(8.0, size * 2.2))
                or restyled(s, ("text", "bubble"), font_size=size)),
                sliding=True)
            self._style_text_view()
            self._refocus_text()
        else:
            self._pen_width = spin.get_value()
            width = self._page_width(self._pen_width)
            self.style = replace(self.style, width=width)
            self._restyle_picked("width", lambda s: restyled(
                s, WIDTH_KINDS, width=width), sliding=True)

    def _on_text_style_toggled(self, button, name):
        if button.get_active():
            self.text_style = name
            self._restyle_picked("text style", lambda s: with_props(
                s, ("text",), remeasure=True,
                **shape_model.text_style_flags(name)))
            self._style_text_view()
            self._refocus_text()

    def _on_align_toggled(self, button, name):
        if button.get_active():
            self.text_align = name
            self._restyle_picked("align", lambda s: with_props(
                s, ("text",), remeasure=True, align=name))
            self._style_text_view()
            self._refocus_text()

    def _on_font_changed(self, button, _pspec):
        desc = button.get_font_desc()
        family = desc.get_family() if desc is not None else None
        if not family:
            return
        self.style = replace(self.style, font_family=family)
        self._restyle_picked("font", lambda s: restyled(
            s, ("text", "bubble"), font_family=family))
        self._style_text_view()
        self._refocus_text()

    def _on_head_changed(self, chooser, _pspec, end):
        head = arrows.HEADS[chooser.get_selected()]
        self.arrow_heads[end] = head
        self._restyle_picked(end, lambda s: with_props(
            s, ("arrow",), **{end: head}))

    def _on_strength_changed(self, scale):
        density = scale.get_value()
        self.redaction_density = density
        self._restyle_picked("strength", lambda s: with_props(
            s, ("obscure",), density=density), sliding=True)
        self._update_style_face()

    def _on_dim_changed(self, scale):
        scrim = scale.get_value()
        self.spotlight_scrim = scrim
        self._restyle_picked("dim", lambda s: with_props(
            s, ("spotlight",), scrim=scrim), sliding=True)
        self._update_style_face()

    def step_size(self, direction: int) -> None:
        """Nudge the current size (line width or text size) by one step."""
        step = self._size_spin.get_adjustment().get_step_increment()
        self._size_spin.spin(Gtk.SpinType.STEP_FORWARD if direction > 0
                             else Gtk.SpinType.STEP_BACKWARD, step)

    # -- placing the bars ---------------------------------------------------

    def _set_bars_visible(self, visible: bool):
        self._bars_visible = visible
        self._toolbar.set_visible(visible)
        self._action_bar.set_visible(visible)
        if not visible:
            self._bar_rects = ()

    def _update_control_layout(self):
        """Put the toolbar and action bar around the selection, in the
        window of the monitor that holds it.

        overlay/layout.py decides where (GTK-free, unit-tested); this
        measures the bars, applies the result as margins and remembers the
        bars' rectangles so the size label can stay clear of them. Runs
        whenever the selection, the view or the toolbar's width changes.
        """
        if not self.sel:
            return
        home = self._home_view()
        self._bars_view = home
        for bar in (self._toolbar, self._action_bar):
            self._place(bar, home)
        with self._looking_through(home):
            self._lay_out_bars()

    def _lay_out_bars(self):
        win_w = max(1, self.area.get_width())
        win_h = max(1, self.area.get_height())
        x, y, w, h = self.sel
        wx0, wy0 = self._to_widget(x, y)
        wx1, wy1 = self._to_widget(x + w, y + h)
        def bar_size(bar):
            return (
                max(1, bar.measure(Gtk.Orientation.HORIZONTAL, -1)[1]
                    - bar.get_margin_start() - bar.get_margin_end()),
                max(1, bar.measure(Gtk.Orientation.VERTICAL, -1)[1]
                    - bar.get_margin_top() - bar.get_margin_bottom()),
            )

        toolbar_size = bar_size(self._toolbar)
        # The action bar's size both ways is measured once: flipping its
        # orientation to measure is not free, and its buttons never change.
        if self._action_sizes is None:
            self._action_bar.set_orientation(Gtk.Orientation.VERTICAL)
            vertical_size = bar_size(self._action_bar)
            self._action_bar.set_orientation(Gtk.Orientation.HORIZONTAL)
            horizontal_size = bar_size(self._action_bar)
            self._action_sizes = (vertical_size, horizontal_size)

        vertical_size, horizontal_size = self._action_sizes
        layout = layout_controls(
            (win_w, win_h), (wx0, wy0, wx1, wy1), toolbar_size,
            vertical_size, horizontal_size,
        )
        self._action_bar.set_orientation(
            Gtk.Orientation.HORIZONTAL if layout.stacked
            else Gtk.Orientation.VERTICAL)
        toolbar_pos, action_pos = layout.toolbar, layout.actions
        tb_w, tb_h = toolbar_size
        action_w, action_h = (horizontal_size if layout.stacked
                              else vertical_size)
        self._toolbar.set_margin_start(toolbar_pos[0])
        self._toolbar.set_margin_top(toolbar_pos[1])
        self._action_bar.set_margin_start(action_pos[0])
        self._action_bar.set_margin_top(action_pos[1])
        self._bar_rects = (
            (toolbar_pos[0], toolbar_pos[1],
             toolbar_pos[0] + tb_w, toolbar_pos[1] + tb_h),
            (action_pos[0], action_pos[1],
             action_pos[0] + action_w, action_pos[1] + action_h),
        )
        self._redraw()
