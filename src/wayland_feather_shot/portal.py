"""xdg-desktop-portal D-Bus helpers.

Everything capture-related goes through the portal so the app works on any
Wayland compositor with a portal backend (GNOME, KDE, wlroots, Hyprland, ...).
No X11 APIs, no compositor-private protocols.
"""

from __future__ import annotations

import os
import secrets
import time
from typing import Optional
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import APP_ID  # noqa: E402

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
IFACE_REQUEST = "org.freedesktop.portal.Request"
IFACE_SESSION = "org.freedesktop.portal.Session"
IFACE_SCREENSHOT = "org.freedesktop.portal.Screenshot"
IFACE_SCREENCAST = "org.freedesktop.portal.ScreenCast"
IFACE_SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"
IFACE_REMOTEDESKTOP = "org.freedesktop.portal.RemoteDesktop"
IFACE_REGISTRY = "org.freedesktop.host.portal.Registry"


class PortalError(Exception):
    pass


def uri_to_path(uri: str) -> str:
    return unquote(urlparse(uri).path)


# -- app id ----------------------------------------------------------------
#
# The portal identifies a client by its D-Bus connection.  Sandboxed apps
# (Flatpak, Snap) are recognised automatically; a process running on the host
# has no app id unless it says so, and the GlobalShortcuts portal refuses to
# open a session without one ("An app id is required").  xdg-desktop-portal
# 1.18+ offers org.freedesktop.host.portal.Registry for exactly this, with two
# rules: Register must be the first portal call on the connection, and a
# desktop entry named <app id>.desktop must exist where the portal can see it.
# GTK talks to the portal (Settings) on the shared session connection as soon
# as it initialises, so the helpers below use a private connection and
# register before anything else touches it.
#
# Only the hotkey daemon registers.  A registered app id also makes the
# Screenshot and ScreenCast portals ask for per-app permission through a
# dialog they cannot show for a client without a window, and the request is
# then denied; the capture path therefore keeps the plain, unregistered
# connection, which the portal treats as a trusted host client as before.

_BUS = {"conn": None, "app_id_error": None}


def register_app_id(bus, app_id: str) -> Optional[str]:
    """Tell the portal which desktop entry this host process belongs to.

    Returns None on success, otherwise the portal's error message.  Failure is
    not fatal: sandboxed apps are identified by the portal itself, older
    portals lack the interface, and every portal except GlobalShortcuts works
    without an app id.
    """
    try:
        bus.call_sync(PORTAL_BUS, PORTAL_PATH, IFACE_REGISTRY, "Register",
                      GLib.Variant("(sa{sv})", (app_id, {})), None,
                      Gio.DBusCallFlags.NONE, 5000, None)
    except GLib.Error as e:
        return e.message
    return None


def _new_private_connection():
    addr = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
    conn = Gio.DBusConnection.new_for_address_sync(
        addr,
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None, None)
    conn.set_exit_on_close(False)
    return conn


def portal_bus():
    """The process-wide portal connection, registered with the app id once."""
    if _BUS["conn"] is None:
        try:
            conn = _new_private_connection()
        except GLib.Error:
            conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        if conn is None:
            raise PortalError("Cannot connect to the session D-Bus bus")
        _BUS["app_id_error"] = register_app_id(conn, APP_ID)
        _BUS["conn"] = conn
    return _BUS["conn"]


def app_id_error() -> Optional[str]:
    """Why the app id could not be registered with the portal, or None."""
    return _BUS["app_id_error"]


def cleanup_portal_file(path: str, since: Optional[float] = None) -> None:
    """Delete the temp file the portal handed us.

    A file under a temp or cache directory is always ours to remove.  Some
    backends write the capture into the Pictures folder or straight into
    $HOME instead (#52); such a file is removed only when *since* (the time
    the request was made) shows it appeared for this very request, so a stale
    path can never cost the user a real picture.
    """
    temp = any(marker in path
               for marker in ("/tmp/", "/.cache/", "/run/", "/var/tmp/"))
    if not temp:
        if since is None:
            return
        try:
            if os.path.getmtime(path) < since - 1.0:
                return
        except OSError:
            return
    try:
        os.remove(path)
    except OSError:
        pass


class Portal:
    """Thin wrapper implementing the portal Request/Response dance."""

    def __init__(self, registered: bool = False):
        """*registered*: use the private connection that carries the app id.
        Needed for GlobalShortcuts, harmful for Screenshot (see above)."""
        if registered:
            self.bus = portal_bus()
        else:
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
        """Take a full-screen screenshot: callback(path_or_None, error_msg)."""

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


class PendingScreenshot:
    """A screenshot request sent before the GTK stack is loaded.

    The portal needs about a second to take the shot. Sending the request
    first and importing GTK while the portal works takes most of our own
    start-up off the time between the key press and the overlay.
    """

    def __init__(self, portal: Portal, interactive: bool = False):
        self.started = time.time()
        self.result = None
        self._waiter = None
        portal.screenshot(self._done, interactive=interactive)

    def _done(self, path, error):
        self.result = (path, error)
        if self._waiter is not None:
            waiter, self._waiter = self._waiter, None
            waiter(path, error)

    def then(self, callback):
        """Call *callback(path, error)* now if the answer is in, else later."""
        if self.result is not None:
            callback(*self.result)
        else:
            self._waiter = callback


class ScreenCastSession:
    """One ScreenCast portal session: pick a monitor/window, get a PipeWire
    node id + connection fd suitable for `pipewiresrc`."""

    def __init__(self, portal: Portal):
        self.portal = portal
        self.session_handle = None

    def start(self, callback) -> None:
        """callback(node_id, pipewire_fd, error); node_id None on failure."""

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
                    # Hidden cursor: it would be stitched into the result.
                    "cursor_mode": GLib.Variant("u", 1),
                },
                on_sources)

        # Response code 1 is the user saying no in the portal's dialog: the
        # capture ends quietly ("cancelled"), not with an error dialog that
        # tells them to check their portal installation.
        def on_sources(code, results):
            if code == 1:
                return fail("cancelled")
            if code != 0:
                return fail("SelectSources failed")
            self.portal.request(
                IFACE_SCREENCAST, "Start",
                lambda opts: GLib.Variant(
                    "(osa{sv})", (self.session_handle, "", opts)),
                {},
                on_started)

        def on_started(code, results):
            if code == 1:
                return fail("cancelled")
            if code != 0:
                return fail("screen cast not authorized")
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
        ("capture-copy", "Copy a screen region to the clipboard (Feather Shot)",
         "CTRL+SHIFT+Print"),
        ("capture-full", "Capture the full screen (Feather Shot)", "SHIFT+CTRL+F12"),
    ]

    def __init__(self, portal: Portal, on_activated, shortcuts=None):
        self.portal = portal
        self.on_activated = on_activated
        self.shortcuts = shortcuts if shortcuts is not None else self.SHORTCUTS
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
                }) for sid, desc, trig in self.shortcuts])
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


class RemoteDesktop:
    """RemoteDesktop portal session used for optional auto-scroll (issue #3).

    Injecting synthetic input on Wayland requires this portal, which shows a
    permission dialog and is not available on every compositor.  It is only
    used opt-in (`scroll --auto`); manual scrolling stays the default and this
    never bypasses the compositor's security model.

    EXPERIMENTAL / untested on hardware — see the on-device checklist (#17).
    """

    def __init__(self, portal: Portal):
        self.portal = portal
        self.session_handle = None

    @staticmethod
    def available(portal: Portal) -> bool:
        """Best-effort check that the RemoteDesktop interface is present."""
        try:
            portal.bus.call_sync(
                PORTAL_BUS, PORTAL_PATH, "org.freedesktop.DBus.Properties",
                "Get", GLib.Variant("(ss)", (IFACE_REMOTEDESKTOP, "version")),
                GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, 2000, None)
            return True
        except GLib.Error:
            return False

    def start(self, callback) -> None:
        """callback(ok, error_msg) once input injection is authorized."""

        def fail(msg):
            self.close()
            callback(False, msg)

        def on_created(code, results):
            if code != 0:
                return fail(f"CreateSession failed ({results})")
            self.session_handle = results["session_handle"]
            self.portal.request(
                IFACE_REMOTEDESKTOP, "SelectDevices",
                lambda opts: GLib.Variant("(oa{sv})",
                                          (self.session_handle, opts)),
                {"types": GLib.Variant("u", 2)},   # 2 = pointer
                on_selected)

        def on_selected(code, results):
            if code != 0:
                return fail("SelectDevices failed or was cancelled")
            self.portal.request(
                IFACE_REMOTEDESKTOP, "Start",
                lambda opts: GLib.Variant("(osa{sv})",
                                          (self.session_handle, "", opts)),
                {},
                on_started)

        def on_started(code, results):
            if code != 0:
                return fail("input injection not authorized (cancelled?)")
            callback(True, None)

        self.portal.request(
            IFACE_REMOTEDESKTOP, "CreateSession",
            lambda opts: GLib.Variant("(a{sv})", (opts,)),
            {"session_handle_token": GLib.Variant("s", self.portal._token())},
            on_created)

    def scroll(self, dy: float) -> bool:
        """Inject a vertical scroll of *dy* pixels (positive = down)."""
        if not self.session_handle:
            return False
        try:
            self.portal.bus.call_sync(
                PORTAL_BUS, PORTAL_PATH, IFACE_REMOTEDESKTOP,
                "NotifyPointerAxis",
                GLib.Variant("(oa{sv}dd)", (self.session_handle, {}, 0.0, dy)),
                None, Gio.DBusCallFlags.NONE, -1, None)
            return True
        except GLib.Error:
            return False

    def close(self) -> None:
        if self.session_handle:
            self.portal.close_session(self.session_handle)
            self.session_handle = None
