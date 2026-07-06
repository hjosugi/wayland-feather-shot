"""Recent-screenshots gallery.

The listing (:func:`recent_screenshots`) is gi-free and unit-tested; the
gallery window is GTK.  Local only — it just reads the save directory.
"""

from __future__ import annotations

import os

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".avif", ".bmp", ".tiff",
              ".gif")


def recent_screenshots(directory, limit: int = 40, exts=IMAGE_EXTS):
    """Return up to *limit* image paths in *directory*, newest first."""
    try:
        entries = []
        with os.scandir(directory) as it:
            for e in it:
                if (e.is_file()
                        and os.path.splitext(e.name)[1].lower() in exts):
                    try:
                        entries.append((e.stat().st_mtime, e.path))
                    except OSError:
                        continue
    except OSError:
        return []
    entries.sort(key=lambda t: t[0], reverse=True)
    return [p for _mtime, p in entries[:limit]]


def _build_window(app, settings, open_file):
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

    from .i18n import _, tr

    class HistoryWindow(Gtk.ApplicationWindow):
        def __init__(self):
            super().__init__(application=app,
                             title=_("Recent screenshots — Feather Shot"))
            self.set_default_size(820, 600)
            directory = settings.save_dir_path
            paths = recent_screenshots(directory)

            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.set_child(scroller)

            if not paths:
                label = Gtk.Label(label=tr("No screenshots yet in {dir}",
                                           dir=directory))
                label.set_vexpand(True)
                scroller.set_child(label)
                return

            flow = Gtk.FlowBox()
            flow.set_valign(Gtk.Align.START)
            flow.set_max_children_per_line(5)
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_margin_top(12)
            flow.set_margin_bottom(12)
            flow.set_margin_start(12)
            flow.set_margin_end(12)
            flow.set_row_spacing(12)
            flow.set_column_spacing(12)
            scroller.set_child(flow)

            for path in paths:
                flow.append(self._thumb(path))
            flow.connect("child-activated", self._on_activated)
            self._paths = paths

        def _thumb(self, path):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    path, 220, 160, True)
                img = Gtk.Picture.new_for_pixbuf(pb)
            except GLib.Error:
                img = Gtk.Label(label="?")
            img.set_size_request(220, 160)
            name = Gtk.Label(label=os.path.basename(path))
            name.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            name.set_max_width_chars(26)
            box.append(img)
            box.append(name)
            box.add_css_class("card")
            return box

        def _on_activated(self, _flow, child):
            idx = child.get_index()
            if 0 <= idx < len(self._paths):
                open_file(self._paths[idx])

    return HistoryWindow()


def open_gallery(app, settings, open_file):
    """Create and present the gallery window."""
    win = _build_window(app, settings, open_file)
    win.present()
    return win
