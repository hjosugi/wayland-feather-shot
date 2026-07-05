"""Saving to disk and copying to the Wayland clipboard.  Local only —
this application has no upload, telemetry or network code whatsoever."""

from __future__ import annotations

import os
import shutil
import subprocess
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkPixbuf, GLib, GObject  # noqa: E402


def timestamp_path(settings) -> str:
    name = time.strftime(settings.filename_pattern)
    return os.path.join(settings.save_dir_path, name)


def pixbuf_to_png_bytes(pixbuf: GdkPixbuf.Pixbuf) -> bytes:
    ok, data = pixbuf.save_to_bufferv("png", [], [])
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return bytes(data)


def save_pixbuf(pixbuf: GdkPixbuf.Pixbuf, path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in ("jpg", "jpeg"):
        pixbuf.savev(path, "jpeg", ["quality"], ["92"])
    elif ext == "webp" and "webp" in _writable_formats():
        pixbuf.savev(path, "webp", [], [])
    else:
        if ext != "png":
            path = path + ".png"
        pixbuf.savev(path, "png", [], [])
    return path


def _writable_formats():
    return {f.get_name() for f in GdkPixbuf.Pixbuf.get_formats() if f.is_writable()}


def copy_pixbuf(pixbuf: GdkPixbuf.Pixbuf) -> str:
    """Copy *pixbuf* to the clipboard.  Returns a short description of the
    mechanism used.

    Preferred path is wl-copy (wl-clipboard): it forks a tiny process that
    keeps owning the clipboard, so the copy survives after this app exits —
    GTK-owned Wayland clipboards vanish with the window.  Falls back to the
    GDK clipboard when wl-copy is unavailable.
    """
    png = pixbuf_to_png_bytes(pixbuf)
    wl_copy = shutil.which("wl-copy")
    if wl_copy:
        try:
            proc = subprocess.Popen(
                [wl_copy, "--type", "image/png"], stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.stdin.write(png)
            proc.stdin.close()
            return "wl-copy"
        except OSError:
            pass

    display = Gdk.Display.get_default()
    clipboard = display.get_clipboard()
    texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    value = GObject.Value(Gdk.Texture, texture)
    provider = Gdk.ContentProvider.new_union([
        Gdk.ContentProvider.new_for_value(value),
        Gdk.ContentProvider.new_for_bytes("image/png", GLib.Bytes.new(png)),
    ])
    clipboard.set_content(provider)
    return "clipboard (valid while the editor stays open)"
