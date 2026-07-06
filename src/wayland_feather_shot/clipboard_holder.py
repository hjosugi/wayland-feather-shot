"""Standalone clipboard holder process.

A Wayland clipboard is owned by a living client: once the app that copied an
image exits, the data is gone.  `wl-copy` works around this by forking a tiny
holder process; when it is not installed we ship our own equivalent here.

The main app copies an image by writing it to a temp PNG and spawning this
module detached (see ``save.copy_pixbuf``).  This process owns the clipboard
until another client takes it (or an optional timeout elapses), then exits —
so the copy survives the app closing, with no external dependency.

Invoked as::

    python3 -m wayland_feather_shot.clipboard_holder PNGPATH [--timeout SECONDS]

`gi` is imported lazily inside ``main`` so the pure helpers below stay
importable (and unit-testable) on machines without GTK.
"""

from __future__ import annotations

import os
import sys


def holder_command(png_path: str, python: str | None = None,
                   timeout: int = 0) -> tuple[list, dict]:
    """Build the (argv, env) for spawning this holder as a detached process.

    Pure and side-effect free so it can be unit tested.  PYTHONPATH is
    extended with this package's source root so the child can import
    ``wayland_feather_shot`` regardless of how the app was launched
    (repo checkout, ``install.sh`` copy, or pip install).
    """
    python = python or sys.executable
    cmd = [python, "-m", "wayland_feather_shot.clipboard_holder", png_path]
    if timeout and timeout > 0:
        cmd += ["--timeout", str(int(timeout))]
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../src
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (src_dir if not existing
                         else src_dir + os.pathsep + existing)
    return cmd, env


def parse_args(argv):
    """Parse ``[PNGPATH, --timeout, N]`` into ``(path, timeout_seconds)``."""
    path = None
    timeout = 0
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--timeout":
            i += 1
            timeout = int(argv[i]) if i < len(argv) else 0
        elif path is None:
            path = a
        i += 1
    if path is None:
        raise SystemExit("clipboard_holder: missing PNG path argument")
    return path, timeout


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    path, timeout = parse_args(argv)

    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, GObject  # noqa: E402

    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        with open(path, "rb") as fh:
            png = fh.read()
    except (GLib.Error, OSError) as e:
        print(f"clipboard_holder: cannot read {path}: {e}", file=sys.stderr)
        return 1
    finally:
        # It is our own temp file; drop it once loaded.
        try:
            os.unlink(path)
        except OSError:
            pass

    display = Gdk.Display.get_default()
    if display is None:
        print("clipboard_holder: no Wayland display", file=sys.stderr)
        return 1
    clipboard = display.get_clipboard()

    texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    value = GObject.Value(Gdk.Texture, texture)
    provider = Gdk.ContentProvider.new_union([
        Gdk.ContentProvider.new_for_value(value),
        Gdk.ContentProvider.new_for_bytes("image/png", GLib.Bytes.new(png)),
    ])
    clipboard.set_content(provider)

    loop = GLib.MainLoop()

    def on_changed(_cb):
        # Someone else took ownership of the clipboard: our job is done.
        if not clipboard.is_local():
            loop.quit()

    clipboard.connect("changed", on_changed)
    if timeout and timeout > 0:
        GLib.timeout_add_seconds(timeout, lambda: (loop.quit(), False)[1])

    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
