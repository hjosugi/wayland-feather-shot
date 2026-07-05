"""Best-effort GlobalShortcuts portal daemon.

The default trigger is CTRL+Print.  If a compositor does not implement the
GlobalShortcuts portal, users can bind the same command in their desktop
keyboard settings:

    wayland-feather-shot capture --target area
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .. import DEFAULT_SHORTCUT
from ..capture.portal import PORTAL_BUS, PORTAL_PATH, PortalClient, PortalUnavailable

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except Exception as exc:  # pragma: no cover - Linux desktop runtime specific
    Gio = GLib = None
    _GI_IMPORT_ERROR = exc
else:  # pragma: no cover
    _GI_IMPORT_ERROR = None


GLOBAL_SHORTCUTS_IFACE = "org.freedesktop.portal.GlobalShortcuts"


class GlobalShortcutDaemon:
    def __init__(self, shortcut: str = DEFAULT_SHORTCUT, command: list[str] | None = None):
        if _GI_IMPORT_ERROR is not None:
            raise PortalUnavailable("PyGObject/Gio is not available") from _GI_IMPORT_ERROR
        self.shortcut = shortcut
        self.command = command or [sys.executable, "-m", "wayland_feather_shot", "capture", "--target", "area"]
        self.client = PortalClient()
        self.proxy = self.client.proxy(GLOBAL_SHORTCUTS_IFACE)
        self.session_handle: str | None = None

    def request(self, method: str, params) -> dict[str, Any]:
        result = self.proxy.call_sync(method, params, Gio.DBusCallFlags.NONE, -1, None)
        handle = result.unpack()[0]
        response = self.client.wait_for_request(handle)
        if not response.ok:
            raise PortalUnavailable(f"{method} failed with response code {response.response}")
        return response.results

    def create_session(self) -> str:
        token = f"wfs_{int(time.time() * 1000)}"
        options = {
            "handle_token": GLib.Variant("s", token),
            "session_handle_token": GLib.Variant("s", f"session_{token}"),
        }
        results = self.request("CreateSession", GLib.Variant("(a{sv})", (options,)))
        value = results.get("session_handle")
        if hasattr(value, "unpack"):
            value = value.unpack()
        if not value:
            raise PortalUnavailable("GlobalShortcuts portal did not return session_handle")
        self.session_handle = str(value)
        return self.session_handle

    def bind_shortcuts(self) -> None:
        if not self.session_handle:
            raise PortalUnavailable("session must be created before binding shortcuts")
        shortcuts = [
            (
                "capture-area",
                {
                    "description": GLib.Variant("s", "Capture an area with Wayland Feather Shot"),
                    "preferred_trigger": GLib.Variant("s", self.shortcut),
                },
            )
        ]
        options = {"handle_token": GLib.Variant("s", f"bind_{int(time.time() * 1000)}")}
        self.request(
            "BindShortcuts",
            GLib.Variant("(oa(sa{sv})sa{sv})", (self.session_handle, shortcuts, "", options)),
        )

    def listen(self) -> None:
        if not self.session_handle:
            raise PortalUnavailable("session must be created before listening")
        loop = GLib.MainLoop()

        def on_activated(connection, sender_name, object_path, interface_name, signal_name, parameters, user_data):
            session_handle, shortcut_id, timestamp, options = parameters.unpack()
            if str(session_handle) == self.session_handle and str(shortcut_id) == "capture-area":
                subprocess.Popen(self.command, start_new_session=True)

        self.client.bus.signal_subscribe(
            PORTAL_BUS,
            GLOBAL_SHORTCUTS_IFACE,
            "Activated",
            PORTAL_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            on_activated,
            None,
        )
        print(f"Wayland Feather Shot shortcut daemon listening for {self.shortcut}")
        loop.run()

    def run(self, bind_only: bool = False) -> None:
        self.create_session()
        self.bind_shortcuts()
        if bind_only:
            print(f"Bound preferred shortcut: {self.shortcut}")
            return
        self.listen()


def run_daemon(args: argparse.Namespace) -> int:
    shortcut = args.shortcut or DEFAULT_SHORTCUT
    try:
        daemon = GlobalShortcutDaemon(shortcut=shortcut)
        daemon.run(bind_only=args.bind_once)
        return 0
    except Exception as exc:
        print("Global shortcut portal is not available or rejected the binding.", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print("Fallback command to bind in your desktop settings:", file=sys.stderr)
        print("  wayland-feather-shot capture --target area", file=sys.stderr)
        return 2
