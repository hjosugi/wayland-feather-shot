"""Editor window: toolbar, keyboard shortcuts, save/copy actions."""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

from .. import save as save_mod
from ..i18n import _, tr
from .canvas import EditorCanvas
from .tools import Style

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
    ("highlight", "High", "Highlighter (H)"),
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
    Gdk.KEY_g: "steparrow", Gdk.KEY_u: "bubble", Gdk.KEY_j: "emoji",
}

EMOJI_CHOICES = ["✅", "❌", "⭐", "❤️", "👍", "👎", "⚠️", "🔥", "💡", "➡️",
                 "🎯", "🚀"]

PRESET_COLORS = [(0.90, 0.15, 0.12), (0.95, 0.55, 0.10), (0.98, 0.85, 0.10),
                 (0.20, 0.70, 0.25), (0.15, 0.50, 0.95), (0.60, 0.20, 0.80),
                 (0.10, 0.10, 0.10), (1.0, 1.0, 1.0)]
PRESET_WIDTHS = [2, 4, 8, 12]


class EditorWindow(Gtk.ApplicationWindow):
    def __init__(self, app, pixbuf: GdkPixbuf.Pixbuf, settings, shapes=None,
                 startup_toast=None, save_path=None):
        super().__init__(application=app, title="Feather Shot")
        self.settings = settings
        self._save_path = save_path  # --output override for Ctrl+S, or None
        self._dirty = False
        self._force_close = False

        rgba = Gdk.RGBA()
        rgba.parse(settings.pen_color)
        style = Style(rgba=(rgba.red, rgba.green, rgba.blue, rgba.alpha),
                      width=float(settings.pen_width),
                      font_size=float(settings.font_size))
        self.canvas = EditorCanvas(pixbuf, style, int(settings.blur_factor))
        if shapes:
            self.canvas.shapes = list(shapes)
        self.canvas.on_request_text = self._open_text_popover
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
        self.set_child(overlay)
        self._install_css()

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.connect("close-request", self._on_close_request)

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
        rgba.parse(self.settings.pen_color)
        color.set_rgba(rgba)
        color.set_tooltip_text(_("Annotation color"))
        color.connect("notify::rgba", self._on_color_changed)
        header.pack_start(color)

        width = Gtk.SpinButton.new_with_range(1, 24, 1)
        width.set_value(float(self.settings.pen_width))
        width.set_tooltip_text(_("Line width"))
        width.connect("value-changed", self._on_width_changed)
        header.pack_start(width)

        font_btn = Gtk.FontDialogButton(dialog=Gtk.FontDialog())
        desc = Pango.FontDescription()
        desc.set_family("Sans")
        desc.set_size(int(float(self.settings.font_size) * Pango.SCALE))
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

        extract = self._build_extract_menu()
        if extract is not None:
            header.pack_start(extract)

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
        pin_btn = Gtk.Button.new_from_icon_name("view-pin-symbolic")
        pin_btn.set_tooltip_text(_("Pin to screen (Ctrl+P)"))
        pin_btn.connect("clicked", lambda *_: self.pin_to_screen())
        header.pack_end(save_btn)
        header.pack_end(save_as_btn)
        header.pack_end(copy_btn)
        header.pack_end(pin_btn)

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
        css = b"""
        .wfs-toast {
            background-color: rgba(20, 20, 24, 0.92);
            color: #ffffff;
            border-radius: 9px;
            padding: 8px 18px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def toast(self, message: str, seconds: float = 2.5):
        self._toast.set_text(message)
        self._toast.set_visible(True)
        GLib.timeout_add(int(seconds * 1000),
                         lambda: (self._toast.set_visible(False), False)[1])

    # -- state ------------------------------------------------------------------

    def _on_canvas_changed(self):
        self._dirty = True

    def _on_tool_toggled(self, button, tool_id):
        if button.get_active():
            self.canvas.tool = tool_id

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

    def _open_text_popover(self, ix, iy, wx, wy):
        popover = Gtk.Popover()
        popover.set_parent(self.canvas)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(wx), int(wy), 1, 1
        popover.set_pointing_to(rect)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        view = Gtk.TextView()
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_size_request(240, 72)
        view.add_css_class("wfs-text-entry")
        buf = view.get_buffer()
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(view)
        scroller.set_size_request(240, 72)
        box.append(scroller)

        opts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outline_chk = Gtk.CheckButton(label=_("Outline"))
        outline_chk.set_active(True)
        bg_chk = Gtk.CheckButton(label=_("Background"))
        opts.append(outline_chk)
        opts.append(bg_chk)
        opts.append(Gtk.Box(hexpand=True))  # spacer
        add_btn = Gtk.Button(label=_("Add"))
        add_btn.add_css_class("suggested-action")
        opts.append(add_btn)
        box.append(opts)
        box.append(Gtk.Label(
            label=_("Enter: newline · Ctrl+Enter: add"),
            css_classes=["dim-label"]))

        def commit(*_a):
            start, end = buf.get_bounds()
            text = buf.get_text(start, end, False)
            self.canvas.add_text(ix, iy, text,
                                 outline=outline_chk.get_active(),
                                 background=bg_chk.get_active())
            popover.popdown()

        add_btn.connect("clicked", commit)

        keys = Gtk.EventControllerKey()

        def on_key(_c, keyval, _kc, state):
            if (keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter)
                    and state & Gdk.ModifierType.CONTROL_MASK):
                commit()
                return True
            return False

        keys.connect("key-pressed", on_key)
        view.add_controller(keys)

        popover.set_child(box)
        popover.connect("closed", lambda p: GLib.idle_add(p.unparent))
        popover.popup()
        view.grab_focus()

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
        self.toast(tr("Saved  {path}", path=path))

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

    def pin_to_screen(self):
        from .pin import PinWindow
        PinWindow(self.get_application(),
                  self.canvas.export_pixbuf()).present()

    # -- keys / close ----------------------------------------------------------------

    def _on_key(self, _ctrl, keyval, _keycode, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        key = Gdk.keyval_to_lower(keyval)

        if ctrl and key == Gdk.KEY_s:
            self.save_as() if shift else self.quick_save()
            return True
        if ctrl and key == Gdk.KEY_c:
            if shift:
                self.copy_file_path()
            else:
                self.copy_to_clipboard()
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

    def _on_close_request(self, _win):
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
