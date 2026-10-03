"""Saving to disk and copying to the Wayland clipboard.  Local only —
this application has no upload, telemetry or network code whatsoever."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
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


def pixbuf_to_png_bytes(pixbuf: GdkPixbuf.Pixbuf, fast: bool = False) -> bytes:
    """PNG bytes for *pixbuf*. *fast* uses the lightest compression: about
    ten times quicker for a screen-sized image (40-80 ms instead of 0.5-0.8 s)
    and somewhat larger, which suits the clipboard, where the bytes are
    thrown away after pasting."""
    keys, values = (["compression"], ["1"]) if fast else ([], [])
    ok, data = pixbuf.save_to_bufferv("png", keys, values)
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return bytes(data)


def pixbuf_from_png_bytes(data: bytes) -> GdkPixbuf.Pixbuf:
    """Decode PNG bytes (an editable sidecar's stored base image)."""
    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
    try:
        loader.write_bytes(GLib.Bytes.new(data))
        loader.close()
    except GLib.Error as exc:
        raise ValueError(f"could not decode the stored base image: {exc}") from exc
    pixbuf = loader.get_pixbuf()
    if pixbuf is None:
        raise ValueError("stored base image decoded to nothing")
    return pixbuf


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


def compositor_keeps_clipboard() -> bool:
    """Whether the compositor keeps a copy of the clipboard once the client
    that set it exits: GNOME's mutter does.

    There a window can set the clipboard itself and the app may exit
    afterwards. wl-copy would be worse: mutter has no data-control
    protocol, so wl-copy maps a window of its own to get the keyboard
    focus, and the focus jumps to it and back after every copy.
    """
    desktops = os.environ.get("XDG_CURRENT_DESKTOP", "").split(":")
    return bool(os.environ.get("WAYLAND_DISPLAY")) and "GNOME" in desktops


class _PendingPng(GObject.Object):
    """A PNG that is made when first asked for; see lazy_png_content."""

    def __init__(self, make_pixbuf, on_served):
        super().__init__()
        self.make_pixbuf = make_pixbuf
        self.on_served = on_served
        self.png = None
        self.encoding = False
        self.waiting = []           # serializers until the PNG is ready
        self.in_flight = 0

    def serve(self, serializer):
        self.in_flight += 1
        self.waiting.append(serializer)
        if self.png is not None:
            self._write_waiting()
        elif not self.encoding:
            self.encoding = True
            try:
                pixbuf = self.make_pixbuf()
            except Exception as exc:  # nothing to paste; say why
                self._fail_waiting(exc)
                return
            threading.Thread(target=self._encode, args=(pixbuf,),
                             daemon=True).start()

    def _encode(self, pixbuf):
        try:
            png, error = pixbuf_to_png_bytes(pixbuf, fast=True), None
        except Exception as exc:
            png, error = None, exc
        GLib.idle_add(self._encoded, png, error)

    def _encoded(self, png, error):
        self.encoding = False
        if error is not None:
            self._fail_waiting(error)
        else:
            self.png = png
            self._write_waiting()
        return False

    def _write_waiting(self):
        waiting, self.waiting = self.waiting, []
        for serializer in waiting:
            def written(stream, result, serializer=serializer):
                try:
                    stream.write_all_finish(result)
                    serializer.return_success()
                except GLib.Error as exc:
                    serializer.return_error(exc)
                self._done_one()
            serializer.get_output_stream().write_all_async(
                self.png, serializer.get_priority(),
                serializer.get_cancellable(), written)

    def _fail_waiting(self, error):
        print(f"wayland-feather-shot: clipboard image failed: {error}",
              file=sys.stderr)
        waiting, self.waiting = self.waiting, []
        for serializer in waiting:
            serializer.return_error(GLib.Error.new_literal(
                Gio.io_error_quark(), str(error), Gio.IOErrorEnum.FAILED))
            self._done_one()

    def _done_one(self):
        self.in_flight -= 1
        if self.in_flight == 0 and self.on_served is not None:
            # A moment for a second reader that asked at the same time.
            GLib.timeout_add(300, self._settled)

    def _settled(self):
        if self.in_flight == 0 and self.on_served is not None:
            on_served, self.on_served = self.on_served, None
            on_served()
        return False


_pending_png_registered = False


def lazy_png_content(make_pixbuf, on_served=None) -> Gdk.ContentProvider:
    """Clipboard content offered as image/png and made when first asked
    for.

    Setting the clipboard on Wayland needs the keyboard focus, so it has to
    happen while the window is up; making the picture and encoding it does
    not, so it waits for the first request (mutter asks at once, to keep
    its copy), by which time the window is gone. *make_pixbuf* runs on the
    main thread, the encoding on a worker thread, once. *on_served* is
    called when a request has been written in full and no other is in
    flight.

    A registered serializer rather than a Gdk.ContentProvider subclass:
    PyGObject hands an async vfunc's user data over as None, which breaks
    GDK's own callback.
    """
    global _pending_png_registered
    if not _pending_png_registered:
        Gdk.content_register_serializer(
            _PendingPng.__gtype__, "image/png",
            lambda serializer, *_: serializer.get_value().serve(serializer))
        _pending_png_registered = True
    pending = _PendingPng(make_pixbuf, on_served)
    return Gdk.ContentProvider.new_for_value(
        GObject.Value(_PendingPng, pending))


def copy_text(text: str) -> str:
    """Copy plain *text* (e.g. a saved file path) to the clipboard."""
    if compositor_keeps_clipboard():
        # Set from this (focused) window; see compositor_keeps_clipboard.
        Gdk.Display.get_default().get_clipboard().set(
            GObject.Value(GObject.TYPE_STRING, text))
        return "clipboard"
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
    png = pixbuf_to_png_bytes(pixbuf, fast=True)
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
