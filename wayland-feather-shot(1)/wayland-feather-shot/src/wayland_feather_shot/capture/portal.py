"""XDG Desktop Portal screenshot integration.

The code talks to org.freedesktop.portal.Desktop on the session bus.  It does
not use X11 APIs, root windows, or any cloud service.
"""

from __future__ import annotations

import enum
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except Exception as exc:  # pragma: no cover - depends on Linux desktop runtime
    gi = None
    Gio = None
    GLib = None
    _GI_IMPORT_ERROR = exc
else:  # pragma: no cover - depends on Linux desktop runtime
    _GI_IMPORT_ERROR = None


PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT_IFACE = "org.freedesktop.portal.Screenshot"
REQUEST_IFACE = "org.freedesktop.portal.Request"


class PortalUnavailable(RuntimeError):
    """Raised when the desktop portal cannot be reached."""


class ScreenshotTarget(enum.IntEnum):
    SCREEN = 1
    WINDOW = 2
    AREA = 4
    ACTIVE_WINDOW = 8


TARGET_ALIASES = {
    "screen": ScreenshotTarget.SCREEN,
    "monitor": ScreenshotTarget.SCREEN,
    "window": ScreenshotTarget.WINDOW,
    "area": ScreenshotTarget.AREA,
    "region": ScreenshotTarget.AREA,
    "active": ScreenshotTarget.ACTIVE_WINDOW,
    "active-window": ScreenshotTarget.ACTIVE_WINDOW,
}


@dataclass(slots=True)
class PortalResponse:
    response: int
    results: dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.response == 0

    @property
    def cancelled(self) -> bool:
        return self.response == 1


def ensure_gio() -> None:
    if _GI_IMPORT_ERROR is not None:
        raise PortalUnavailable(
            "PyGObject/Gio is not available. Install python3-gi and GTK4 introspection packages."
        ) from _GI_IMPORT_ERROR


def file_uri_to_path(uri: str) -> Path:
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme == "file":
        return Path(urllib.parse.unquote(parsed.path))
    if not parsed.scheme:
        return Path(uri)
    # Documents portal may still provide a file-like path. Return the raw URI as a
    # Path-like string only as a last resort so the caller can show a clear error.
    raise PortalUnavailable(f"Unsupported screenshot URI from portal: {uri}")


class PortalClient:
    """Small synchronous helper around request/response style portal methods."""

    def __init__(self) -> None:
        ensure_gio()
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def proxy(self, interface_name: str):
        return Gio.DBusProxy.new_sync(
            self.bus,
            Gio.DBusProxyFlags.NONE,
            None,
            PORTAL_BUS,
            PORTAL_PATH,
            interface_name,
            None,
        )

    @staticmethod
    def _token(prefix: str) -> str:
        return f"{prefix}_{int(time.time() * 1000)}"

    def wait_for_request(self, handle: str, timeout_ms: int = 300_000) -> PortalResponse:
        loop = GLib.MainLoop()
        box: dict[str, Any] = {}

        def on_response(connection, sender_name, object_path, interface_name, signal_name, parameters, user_data):
            response, results = parameters.unpack()
            box["response"] = int(response)
            box["results"] = dict(results)
            loop.quit()

        sub_id = self.bus.signal_subscribe(
            PORTAL_BUS,
            REQUEST_IFACE,
            "Response",
            handle,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
            None,
        )

        def on_timeout():
            box["error"] = TimeoutError("Timed out waiting for portal response")
            loop.quit()
            return False

        timeout_id = GLib.timeout_add(timeout_ms, on_timeout)
        try:
            loop.run()
        finally:
            self.bus.signal_unsubscribe(sub_id)
            try:
                GLib.source_remove(timeout_id)
            except Exception:
                pass

        if "error" in box:
            raise PortalUnavailable(str(box["error"]))
        return PortalResponse(response=box.get("response", 2), results=box.get("results", {}))


class PortalScreenshot:
    """Screenshot capture through org.freedesktop.portal.Screenshot."""

    def __init__(self) -> None:
        self.client = PortalClient()
        self.proxy = self.client.proxy(SCREENSHOT_IFACE)

    def capture(self, target: str | ScreenshotTarget = "area", interactive: bool = True) -> Path:
        target_enum = target if isinstance(target, ScreenshotTarget) else TARGET_ALIASES[target]
        try:
            return self._capture_once(target_enum, interactive=interactive, include_target=True)
        except Exception as exc:
            # Older portal implementations may not accept the version-3 target key.
            if "target" not in str(exc).lower() and "invalid" not in str(exc).lower():
                raise
            return self._capture_once(target_enum, interactive=interactive, include_target=False)

    def _capture_once(self, target: ScreenshotTarget, interactive: bool, include_target: bool) -> Path:
        token = self.client._token("screenshot")
        options: dict[str, Any] = {
            "handle_token": GLib.Variant("s", token),
            "interactive": GLib.Variant("b", bool(interactive)),
            "modal": GLib.Variant("b", True),
        }
        if include_target:
            options["target"] = GLib.Variant("u", int(target))

        params = GLib.Variant("(sa{sv})", ("", options))
        try:
            result = self.proxy.call_sync("Screenshot", params, Gio.DBusCallFlags.NONE, -1, None)
        except Exception as exc:  # pragma: no cover - desktop/runtime specific
            raise PortalUnavailable(f"Screenshot portal call failed: {exc}") from exc
        handle = result.unpack()[0]
        response = self.client.wait_for_request(handle)
        if response.cancelled:
            raise PortalUnavailable("Screenshot was cancelled by the user")
        if not response.ok:
            raise PortalUnavailable(f"Screenshot portal returned response code {response.response}")
        uri = response.results.get("uri")
        if hasattr(uri, "unpack"):
            uri = uri.unpack()
        if not uri:
            raise PortalUnavailable("Screenshot portal did not return a URI")
        return file_uri_to_path(str(uri))
