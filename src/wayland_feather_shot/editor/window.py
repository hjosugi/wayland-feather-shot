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
    ("rect", "Rect", "Rectangle (R)"),
    ("ellipse", "Ellipse", "Ellipse (E)"),
    ("highlight", "High", "Highlighter (H)"),
    ("text", "Text", "Text — click to place (T)"),
    ("blur", "Blur", "Blur region (B)"),
    ("pixelate", "Pixel", "Pixelate region (X)"),
    ("marker", "1,2,3", "Numbered marker — click to place (M)"),
    ("crop", "Crop", "Crop image (C)"),
]

TOOL_KEYS = {
    Gdk.KEY_p: "pen", Gdk.KEY_l: "line", Gdk.KEY_a: "arrow",
    Gdk.KEY_r: "rect", Gdk.KEY_e: "ellipse", Gdk.KEY_h: "highlight",
    Gdk.KEY_t: "text", Gdk.KEY_b: "blur", Gdk.KEY_x: "pixelate",
    Gdk.KEY_m: "marker", Gdk.KEY_c: "crop",
}


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
        header.pack_end(save_btn)
        header.pack_end(save_as_btn)
        header.pack_end(copy_btn)

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

    def _on_color_changed(self, button, _pspec):
        rgba = button.get_rgba()
        s = self.canvas.style
        self.canvas.style = Style(
            rgba=(rgba.red, rgba.green, rgba.blue, rgba.alpha),
            width=s.width, font_size=s.font_size, font_family=s.font_family)

    def _on_width_changed(self, spin):
        s = self.canvas.style
        self.canvas.style = Style(rgba=s.rgba, width=spin.get_value(),
                                  font_size=s.font_size,
                                  font_family=s.font_family)

    def _on_font_changed(self, button, _pspec):
        desc = button.get_font_desc()
        if desc is None:
            return
        family = desc.get_family() or "Sans"
        size = desc.get_size() / Pango.SCALE
        s = self.canvas.style
        self.canvas.style = Style(
            rgba=s.rgba, width=s.width,
            font_size=size if size > 0 else s.font_size,
            font_family=family)

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

    # -- keys / close ----------------------------------------------------------------

    def _on_key(self, _ctrl, keyval, _keycode, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        key = Gdk.keyval_to_lower(keyval)

        if ctrl and key == Gdk.KEY_s:
            self.save_as() if shift else self.quick_save()
            return True
        if ctrl and key == Gdk.KEY_c:
            self.copy_to_clipboard()
            return True
        if ctrl and key == Gdk.KEY_z:
            self.canvas.redo() if shift else self.canvas.undo()
            return True
        if ctrl and key == Gdk.KEY_y:
            self.canvas.redo()
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
