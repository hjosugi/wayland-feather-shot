"""GTK theme helpers used by the application chrome."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402


_STYLE_PROVIDERS = []
_STYLE_DISPLAY_IDS = set()


def _read_portal_color_scheme() -> int | None:
    """Return the xdg-desktop-portal appearance color-scheme value.

    Values are 0=no preference, 1=prefer dark, 2=prefer light. Any failure is
    treated as unknown; GTK's own theme resolution remains the fallback.
    """
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = bus.call_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            "Read",
            GLib.Variant(
                "(ss)",
                ("org.freedesktop.appearance", "color-scheme"),
            ),
            GLib.VariantType.new("(v)"),
            Gio.DBusCallFlags.NONE,
            250,
            None,
        )
        value = result.unpack()[0]
        if isinstance(value, GLib.Variant):
            value = value.unpack()
        return int(value)
    except Exception:
        return None


def apply_system_color_scheme() -> None:
    """Sync GTK's dark hint with the desktop portal when available."""
    settings = Gtk.Settings.get_default()
    if settings is None:
        return
    scheme = _read_portal_color_scheme()
    if scheme not in (1, 2):
        return
    try:
        settings.set_property("gtk-application-prefer-dark-theme", scheme == 1)
    except Exception:
        pass


def install_custom_css() -> None:
    """Install high-contrast CSS for Feather Shot's custom overlay widgets."""
    display = Gdk.Display.get_default()
    if display is None:
        return

    display_id = id(display)
    if display_id in _STYLE_DISPLAY_IDS:
        return

    css = b"""
    .wfs-bar {
        padding: 4px;
        border-radius: 22px;
        background-color: rgba(17, 24, 39, 0.88);
        border: 1px solid rgba(255, 255, 255, 0.30);
    }
    .wfs-round {
        border-radius: 999px;
        padding: 6px 10px;
        background-color: #f8fafc;
        color: #111827;
        border: 1px solid rgba(15, 23, 42, 0.28);
        font-weight: bold;
    }
    .wfs-round:hover {
        background-color: #ffffff;
        color: #111827;
    }
    .wfs-round:checked {
        background-color: #2563eb;
        color: #ffffff;
        border-color: rgba(191, 219, 254, 0.95);
    }
    .wfs-round:disabled {
        background-color: #e5e7eb;
        color: #6b7280;
    }
    .wfs-toast {
        background-color: rgba(17, 24, 39, 0.96);
        color: #ffffff;
        border: 1px solid rgba(255, 255, 255, 0.24);
        border-radius: 9px;
        padding: 8px 18px;
    }
    .wfs-pin {
        border: 1px solid rgba(255, 255, 255, 0.85);
    }
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _STYLE_PROVIDERS.append(provider)
    _STYLE_DISPLAY_IDS.add(display_id)
