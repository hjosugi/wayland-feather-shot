"""Editor window: toolbar, keyboard shortcuts, save/copy actions."""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

from .. import save as save_mod
from ..i18n import _, tr
from ..theme import install_custom_css
from . import arrows as arrow_mod
from . import crop as crop_mod
from . import preset as preset_mod
from . import sidecar
from .canvas import EditorCanvas
from .shapes import Style

TOOLS = [
    # (id, label, tooltip incl. shortcut key)
    ("pen", "Pen", "Freehand pen (P)"),
    ("line", "Line", "Straight line (L)"),
    ("arrow", "Arrow", "Arrow (A)"),
    ("steparrow", "Step", "Numbered step arrow (G)"),
    ("bubble", "Bubble", "Speech bubble (U)"),
    ("emoji", "Emoji", "Emoji sticker (J)"),
    ("rect", "Rect", "Rectangle (R)"),
    ("ellipse", "Ellipse", "Ellipse (E)"),
    ("highlight", "Marker", "Highlighter pen (H)"),
    ("spotlight", "Spot", "Spotlight — dim everything outside (S)"),
    ("text", "Text", "Text — click to place (T)"),
    ("blur", "Blur", "Blur region (B)"),
    ("pixelate", "Pixel", "Pixelate region (X)"),
    ("marker", "1,2,3", "Numbered marker — click to place (M)"),
    ("crop", "Crop", "Crop image (C)"),
    ("select", "Select", "Select / move a shape (V)"),
]

TOOL_KEYS = {
    Gdk.KEY_p: "pen", Gdk.KEY_l: "line", Gdk.KEY_a: "arrow",
    Gdk.KEY_r: "rect", Gdk.KEY_e: "ellipse", Gdk.KEY_h: "highlight",
    Gdk.KEY_t: "text", Gdk.KEY_b: "blur", Gdk.KEY_x: "pixelate",
    Gdk.KEY_m: "marker", Gdk.KEY_c: "crop", Gdk.KEY_v: "select",
    Gdk.KEY_s: "spotlight",
    Gdk.KEY_g: "steparrow", Gdk.KEY_u: "bubble", Gdk.KEY_j: "emoji",
}

_NUDGE_KEYS = {
    Gdk.KEY_Left: (-1.0, 0.0), Gdk.KEY_Right: (1.0, 0.0),
    Gdk.KEY_Up: (0.0, -1.0), Gdk.KEY_Down: (0.0, 1.0),
}

EMOJI_CHOICES = ["✅", "❌", "⭐", "❤️", "👍", "👎", "⚠️", "🔥", "💡", "➡️",
                 "🎯", "🚀"]

PRESET_COLORS = [(0.90, 0.15, 0.12), (0.95, 0.55, 0.10), (0.98, 0.85, 0.10),
                 (0.20, 0.70, 0.25), (0.15, 0.50, 0.95), (0.60, 0.20, 0.80),
                 (0.10, 0.10, 0.10), (1.0, 1.0, 1.0)]
PRESET_WIDTHS = [2, 4, 8, 12]


class EditorWindow(Gtk.ApplicationWindow):
    def __init__(self, app, pixbuf: GdkPixbuf.Pixbuf, settings, shapes=None,
                 startup_toast=None, save_path=None, crop=None):
        super().__init__(application=app, title="Feather Shot")
        self.settings = settings
        self._save_path = save_path  # --output override for Ctrl+S, or None
        self._dirty = False
        self._force_close = False

        # Where the editor left off last time, falling back to the configured
        # defaults on a machine that has never opened it.
        self._preset = preset_mod.load()
        if not os.path.exists(preset_mod.PRESET_PATH):
            rgba = Gdk.RGBA()
            rgba.parse(settings.pen_color)
            self._preset = preset_mod.from_settings(settings)
            self._preset.rgba = (rgba.red, rgba.green, rgba.blue, rgba.alpha)

        style = Style(rgba=self._preset.rgba, width=self._preset.width,
                      font_size=self._preset.font_size,
                      font_family=self._preset.font_family)
        self.canvas = EditorCanvas(pixbuf, style, int(settings.blur_factor))
        self.canvas.editor.redaction_density = self._preset.redaction_density
        self.canvas.editor.spotlight_scrim = self._preset.spotlight_scrim
        self.canvas.editor.text_align = self._preset.text_align
        self.canvas.editor.head_start = self._preset.head_start
        self.canvas.editor.head_end = self._preset.head_end
        if crop is not None:
            self.canvas.set_source(pixbuf, crop)
        if shapes:
            self.canvas.shapes = list(shapes)
        self.canvas.on_edit_text = self._on_edit_text
        self.canvas.on_request_bubble = self._open_bubble_popover
        self.canvas.on_request_emoji = self._open_emoji_popover
        self.canvas.on_changed = self._on_canvas_changed

        self._build_header()

        overlay = Gtk.Overlay()
        overlay.set_child(self.canvas)
        self._toast = Gtk.Label()
        self._toast.add_css_class("wfs-toast")
        self._toast.set_halign(Gtk.Align.CENTER)
        self._toast.set_valign(Gtk.Align.END)
        self._toast.set_margin_bottom(24)
        self._toast.set_visible(False)
        overlay.add_overlay(self._toast)
        self._crop_bar = self._build_crop_bar()
        overlay.add_overlay(self._crop_bar)
        self._text_layer = self._build_text_editor()
        overlay.add_overlay(self._text_layer)
        self.set_child(overlay)
        self._install_css()

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.connect("close-request", self._on_close_request)

        self.select_tool(self._preset.tool)

        iw, ih = pixbuf.get_width(), pixbuf.get_height()
        self.set_default_size(min(iw + 40, 1500), min(ih + 110, 950))

        if startup_toast:
            GLib.idle_add(lambda: (self.toast(startup_toast, 6.0), False)[1])

    # -- UI ------------------------------------------------------------------

    def _build_header(self):
        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        tool_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        tool_box.add_css_class("linked")
        first = None
        self._tool_buttons = {}
        for tid, label, tip in TOOLS:
            btn = Gtk.ToggleButton(label=_(label))
            btn.set_tooltip_text(_(tip))
            if first is None:
                first = btn
                btn.set_active(True)
            else:
                btn.set_group(first)
            btn.connect("toggled", self._on_tool_toggled, tid)
            tool_box.append(btn)
            self._tool_buttons[tid] = btn
        header.set_title_widget(tool_box)

        color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        rgba = Gdk.RGBA()
        (rgba.red, rgba.green, rgba.blue, rgba.alpha) = self._preset.rgba
        color.set_rgba(rgba)
        color.set_tooltip_text(_("Annotation color"))
        color.connect("notify::rgba", self._on_color_changed)
        header.pack_start(color)

        width = Gtk.SpinButton.new_with_range(1, 24, 1)
        width.set_value(self._preset.width)
        width.set_tooltip_text(_("Line width"))
        width.connect("value-changed", self._on_width_changed)
        header.pack_start(width)

        font_btn = Gtk.FontDialogButton(dialog=Gtk.FontDialog())
        desc = Pango.FontDescription()
        desc.set_family(self._preset.font_family)
        desc.set_size(int(self._preset.font_size * Pango.SCALE))
        font_btn.set_font_desc(desc)
        font_btn.set_tooltip_text(_("Text font"))
        font_btn.connect("notify::font-desc", self._on_font_changed)
        header.pack_start(font_btn)

        composite = Gtk.ToggleButton()
        composite.set_icon_name("view-conceal-symbolic")
        composite.set_tooltip_text(
            _("Blur/pixelate covers annotations too (flatten)"))
        composite.connect("toggled", self._on_composite_toggled)
        header.pack_start(composite)

        header.pack_start(self._build_presets(color, width))
        header.pack_start(self._build_arrowhead_menu())
        header.pack_start(self._build_align_buttons())

        extract = self._build_extract_menu()
        if extract is not None:
            header.pack_start(extract)

        header.pack_start(self._build_zoom_controls())

        undo = Gtk.Button.new_from_icon_name("edit-undo-symbolic")
        undo.set_tooltip_text(_("Undo (Ctrl+Z)"))
        undo.connect("clicked", lambda *_: self.canvas.undo())
        redo = Gtk.Button.new_from_icon_name("edit-redo-symbolic")
        redo.set_tooltip_text(_("Redo (Ctrl+Shift+Z)"))
        redo.connect("clicked", lambda *_: self.canvas.redo())
        header.pack_start(undo)
        header.pack_start(redo)

        save_btn = Gtk.Button.new_from_icon_name("document-save-symbolic")
        save_btn.set_tooltip_text(_("Save (Ctrl+S)"))
        save_btn.connect("clicked", lambda *_: self.quick_save())
        copy_btn = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
        copy_btn.set_tooltip_text(_("Copy to clipboard (Ctrl+C)"))
        copy_btn.connect("clicked", lambda *_: self.copy_to_clipboard())
        save_as_btn = Gtk.Button.new_from_icon_name("document-save-as-symbolic")
        save_as_btn.set_tooltip_text(_("Save as… (Ctrl+Shift+S)"))
        save_as_btn.connect("clicked", lambda *_: self.save_as())
        folder_btn = Gtk.Button.new_from_icon_name("folder-open-symbolic")
        folder_btn.set_tooltip_text(_("Open save folder (Ctrl+O)"))
        folder_btn.connect("clicked", lambda *_: self.open_save_folder())
        pin_btn = Gtk.Button.new_from_icon_name("view-pin-symbolic")
        pin_btn.set_tooltip_text(_("Pin to screen (Ctrl+P)"))
        pin_btn.connect("clicked", lambda *_: self.pin_to_screen())
        header.pack_end(save_btn)
        header.pack_end(save_as_btn)
        header.pack_end(copy_btn)
        header.pack_end(folder_btn)
        header.pack_end(pin_btn)

    def _build_text_editor(self):
        """The caret that sits on the canvas while text is being typed.

        Typing where the text will actually appear, at the size it will appear,
        is the point: a popover at widget scale told you nothing about how the
        result would look at export size.
        """
        layer = Gtk.Fixed()
        layer.set_visible(False)
        layer.set_can_target(True)

        self._text_view = Gtk.TextView()
        self._text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._text_view.add_css_class("wfs-text-edit")
        self._text_view.get_buffer().connect("changed", self._on_text_changed)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_text_key)
        self._text_view.add_controller(keys)

        layer.put(self._text_view, 0, 0)
        return layer

    def _on_edit_text(self, sid):
        if sid is None:
            self._text_layer.set_visible(False)
            self.canvas.grab_focus()
            return
        buffer = self._text_view.get_buffer()
        shape = self.canvas.editor.doc.shape(sid)
        self._suppress_text_change = True
        buffer.set_text(shape.props.text if shape else "")
        self._suppress_text_change = False
        self._text_layer.set_visible(True)
        self._position_text_editor()
        self._text_view.grab_focus()

    def _position_text_editor(self):
        geometry = self.canvas.text_edit_geometry()
        if geometry is None:
            return
        x, y, width, height, font_px, rgba, align = geometry
        self._text_layer.move(self._text_view, int(x), int(y))
        self._text_view.set_size_request(int(width) + 12, int(height) + 6)
        self._text_view.set_justification({
            "left": Gtk.Justification.LEFT,
            "center": Gtk.Justification.CENTER,
            "right": Gtk.Justification.RIGHT,
        }.get(align, Gtk.Justification.LEFT))
        self._style_text_editor(font_px, rgba)

    def _style_text_editor(self, font_px, rgba):
        """Match the caret's type to the annotation's.

        Styled with a text tag rather than CSS: the size changes with the zoom
        level, and a tag carries both the size and the colour without reloading
        a stylesheet on every keystroke.
        """
        buffer = self._text_view.get_buffer()
        tag_table = buffer.get_tag_table()
        tag = tag_table.lookup("wfs-live")
        if tag is None:
            tag = buffer.create_tag("wfs-live")
        desc = Pango.FontDescription()
        desc.set_family("Sans")
        desc.set_weight(Pango.Weight.BOLD)
        desc.set_absolute_size(max(6.0, font_px) * Pango.SCALE)
        tag.set_property("font-desc", desc)
        colour = Gdk.RGBA()
        colour.red, colour.green, colour.blue, colour.alpha = rgba
        tag.set_property("foreground-rgba", colour)
        start, end = buffer.get_bounds()
        buffer.apply_tag(tag, start, end)

    def _on_text_changed(self, buffer):
        if getattr(self, "_suppress_text_change", False):
            return
        start, end = buffer.get_bounds()
        self.canvas.commit_text(buffer.get_text(start, end, False))
        # The shape grows as it is typed into, so the caret follows it.
        self._position_text_editor()

    def _on_text_key(self, _controller, keyval, _keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.canvas.stop_editing()
            return True
        # Enter is a newline; Ctrl+Enter finishes, matching the old popover.
        if (keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter)
                and state & Gdk.ModifierType.CONTROL_MASK):
            self.canvas.stop_editing()
            return True
        return False

    def _build_crop_bar(self):
        """Aspect presets plus apply/cancel, shown only while cropping.

        Crop is modal on purpose: the annotation layer is visible but not
        editable, so the bar has to say plainly how to get out of it.
        """
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.add_css_class("wfs-crop-bar")
        bar.set_halign(Gtk.Align.CENTER)
        bar.set_valign(Gtk.Align.END)
        bar.set_margin_bottom(18)
        bar.set_visible(False)

        ratios = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        ratios.add_css_class("linked")
        self._crop_buttons = {}
        first = None
        for name in crop_mod.ASPECTS:
            btn = Gtk.ToggleButton(label=_(crop_mod.ASPECT_TITLES[name]))
            if first is None:
                first = btn
                btn.set_active(True)
            else:
                btn.set_group(first)
            btn.connect("toggled", self._on_crop_aspect, name)
            ratios.append(btn)
            self._crop_buttons[name] = btn
        bar.append(ratios)

        cancel = Gtk.Button(label=_("Cancel (Esc)"))
        cancel.connect("clicked", lambda *_: self.cancel_crop())
        apply_btn = Gtk.Button(label=_("Crop (Enter)"))
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", lambda *_: self.apply_crop())
        bar.append(cancel)
        bar.append(apply_btn)
        return bar

    def _on_crop_aspect(self, button, name):
        if button.get_active():
            self.canvas.set_crop_aspect(name)

    def begin_crop(self):
        self.canvas.begin_crop()
        self._crop_bar.set_visible(True)

    def apply_crop(self):
        changed = self.canvas.apply_crop()
        self._leave_crop()
        if changed:
            self.toast(_("Cropped. Undo restores the full image."))

    def cancel_crop(self):
        self.canvas.cancel_crop()
        self._leave_crop()

    def _leave_crop(self):
        self._crop_bar.set_visible(False)
        if self.canvas.tool == "crop":
            self.select_tool("select")

    def _build_zoom_controls(self):
        """Zoom out / percentage / zoom in.  Clicking the percentage toggles
        between fit and 100%."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        box.add_css_class("linked")

        out = Gtk.Button.new_from_icon_name("zoom-out-symbolic")
        out.set_tooltip_text(_("Zoom out (Ctrl+-)"))
        out.connect("clicked", lambda *_: self.canvas.zoom_out())

        self._zoom_label = Gtk.Button(label="100%")
        self._zoom_label.set_tooltip_text(
            _("Fit / actual size (Ctrl+1 / Ctrl+0)"))
        self._zoom_label.connect("clicked", self._on_zoom_toggle)

        into = Gtk.Button.new_from_icon_name("zoom-in-symbolic")
        into.set_tooltip_text(_("Zoom in (Ctrl++)"))
        into.connect("clicked", lambda *_: self.canvas.zoom_in())

        box.append(out)
        box.append(self._zoom_label)
        box.append(into)
        self.canvas.on_zoom_changed = self._update_zoom_label
        return box

    def _on_zoom_toggle(self, _button):
        if self.canvas.zoom_to_fit:
            self.canvas.zoom_actual()
        else:
            self.canvas.zoom_fit()

    def _update_zoom_label(self):
        if getattr(self, "_zoom_label", None) is not None:
            self._zoom_label.set_label(f"{self.canvas.zoom_percent}%")

    def _build_presets(self, color_btn, width_spin):
        """A popover of colour swatches + stroke-size presets. Reuses the
        header colour/width handlers (which also restyle the selection)."""
        menu = Gtk.MenuButton()
        menu.set_icon_name("color-select-symbolic")
        menu.set_tooltip_text(_("Colour & width presets"))
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        flow = Gtk.FlowBox()
        flow.set_max_children_per_line(4)
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        for rgb in PRESET_COLORS:
            flow.append(self._swatch(rgb, color_btn, popover))
        box.append(flow)

        dim_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        dim_row.append(Gtk.Label(label=_("Spotlight dim"), xalign=0.0))
        dim = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.1, 0.9, 0.05)
        dim.set_value(self._preset.spotlight_scrim)
        dim.set_hexpand(True)
        dim.set_draw_value(False)
        dim.set_tooltip_text(_("How dark the area outside a spotlight goes"))
        dim.connect("value-changed",
                    lambda s: self.canvas.set_spotlight_scrim(s.get_value()))
        dim_row.append(dim)
        box.append(dim_row)

        wrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        wrow.set_halign(Gtk.Align.CENTER)
        for w in PRESET_WIDTHS:
            btn = Gtk.Button(label=str(w))

            def pick_width(_b, ww=w):
                width_spin.set_value(ww)   # triggers _on_width_changed
                popover.popdown()

            btn.connect("clicked", pick_width)
            wrow.append(btn)
        box.append(wrow)

        popover.set_child(box)
        menu.set_popover(popover)
        return menu

    def _build_align_buttons(self):
        """Text alignment, applied to new text and to any selected text."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        box.add_css_class("linked")
        first = None
        for name, icon, tip in (
                ("left", "format-justify-left-symbolic", _("Align left")),
                ("center", "format-justify-center-symbolic", _("Align centre")),
                ("right", "format-justify-right-symbolic", _("Align right"))):
            btn = Gtk.ToggleButton()
            btn.set_icon_name(icon)
            btn.set_tooltip_text(tip)
            if first is None:
                first = btn
                btn.set_active(True)
            else:
                btn.set_group(first)
            btn.connect("toggled", self._on_align_toggled, name)
            box.append(btn)
        return box

    def _on_align_toggled(self, button, name):
        if button.get_active():
            self.canvas.set_text_align(name)

    def _build_arrowhead_menu(self):
        """Which head each end of a new arrow gets.

        Applies to the selection too, so an arrow already drawn can be turned
        around or given a second head without redrawing it.
        """
        menu = Gtk.MenuButton()
        menu.set_icon_name("mail-forward-symbolic")
        menu.set_tooltip_text(_("Arrowheads"))
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for margin in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{margin}")(8)

        for end, label in (("head_start", _("Start")), ("head_end", _("End"))):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row.append(Gtk.Label(label=label, xalign=0.0, width_chars=5))
            chooser = Gtk.DropDown.new_from_strings(
                [_(arrow_mod.HEAD_TITLES[name]) for name in arrow_mod.HEADS])
            chooser.set_selected(arrow_mod.HEADS.index(
                "none" if end == "head_start" else "arrow"))
            chooser.connect("notify::selected", self._on_arrowhead_changed, end)
            row.append(chooser)
            box.append(row)

        popover.set_child(box)
        menu.set_popover(popover)
        return menu

    def _on_arrowhead_changed(self, chooser, _pspec, end):
        name = arrow_mod.HEADS[chooser.get_selected()]
        self.canvas.set_arrowhead(end, name)

    def _build_extract_menu(self):
        """OCR / QR menu, or None when neither tool is installed."""
        from .. import recognize
        has_ocr, has_qr = recognize.ocr_available(), recognize.qr_available()
        if not (has_ocr or has_qr):
            return None
        menu = Gtk.MenuButton()
        menu.set_icon_name("edit-find-symbolic")
        menu.set_tooltip_text(_("Extract text / QR (local)"))
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        if has_ocr:
            b = Gtk.Button(label=_("Copy text (OCR)"))
            b.add_css_class("flat")
            b.connect("clicked",
                      lambda *_: (popover.popdown(), self.extract_text("ocr")))
            box.append(b)
        if has_qr:
            b = Gtk.Button(label=_("Copy QR / barcode"))
            b.add_css_class("flat")
            b.connect("clicked",
                      lambda *_: (popover.popdown(), self.extract_text("qr")))
            box.append(b)
        popover.set_child(box)
        menu.set_popover(popover)
        return menu

    def extract_text(self, kind):
        import os
        import tempfile
        from .. import recognize
        fd, tmp = tempfile.mkstemp(prefix="wfs-ocr-", suffix=".png")
        os.close(fd)
        try:
            save_mod.save_pixbuf(self.canvas.export_pixbuf(), tmp)
            text = (recognize.run_ocr(tmp) if kind == "ocr"
                    else recognize.run_qr(tmp))
        except Exception as e:
            self.toast(tr("Recognition failed: {error}", error=e))
            return
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        if not text:
            self.toast(_("Nothing recognized."))
            return
        save_mod.copy_text(text)
        self.toast(_("Recognized text copied to clipboard."))

    def _swatch(self, rgb, color_btn, popover):
        r, g, b = rgb
        btn = Gtk.Button()
        area = Gtk.DrawingArea()
        area.set_size_request(24, 24)

        def draw(_a, cr, w, h, _d):
            cr.set_source_rgb(r, g, b)
            cr.rectangle(0, 0, w, h)
            cr.fill()

        area.set_draw_func(draw, None)
        btn.set_child(area)

        def pick(_b):
            rgba = Gdk.RGBA()
            rgba.red, rgba.green, rgba.blue, rgba.alpha = r, g, b, 1.0
            color_btn.set_rgba(rgba)       # triggers _on_color_changed
            popover.popdown()

        btn.connect("clicked", pick)
        return btn

    def _install_css(self):
        install_custom_css()

    def toast(self, message: str, seconds: float = 2.5):
        self._toast.set_text(message)
        self._toast.set_visible(True)
        GLib.timeout_add(int(seconds * 1000),
                         lambda: (self._toast.set_visible(False), False)[1])

    # -- state ------------------------------------------------------------------

    def _on_canvas_changed(self):
        self._dirty = True

    def _on_tool_toggled(self, button, tool_id):
        if not button.get_active():
            return
        if self.canvas.is_cropping and tool_id != "crop":
            # Switching tools out of a modal crop abandons it rather than
            # leaving a half-committed rect behind.
            self.canvas.cancel_crop()
            self._crop_bar.set_visible(False)
        self.canvas.tool = tool_id
        if tool_id == "crop":
            self.begin_crop()

    def select_tool(self, tool_id: str):
        btn = self._tool_buttons.get(tool_id)
        if btn:
            btn.set_active(True)

    def _apply_style(self, style: Style):
        """Set the active style and, on the select tool, restyle the
        currently selected shape too."""
        self.canvas.style = style
        if self.canvas.tool == "select":
            self.canvas.restyle_selected(style)

    def _on_color_changed(self, button, _pspec):
        rgba = button.get_rgba()
        s = self.canvas.style
        self._apply_style(Style(
            rgba=(rgba.red, rgba.green, rgba.blue, rgba.alpha),
            width=s.width, font_size=s.font_size, font_family=s.font_family))

    def _on_width_changed(self, spin):
        s = self.canvas.style
        self._apply_style(Style(rgba=s.rgba, width=spin.get_value(),
                                font_size=s.font_size,
                                font_family=s.font_family))

    def _on_composite_toggled(self, button):
        self.canvas.blur_composite = button.get_active()

    def _on_font_changed(self, button, _pspec):
        desc = button.get_font_desc()
        if desc is None:
            return
        family = desc.get_family() or "Sans"
        size = desc.get_size() / Pango.SCALE
        s = self.canvas.style
        self._apply_style(Style(
            rgba=s.rgba, width=s.width,
            font_size=size if size > 0 else s.font_size,
            font_family=family))

    # -- text tool ---------------------------------------------------------------

    def _popover_at(self, wx, wy):
        popover = Gtk.Popover()
        popover.set_parent(self.canvas)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(wx), int(wy), 1, 1
        popover.set_pointing_to(rect)
        popover.connect("closed", lambda p: GLib.idle_add(p.unparent))
        return popover

    def _open_bubble_popover(self, ix, iy, wx, wy):
        popover = self._popover_at(wx, wy)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        view = Gtk.TextView()
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_size_request(200, 60)
        buf = view.get_buffer()
        box.append(view)
        add = Gtk.Button(label=_("Add"))
        add.add_css_class("suggested-action")

        def commit(*_a):
            start, end = buf.get_bounds()
            self.canvas.add_bubble(ix, iy, buf.get_text(start, end, False))
            popover.popdown()

        add.connect("clicked", commit)
        box.append(add)
        popover.set_child(box)
        popover.popup()
        view.grab_focus()

    def _open_emoji_popover(self, ix, iy, wx, wy):
        popover = self._popover_at(wx, wy)
        grid = Gtk.FlowBox()
        grid.set_max_children_per_line(6)
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        for ch in EMOJI_CHOICES:
            btn = Gtk.Button(label=ch)
            btn.add_css_class("flat")

            def pick(_b, c=ch):
                self.canvas.add_emoji(ix, iy, c)
                popover.popdown()

            btn.connect("clicked", pick)
            grid.append(btn)
        popover.set_child(grid)
        popover.popup()

    # -- actions -------------------------------------------------------------------

    def quick_save(self):
        path = self._save_path or save_mod.timestamp_path(self.settings)
        try:
            path = save_mod.save_pixbuf(self.canvas.export_pixbuf(), path)
        except Exception as e:  # GLib.Error or OSError
            self.toast(tr("Save failed: {error}", error=e))
            return
        self._dirty = False
        self._write_sidecar(path)
        self.toast(tr("Saved  {path}", path=path))

    def _write_sidecar(self, image_path: str) -> None:
        """Keep the annotations editable next to the saved image.

        The saved file has them burned in, so the sidecar carries the untouched
        base as well; without it `edit` could only ever reopen flat pixels.
        Best effort — a screenshot that saved is saved, and failing to write the
        re-edit document must never look like the save failed.
        """
        if not self.settings.get("save_sidecar", True):
            return
        try:
            if not self.canvas.shapes:
                # Nothing to re-edit: don't litter, and drop a stale document
                # from an earlier save to this same path.
                sidecar.remove(image_path)
                return
            sidecar.save(image_path, self.canvas.shapes,
                         save_mod.pixbuf_to_png_bytes(self.canvas.source),
                         crop=self.canvas.crop_rect)
        except Exception:
            pass

    def save_as(self):
        dialog = Gtk.FileDialog()
        dialog.set_initial_name(
            os.path.basename(save_mod.timestamp_path(self.settings)))
        dialog.set_initial_folder(
            Gio.File.new_for_path(self.settings.save_dir_path))

        def done(dlg, result):
            try:
                gfile = dlg.save_finish(result)
            except GLib.Error:
                return  # cancelled
            try:
                path = save_mod.save_pixbuf(self.canvas.export_pixbuf(),
                                            gfile.get_path())
            except Exception as e:
                self.toast(tr("Save failed: {error}", error=e))
                return
            self._dirty = False
            self._write_sidecar(path)
            self.toast(tr("Saved  {path}", path=path))

        dialog.save(self, None, done)

    def copy_to_clipboard(self):
        try:
            how = save_mod.copy_pixbuf(self.canvas.export_pixbuf())
        except Exception as e:
            self.toast(tr("Copy failed: {error}", error=e))
            return
        self._dirty = False
        self.toast(tr("Copied to clipboard via {how}", how=_(how)))

    def copy_file_path(self):
        """Save to disk (if needed) and copy the file path as text."""
        path = self._save_path or save_mod.timestamp_path(self.settings)
        try:
            path = save_mod.save_pixbuf(self.canvas.export_pixbuf(), path)
            save_mod.copy_text(path)
        except Exception as e:
            self.toast(tr("Copy failed: {error}", error=e))
            return
        self._dirty = False
        self.toast(tr("Copied path  {path}", path=path))

    def open_save_folder(self):
        try:
            path = save_mod.open_folder(self.settings.save_dir_path)
        except Exception as e:
            self.toast(tr("Open folder failed: {error}", error=e))
            return
        self.toast(tr("Opened save folder  {path}", path=path))

    def pin_to_screen(self):
        from .pin import PinWindow
        PinWindow(self.get_application(),
                  self.canvas.export_pixbuf()).present()

    # -- keys / close ----------------------------------------------------------------

    def _on_key(self, _ctrl, keyval, _keycode, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        key = Gdk.keyval_to_lower(keyval)

        # Crop is modal: Return applies, Escape cancels, and every other
        # editing shortcut is swallowed so it cannot act on the layer the crop
        # overlay is covering.
        if self.canvas.is_cropping:
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                self.apply_crop()
                return True
            if keyval == Gdk.KEY_Escape:
                self.cancel_crop()
                return True
            if ctrl and key == Gdk.KEY_z:
                self.canvas.redo() if shift else self.canvas.undo()
                return True
            return True

        if ctrl and key == Gdk.KEY_s:
            self.save_as() if shift else self.quick_save()
            return True
        if ctrl and key == Gdk.KEY_c:
            if shift:
                self.copy_file_path()
            else:
                self.copy_to_clipboard()
            return True
        if ctrl and key == Gdk.KEY_o:
            self.open_save_folder()
            return True
        if ctrl and key == Gdk.KEY_p:
            self.pin_to_screen()
            return True
        if ctrl and key == Gdk.KEY_z:
            self.canvas.redo() if shift else self.canvas.undo()
            return True
        if ctrl and key == Gdk.KEY_y:
            self.canvas.redo()
            return True
        if ctrl and key == Gdk.KEY_a:
            self.canvas.select_all()
            self.select_tool("select")
            return True
        if ctrl and keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.canvas.zoom_in()
            return True
        if ctrl and keyval in (Gdk.KEY_minus, Gdk.KEY_underscore,
                               Gdk.KEY_KP_Subtract):
            self.canvas.zoom_out()
            return True
        if ctrl and keyval == Gdk.KEY_1:
            self.canvas.zoom_fit()
            return True
        if ctrl and keyval == Gdk.KEY_0:
            self.canvas.zoom_actual()
            return True
        if ctrl and keyval == Gdk.KEY_Up:
            return self.canvas.raise_selected()
        if ctrl and keyval == Gdk.KEY_Down:
            return self.canvas.lower_selected()
        if keyval in _NUDGE_KEYS:
            dx, dy = _NUDGE_KEYS[keyval]
            step = 10.0 if shift else 1.0
            return self.canvas.nudge_selected(dx * step, dy * step)
        if keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            if self.canvas.delete_selected():
                return True
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if not ctrl and not shift and key in TOOL_KEYS:
            self.select_tool(TOOL_KEYS[key])
            return True
        return False

    def _remember_style(self):
        """Persist where the editor got to.  Best effort, and never in the way
        of closing the window."""
        editor = self.canvas.editor
        style = editor.style
        self._preset.tool = editor.tool
        self._preset.rgba = tuple(style.rgba)
        self._preset.width = style.width
        self._preset.font_size = style.font_size
        self._preset.font_family = style.font_family
        self._preset.redaction_density = editor.redaction_density
        self._preset.spotlight_scrim = editor.spotlight_scrim
        self._preset.text_align = editor.text_align
        self._preset.head_start = editor.head_start
        self._preset.head_end = editor.head_end
        preset_mod.save(self._preset)

    def _on_close_request(self, _win):
        self._remember_style()
        if not self._dirty or self._force_close:
            return False
        alert = Gtk.AlertDialog()
        alert.set_message(_("Discard this screenshot?"))
        alert.set_detail(_("It has not been saved or copied."))
        alert.set_buttons([_("Cancel"), _("Discard"), _("Save & Close")])
        alert.set_default_button(2)
        alert.set_cancel_button(0)

        def chosen(dlg, result):
            try:
                idx = dlg.choose_finish(result)
            except GLib.Error:
                return
            if idx == 1:
                self._force_close = True
                self.close()
            elif idx == 2:
                self.quick_save()
                self._force_close = True
                self.close()

        alert.choose(self, None, chosen)
        return True  # keep the window until the dialog answers
