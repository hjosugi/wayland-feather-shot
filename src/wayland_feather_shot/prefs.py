"""Settings window — a simple form over config.json.

config.json stays the source of truth; this just edits it. GTK only.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .i18n import _, tr
from .settings import DEFAULTS

# Short one-line help per setting, shown under each field.
_HELP = {
    "save_dir": "Quick-save folder (empty = Pictures/Screenshots)",
    "filename_pattern": "strftime pattern for saved filenames",
    "pen_color": "Default annotation colour (#rrggbb)",
    "pen_width": "Default line width",
    "font_size": "Default text size",
    "blur_factor": "Blur/pixelate strength",
    "scroll_top_margin": "Fixed header rows to drop (-1 = auto)",
    "scroll_bottom_margin": "Fixed footer rows to drop (-1 = auto)",
    "scroll_max_height": "Max stitched image height (px)",
    "scroll_settle_seconds": "Pause before a scroll frame is kept",
    "scroll_auto_delta": "Auto-scroll pixels per step",
    "scroll_auto_interval": "Auto-scroll seconds between steps",
    "scroll_auto_steps": "Auto-scroll max steps",
}


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, app, settings):
        super().__init__(application=app,
                         title=_("Settings — Feather Shot"))
        self.settings = settings
        self.set_default_size(560, -1)
        self._rows = {}

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_margin_top(16)
        outer.set_margin_bottom(16)
        outer.set_margin_start(16)
        outer.set_margin_end(16)
        self.set_child(outer)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        outer.append(scroller)

        listbox = Gtk.ListBox()
        listbox.add_css_class("boxed-list")
        scroller.set_child(listbox)

        for key in DEFAULTS:
            listbox.append(self._make_row(key))

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda *_: self.close())
        save = Gtk.Button(label=_("Save"))
        save.add_css_class("suggested-action")
        save.connect("clicked", self._on_save)
        buttons.append(cancel)
        buttons.append(save)
        outer.append(buttons)

    def _make_row(self, key):
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row.set_margin_top(8)
        row.set_margin_bottom(8)
        row.set_margin_start(10)
        row.set_margin_end(10)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        label = Gtk.Label(label=key, xalign=0.0)
        label.set_hexpand(True)
        proto = DEFAULTS[key]
        value = self.settings.get(key, proto)
        if isinstance(proto, bool):
            widget = Gtk.Switch()
            widget.set_active(bool(value))
            widget.set_halign(Gtk.Align.END)
        else:
            widget = Gtk.Entry()
            widget.set_text("" if value is None else str(value))
            widget.set_width_chars(22)
        self._rows[key] = widget
        top.append(label)
        top.append(widget)
        row.append(top)
        if key in _HELP:
            help_label = Gtk.Label(label=_(_HELP[key]), xalign=0.0)
            help_label.add_css_class("dim-label")
            row.append(help_label)
        return row

    def _on_save(self, _btn):
        bad = []
        for key, widget in self._rows.items():
            if isinstance(widget, Gtk.Switch):
                self.settings.set(key, widget.get_active())
            else:
                if not self.settings.set(key, widget.get_text()):
                    bad.append(key)
        if bad:
            dlg = Gtk.AlertDialog()
            dlg.set_message(tr("Invalid value for: {keys}",
                               keys=", ".join(bad)))
            dlg.show(self)
            return
        try:
            self.settings.save()
        except OSError as e:
            dlg = Gtk.AlertDialog()
            dlg.set_message(tr("Could not save settings: {error}", error=e))
            dlg.show(self)
            return
        self.close()


def open_settings(app, settings):
    win = SettingsWindow(app, settings)
    win.present()
    return win
