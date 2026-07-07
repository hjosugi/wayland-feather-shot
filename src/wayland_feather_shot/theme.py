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

    # These selectors are deliberately specific (.wfs-bar button.wfs-round) and
    # installed at USER priority so the frozen-overlay toolbar keeps a fixed,
    # high-contrast look no matter which GTK theme the user runs. Adwaita-dark
    # and many third-party themes paint buttons with a background *image*/gradient
    # and set the label colour on the label node, which silently overrode the old
    # low-specificity `.wfs-round` rules — leaving white labels on white pills.
    # Neutralising background-image and pinning both the button and its label
    # colour makes the styling theme-independent.
    css = b"""
    .wfs-bar {
        padding: 5px;
        border-radius: 14px;
        background-color: rgba(17, 24, 39, 0.92);
        border: 1px solid rgba(255, 255, 255, 0.28);
    }
    .wfs-bar button.wfs-round {
        min-width: 0;
        min-height: 30px;
        margin: 0;
        padding: 4px 12px;
        border-radius: 8px;
        background-image: none;
        background-color: #f1f5f9;
        color: #111827;
        border: 1px solid rgba(15, 23, 42, 0.22);
        box-shadow: none;
        text-shadow: none;
        font-weight: bold;
    }
    .wfs-bar button.wfs-round label {
        color: inherit;
    }
    .wfs-bar button.wfs-round:hover {
        background-image: none;
        background-color: #ffffff;
        color: #0b1220;
    }
    .wfs-bar button.wfs-round:checked,
    .wfs-bar button.wfs-round:checked:hover {
        background-image: none;
        background-color: #2563eb;
        color: #ffffff;
        border-color: #1d4ed8;
    }
    .wfs-bar button.wfs-round:checked label {
        color: #ffffff;
    }
    .wfs-bar button.wfs-round:disabled {
        background-image: none;
        background-color: #d7dbe0;
        color: #7b828c;
    }
    .wfs-bar spinbutton {
        background-image: none;
        background-color: #f1f5f9;
        color: #111827;
        border-radius: 8px;
        border: 1px solid rgba(15, 23, 42, 0.22);
        box-shadow: none;
        min-height: 30px;
    }
    .wfs-bar spinbutton text {
        color: #111827;
        background-color: transparent;
        caret-color: #111827;
    }
    .wfs-bar spinbutton button {
        color: #111827;
        background-image: none;
        background-color: transparent;
        box-shadow: none;
        border: none;
    }
    .wfs-bar spinbutton button:hover {
        background-color: rgba(15, 23, 42, 0.10);
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
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
    )
    _STYLE_PROVIDERS.append(provider)
    _STYLE_DISPLAY_IDS.add(display_id)
