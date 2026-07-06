"""Command-line entry point.

Deliberately import-light: `diagnose`, `--help` and `--version` must work on
machines where GTK/PyGObject is missing or broken, and every other mode
should fail with a pointer to `wayland-feather-shot diagnose` instead of a
bare ImportError traceback.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__

MODES = ["gui", "full", "window", "scroll", "gif", "edit", "history",
         "settings", "daemon", "diagnose"]

# Stable exit codes, so `wayland-feather-shot` can be used in scripts.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2          # also argparse's own error code
EXIT_CANCELLED = 130    # user cancelled (matches SIGINT convention)

# Modes that actually capture the screen and can be scripted with
# --region / --output / --no-editor.
CAPTURE_MODES = {"gui", "full"}


def parse_region(value: str):
    """Parse a ``X,Y,W,H`` crop region into a 4-int tuple.

    Pure and side-effect free so it can be unit tested without GTK.  Raises
    ValueError with a clear message on malformed input.
    """
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 4:
        raise ValueError("region must be X,Y,W,H (four comma-separated integers)")
    try:
        x, y, w, h = (int(p) for p in parts)
    except ValueError:
        raise ValueError("region X,Y,W,H must all be integers")
    if x < 0 or y < 0:
        raise ValueError("region X and Y must be >= 0")
    if w <= 0 or h <= 0:
        raise ValueError("region width and height must be > 0")
    return (x, y, w, h)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wayland-feather-shot",
        description="Flameshot-style screenshot tool built Wayland-first: "
                    "portal capture, in-place annotation (pen, arrow, blur, "
                    "…), scrolling capture. 100% local — no upload, no "
                    "network code.")
    parser.add_argument("mode", nargs="?", default="gui", choices=MODES,
                        help="gui: region capture (default) / full: whole "
                             "screen / window: pick a window via the portal "
                             "picker / scroll: scrolling capture / edit: "
                             "open an existing image in the editor / "
                             "daemon: GlobalShortcuts-portal hotkey daemon "
                             "/ diagnose: print runtime environment checks")
    parser.add_argument("file", nargs="?", metavar="FILE",
                        help="image to open (edit mode only)")
    parser.add_argument("-d", "--delay", type=float, default=0.0,
                        metavar="SEC", help="delay before capturing")

    script = parser.add_argument_group(
        "scripting (gui/full)",
        "non-interactive options for use in scripts")
    script.add_argument("--region", metavar="X,Y,W,H",
                        help="crop the capture to this pixel region")
    script.add_argument("--output", "-o", metavar="PATH",
                        help="write the capture to PATH (PNG/JPEG/WebP by "
                             "extension) instead of the default folder")
    script.add_argument("--no-editor", action="store_true",
                        help="do not open a window; capture, save, print the "
                             "path, and exit")

    scroll = parser.add_argument_group("scroll", "options for scroll mode")
    scroll.add_argument("--auto", action="store_true",
                        help="auto-scroll via the RemoteDesktop portal "
                             "(experimental; falls back to manual if denied)")

    daemon = parser.add_argument_group(
        "daemon", "options for the GlobalShortcuts hotkey daemon")
    daemon.add_argument("--shortcut", metavar="TRIGGER",
                        help="portal trigger for region capture "
                             "(default CTRL+Print), e.g. CTRL+Print")
    daemon.add_argument("--bind-once", action="store_true",
                        help="bind the shortcuts and exit (test the binding)")

    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    return parser


def _validate(parser: argparse.ArgumentParser, args) -> None:
    """Cross-argument validation shared by all modes."""
    scripting = args.region or args.output or args.no_editor
    if scripting and args.mode not in CAPTURE_MODES:
        parser.error("--region/--output/--no-editor only apply to the "
                     "'gui' and 'full' capture modes")
    if args.region is not None:
        try:
            args.region = parse_region(args.region)
        except ValueError as e:
            parser.error(str(e))
    if args.output:
        args.output = os.path.abspath(os.path.expanduser(args.output))

    if getattr(args, "auto", False) and args.mode != "scroll":
        parser.error("--auto only applies to the 'scroll' mode")

    if (args.shortcut or args.bind_once) and args.mode != "daemon":
        parser.error("--shortcut/--bind-once only apply to the 'daemon' mode")
    if args.shortcut is not None:
        from .hotkey import valid_trigger
        if not valid_trigger(args.shortcut):
            parser.error(f"invalid shortcut trigger: {args.shortcut!r} "
                         "(expected e.g. CTRL+Print or SHIFT+CTRL+F12)")


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.mode == "diagnose":
        from .diagnostics import print_diagnostics
        return print_diagnostics()

    if args.mode == "edit":
        if not args.file:
            parser.error("edit mode needs an image file: "
                         "wayland-feather-shot edit FILE")
        args.file = os.path.abspath(os.path.expanduser(args.file))
        if not os.path.isfile(args.file):
            parser.error(f"no such file: {args.file}")
    elif args.file:
        parser.error(f"unexpected argument {args.file!r} "
                     "(a FILE is only valid in edit mode)")

    _validate(parser, args)

    try:
        from .app import run
    except ImportError as e:
        print(f"wayland-feather-shot: cannot load the GTK stack: {e}\n"
              "Run `wayland-feather-shot diagnose` to see what is missing "
              "(usually python3-gi / GTK 4 / pycairo).", file=sys.stderr)
        return EXIT_ERROR
    return run(args)
