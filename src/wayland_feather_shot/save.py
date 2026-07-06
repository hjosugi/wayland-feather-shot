"""Saving to disk and copying to the Wayland clipboard.  Local only —
this application has no upload, telemetry or network code whatsoever."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, GObject  # noqa: E402
from gi.repository import Gio  # noqa: E402

from . import clipboard_holder
from .imaging import format_for_path, writable_image_extensions


def timestamp_path(settings) -> str:
    name = time.strftime(settings.filename_pattern)
    return os.path.join(settings.save_dir_path, name)


def pixbuf_to_png_bytes(pixbuf: GdkPixbuf.Pixbuf) -> bytes:
    ok, data = pixbuf.save_to_bufferv("png", [], [])
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return bytes(data)


def save_pixbuf(pixbuf: GdkPixbuf.Pixbuf, path: str) -> str:
    name, path, options = format_for_path(path, _writable_formats())
    keys = [k for k, _v in options]
    values = [v for _k, v in options]
    pixbuf.savev(path, name, keys, values)
    return path


def open_folder(path: str) -> str:
    """Open *path* in the desktop file manager and return the opened path."""
    os.makedirs(path, exist_ok=True)
    uri = GLib.filename_to_uri(path, None)
    Gio.AppInfo.launch_default_for_uri(uri, None)
    return path


def _writable_formats():
    return {f.get_name() for f in GdkPixbuf.Pixbuf.get_formats() if f.is_writable()}


def writable_image_formats():
    """Extensions we can save to on this system (always includes png)."""
    return writable_image_extensions(_writable_formats())


def copy_text(text: str) -> str:
    """Copy plain *text* (e.g. a saved file path) to the clipboard."""
    wl_copy = shutil.which("wl-copy")
    if wl_copy:
        try:
            proc = subprocess.Popen(
                [wl_copy, "--type", "text/plain"], stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.stdin.write(text.encode("utf-8"))
            proc.stdin.close()
            return "wl-copy"
        except OSError:
            pass
    display = Gdk.Display.get_default()
    clipboard = display.get_clipboard()
    clipboard.set_content(Gdk.ContentProvider.new_for_bytes(
        "text/plain;charset=utf-8", GLib.Bytes.new(text.encode("utf-8"))))
    return "clipboard (valid while the editor stays open)"


def _spawn_holder(png: bytes):
    """Write *png* to a temp file and launch the detached clipboard holder.
    Returns a short description on success, or None to fall back."""
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix="wfs-clip-", suffix=".png")
        with os.fdopen(fd, "wb") as fh:
            fh.write(png)
        cmd, env = clipboard_holder.holder_command(tmp)
        subprocess.Popen(cmd, env=env, start_new_session=True,
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "holder process"
    except OSError:
        if tmp:
            try:
                os.unlink(tmp)  # holder never started; clean up our temp
            except OSError:
                pass
        return None


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

    # No wl-clipboard: spawn our own detached holder process so the copy
    # still outlives this app (see clipboard_holder).  Falls back to the
    # in-process GDK clipboard (valid only while the window stays open).
    holder = _spawn_holder(png)
    if holder:
        return holder

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
