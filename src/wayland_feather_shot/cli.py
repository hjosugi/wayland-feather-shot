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

MODES = ["gui", "full", "scroll", "edit", "daemon", "diagnose"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wayland-feather-shot",
        description="Flameshot-style screenshot tool built Wayland-first: "
                    "portal capture, in-place annotation (pen, arrow, blur, "
                    "…), scrolling capture. 100% local — no upload, no "
                    "network code.")
    parser.add_argument("mode", nargs="?", default="gui", choices=MODES,
                        help="gui: region capture (default) / full: whole "
                             "screen / scroll: scrolling capture / edit: "
                             "open an existing image in the editor / "
                             "daemon: GlobalShortcuts-portal hotkey daemon "
                             "/ diagnose: print runtime environment checks")
    parser.add_argument("file", nargs="?", metavar="FILE",
                        help="image to open (edit mode only)")
    parser.add_argument("-d", "--delay", type=float, default=0.0,
                        metavar="SEC", help="delay before capturing")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    return parser


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

    try:
        from .app import run
    except ImportError as e:
        print(f"wayland-feather-shot: cannot load the GTK stack: {e}\n"
              "Run `wayland-feather-shot diagnose` to see what is missing "
              "(usually python3-gi / GTK 4 / pycairo).", file=sys.stderr)
        return 1
    return run(args)
