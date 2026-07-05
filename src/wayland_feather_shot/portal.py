"""xdg-desktop-portal D-Bus helpers.

Everything capture-related goes through the portal so the app works on any
Wayland compositor with a portal backend (GNOME, KDE, wlroots, Hyprland, ...).
No X11 APIs, no compositor-private protocols.
"""

from __future__ import annotations

import os
import secrets
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
IFACE_REQUEST = "org.freedesktop.portal.Request"
IFACE_SESSION = "org.freedesktop.portal.Session"
IFACE_SCREENSHOT = "org.freedesktop.portal.Screenshot"
IFACE_SCREENCAST = "org.freedesktop.portal.ScreenCast"
IFACE_SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"


class PortalError(Exception):
    pass


def uri_to_path(uri: str) -> str:
    return unquote(urlparse(uri).path)


def cleanup_portal_file(path: str) -> None:
    """Delete the temp file the portal handed us — but only if it clearly
    lives in a temp/cache location, never a real user directory."""
    for marker in ("/tmp/", "/.cache/", "/run/", "/var/tmp/"):
        if marker in path:
            try:
                os.remove(path)
            except OSError:
                pass
            return


class Portal:
    """Thin wrapper implementing the portal Request/Response dance."""

    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        if self.bus is None:
            raise PortalError("Cannot connect to the session D-Bus bus")
        unique = self.bus.get_unique_name() or ":0.0"
        self._sender_token = unique[1:].replace(".", "_")

    # -- low level ---------------------------------------------------------

    def _token(self) -> str:
        return "wfs" + secrets.token_hex(8)

    def call(self, iface: str, method: str, params: GLib.Variant,
             reply: str = None) -> GLib.Variant:
        return self.bus.call_sync(
            PORTAL_BUS, PORTAL_PATH, iface, method, params,
            GLib.VariantType(reply) if reply else None,
            Gio.DBusCallFlags.NONE, -1, None)

    def request(self, iface: str, method: str, build_params, options: dict,
                callback) -> None:
        """Portal request helper.

        *build_params(options_variant_dict)* must return the full GLib.Variant
        tuple for the method call.  *callback(response_code, results)* fires
        when the matching Response signal arrives (code 0 = success,
        1 = user cancelled, 2 = error).
        """
        token = self._token()
        opts = dict(options)
        opts["handle_token"] = GLib.Variant("s", token)
        expected = f"{PORTAL_PATH}/request/{self._sender_token}/{token}"
        state = {"id": 0}

        def on_response(_bus, _sender, _path, _iface, _signal, params):
            self.bus.signal_unsubscribe(state["id"])
            code, results = params.unpack()
            callback(code, results)

        def subscribe(path):
            return self.bus.signal_subscribe(
                PORTAL_BUS, IFACE_REQUEST, "Response", path, None,
                Gio.DBusSignalFlags.NONE, on_response)

        state["id"] = subscribe(expected)
        try:
            reply = self.call(iface, method, build_params(opts), "(o)")
        except GLib.Error as e:
            self.bus.signal_unsubscribe(state["id"])
            callback(2, {"error": str(e)})
            return
        handle = reply.unpack()[0]
        if handle != expected:
            # Pre-0.9 portals ignore handle_token; re-subscribe on the real
            # handle (tiny race, but such portals are ancient by now).
            self.bus.signal_unsubscribe(state["id"])
            state["id"] = subscribe(handle)

    def close_session(self, session_handle: str) -> None:
        try:
            self.bus.call_sync(
                PORTAL_BUS, session_handle, IFACE_SESSION, "Close",
                None, None, Gio.DBusCallFlags.NONE, -1, None)
        except GLib.Error:
            pass

    # -- Screenshot --------------------------------------------------------

    def screenshot(self, callback, interactive: bool = False) -> None:
        """Take a full-screen screenshot.  callback(path_or_None, error_msg)."""

        def on_resp(code, results):
            if code == 0 and results.get("uri"):
                callback(uri_to_path(results["uri"]), None)
            elif code == 1:
                callback(None, "cancelled")
            else:
                callback(None, results.get("error") or f"portal response code {code}")

        self.request(
            IFACE_SCREENSHOT, "Screenshot",
            lambda opts: GLib.Variant("(sa{sv})", ("", opts)),
            {"interactive": GLib.Variant("b", interactive)},
            on_resp)


class ScreenCastSession:
    """One ScreenCast portal session: pick a monitor/window, get a PipeWire
    node id + connection fd suitable for `pipewiresrc`."""

    def __init__(self, portal: Portal):
        self.portal = portal
        self.session_handle = None

    def start(self, callback) -> None:
        """callback(node_id, pipewire_fd, error_msg) — node_id None on failure."""

        def fail(msg):
            self.close()
            callback(None, -1, msg)

        def on_created(code, results):
            if code != 0:
                return fail(f"CreateSession failed ({results})")
            self.session_handle = results["session_handle"]
            self.portal.request(
                IFACE_SCREENCAST, "SelectSources",
                lambda opts: GLib.Variant(
                    "(oa{sv})", (self.session_handle, opts)),
                {
                    "types": GLib.Variant("u", 3),      # monitor | window
                    "multiple": GLib.Variant("b", False),
                    "cursor_mode": GLib.Variant("u", 1),  # hidden (clean stitching)
                },
                on_sources)

        def on_sources(code, results):
            if code != 0:
                return fail("SelectSources failed or was cancelled")
            self.portal.request(
                IFACE_SCREENCAST, "Start",
                lambda opts: GLib.Variant(
                    "(osa{sv})", (self.session_handle, "", opts)),
                {},
                on_started)

        def on_started(code, results):
            if code != 0:
                return fail("screen cast not authorized (cancelled?)")
            streams = results.get("streams") or []
            if not streams:
                return fail("portal returned no streams")
            node_id = streams[0][0]
            try:
                fd = self._open_pipewire_fd()
            except GLib.Error as e:
                return fail(f"OpenPipeWireRemote failed: {e}")
            callback(node_id, fd, None)

        self.portal.request(
            IFACE_SCREENCAST, "CreateSession",
            lambda opts: GLib.Variant("(a{sv})", (opts,)),
            {"session_handle_token": GLib.Variant("s", self.portal._token())},
            on_created)

    def _open_pipewire_fd(self) -> int:
        reply, fd_list = self.portal.bus.call_with_unix_fd_list_sync(
            PORTAL_BUS, PORTAL_PATH, IFACE_SCREENCAST, "OpenPipeWireRemote",
            GLib.Variant("(oa{sv})", (self.session_handle, {})),
            GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None)
        index = reply.unpack()[0]
        return fd_list.get(index)

    def close(self) -> None:
        if self.session_handle:
            self.portal.close_session(self.session_handle)
            self.session_handle = None


class GlobalShortcuts:
    """GlobalShortcuts portal binding (used by `wayland-feather-shot daemon`).

    Backend support varies by desktop (KDE Plasma and GNOME 46+ implement it;
    wlroots desktops generally do not yet) — the daemon reports failure and
    the hotkey setup script covers those desktops instead.
    """

    SHORTCUTS = [
        ("capture-region", "Capture a screen region (Feather Shot)", "CTRL+Print"),
        ("capture-full", "Capture the full screen (Feather Shot)", "SHIFT+CTRL+F12"),
        ("capture-scroll", "Scrolling capture (Feather Shot)", "CTRL+SHIFT+Print"),
    ]

    def __init__(self, portal: Portal, on_activated):
        self.portal = portal
        self.on_activated = on_activated
        self.session_handle = None

    def bind(self, callback) -> None:
        """callback(ok, error_msg)"""

        def on_created(code, results):
            if code != 0:
                return callback(False, f"CreateSession failed ({results})")
            self.session_handle = results["session_handle"]
            self.portal.bus.signal_subscribe(
                PORTAL_BUS, IFACE_SHORTCUTS, "Activated", PORTAL_PATH, None,
                Gio.DBusSignalFlags.NONE, self._activated)
            shortcuts = GLib.Variant(
                "a(sa{sv})",
                [(sid, {
                    "description": GLib.Variant("s", desc),
                    "preferred_trigger": GLib.Variant("s", trig),
                }) for sid, desc, trig in self.SHORTCUTS])
            self.portal.request(
                IFACE_SHORTCUTS, "BindShortcuts",
                lambda opts: GLib.Variant.new_tuple(
                    GLib.Variant("o", self.session_handle), shortcuts,
                    GLib.Variant("s", ""), GLib.Variant("a{sv}", opts)),
                {},
                lambda code, results: callback(
                    code == 0, None if code == 0 else f"BindShortcuts failed ({results})"))

        self.portal.request(
            IFACE_SHORTCUTS, "CreateSession",
            lambda opts: GLib.Variant("(a{sv})", (opts,)),
            {"session_handle_token": GLib.Variant("s", self.portal._token())},
            on_created)

    def _activated(self, _bus, _sender, _path, _iface, _signal, params):
        session, shortcut_id, _timestamp, _opts = params.unpack()
        if session == self.session_handle:
            self.on_activated(shortcut_id)
