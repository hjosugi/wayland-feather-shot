"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import DEFAULT_SHORTCUT
from .capture.portal import PortalScreenshot
from .diagnostics import print_diagnostics
from .editor.window import run_editor
from .scrollcap.session import run_scroll_capture
from .shortcuts.daemon import run_daemon


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wayland-feather-shot",
        description="Local-only Flameshot-like screenshot editor for Linux Wayland.",
    )
    sub = parser.add_subparsers(dest="command")

    capture = sub.add_parser("capture", help="capture a screenshot through xdg-desktop-portal")
    capture.add_argument("--target", choices=["area", "screen", "window", "active-window"], default="area")
    capture.add_argument("--no-editor", action="store_true", help="print captured file path instead of opening the editor")
    capture.add_argument("--non-interactive", action="store_true", help="ask portal to skip customization when supported")

    edit = sub.add_parser("edit", help="open an existing image in the editor")
    edit.add_argument("file", type=Path)

    scroll = sub.add_parser("scroll", help="user-assisted scroll capture and vertical stitching")
    scroll.add_argument("--frames", type=int, default=4, help="number of visible frames to capture")
    scroll.add_argument("--delay", type=float, default=2.5, help="seconds before each next frame capture")
    scroll.add_argument("--crop", help="fixed crop as x,y,width,height; omit to select after first screen capture")
    scroll.add_argument("--output", help="output PNG path")
    scroll.add_argument("--no-editor", action="store_true", help="do not open stitched image in editor")

    daemon = sub.add_parser("daemon", help="listen for the default global shortcut through the portal")
    daemon.add_argument("--shortcut", default=DEFAULT_SHORTCUT, help="XDG shortcut trigger, default CTRL+Print")
    daemon.add_argument("--bind-once", action="store_true", help="bind the shortcut and exit")

    sub.add_parser("diagnose", help="print runtime checks")
    return parser


def run_capture(args: argparse.Namespace) -> int:
    portal = PortalScreenshot()
    target = "active" if args.target == "active-window" else args.target
    path = portal.capture(target=target, interactive=not args.non_interactive)
    if args.no_editor:
        print(path)
        return 0
    return run_editor(path)


def run_edit(args: argparse.Namespace) -> int:
    path = Path(args.file).expanduser()
    if not path.exists():
        raise FileNotFoundError(path)
    return run_editor(path)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(["capture", "--target", "area"])

    try:
        if args.command == "capture":
            return run_capture(args)
        if args.command == "edit":
            return run_edit(args)
        if args.command == "scroll":
            output = run_scroll_capture(args)
            print(output)
            if args.no_editor:
                return 0
            return run_editor(output)
        if args.command == "daemon":
            return run_daemon(args)
        if args.command == "diagnose":
            return print_diagnostics()
        parser.print_help()
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"wayland-feather-shot: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
