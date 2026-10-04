"""GTK theme helpers used by the application chrome."""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402


_STYLE_PROVIDERS = []
_STYLE_DISPLAY_IDS = set()


def register_bundled_icons() -> None:
    """Make bundled symbolic tool icons available before windows are built."""
    display = Gdk.Display.get_default()
    if display is None:
        return
    icon_theme = Gtk.IconTheme.get_for_display(display)
    icon_path = str(Path(__file__).resolve().parent.parent / "icons")
    if icon_path not in icon_theme.get_search_path():
        icon_theme.add_search_path(icon_path)


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
    # and many third-party themes paint buttons with a background
    # *image*/gradient and set the label colour on the label node, which
    # silently overrode the old low-specificity `.wfs-round` rules — leaving
    # white labels on white pills. Neutralising background-image and pinning
    # both the button and its label colour makes the styling theme-independent.
    css = b"""
    .wfs-bar {
        padding: 5px;
        border-radius: 14px;
        background-color: rgba(17, 24, 39, 0.92);
        border: 1px solid rgba(255, 255, 255, 0.28);
    }
    .wfs-bar button.wfs-round,
    .wfs-popover button.wfs-round {
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
    .wfs-bar button.wfs-round label,
    .wfs-popover button.wfs-round label {
        color: inherit;
    }
    .wfs-bar button.wfs-round:hover,
    .wfs-popover button.wfs-round:hover {
        background-image: none;
        background-color: #ffffff;
        color: #0b1220;
    }
    .wfs-bar button.wfs-round:checked,
    .wfs-popover button.wfs-round:checked,
    .wfs-bar button.wfs-round:checked:hover,
    .wfs-popover button.wfs-round:checked:hover {
        background-image: none;
        background-color: #2563eb;
        color: #ffffff;
        border-color: #1d4ed8;
    }
    .wfs-bar button.wfs-round:checked label,
    .wfs-popover button.wfs-round:checked label {
        color: #ffffff;
    }
    .wfs-bar button.wfs-round:disabled,
    .wfs-popover button.wfs-round:disabled {
        background-image: none;
        background-color: #d7dbe0;
        color: #7b828c;
    }
    .wfs-bar.wfs-toolbar button.wfs-round {
        min-width: 20px;
        min-height: 20px;
        padding: 6px;
    }
    .wfs-bar.wfs-toolbar button.wfs-round image {
        -gtk-icon-size: 18px;
    }
    .wfs-bar.wfs-toolbar button.wfs-round:focus {
        outline: 2px solid #fbbf24;
        outline-offset: 1px;
    }
    .wfs-bar spinbutton,
    .wfs-popover spinbutton {
        background-image: none;
        background-color: #f1f5f9;
        color: #111827;
        border-radius: 8px;
        border: 1px solid rgba(15, 23, 42, 0.22);
        box-shadow: none;
        min-height: 30px;
    }
    .wfs-bar spinbutton text,
    .wfs-popover spinbutton text {
        color: #111827;
        background-color: transparent;
        caret-color: #111827;
    }
    .wfs-bar spinbutton button,
    .wfs-popover spinbutton button {
        color: #111827;
        background-image: none;
        background-color: transparent;
        box-shadow: none;
        border: none;
    }
    .wfs-bar spinbutton button:hover,
    .wfs-popover spinbutton button:hover {
        background-color: rgba(15, 23, 42, 0.10);
    }
    /* Popovers of the toolbar and the action bar: dark, like the bars. */
    popover.wfs-popover > contents {
        background-color: rgba(17, 24, 39, 0.97);
        color: #ffffff;
        border: 1px solid rgba(255, 255, 255, 0.28);
        border-radius: 12px;
        padding: 8px;
    }
    popover.wfs-popover > arrow {
        background-color: rgba(17, 24, 39, 0.97);
        border: 1px solid rgba(255, 255, 255, 0.28);
    }
    .wfs-popover button.wfs-menu-item {
        background-image: none;
        background-color: transparent;
        color: #ffffff;
        border: none;
        box-shadow: none;
        border-radius: 8px;
        padding: 6px 10px;
    }
    .wfs-popover button.wfs-menu-item:hover {
        background-color: rgba(255, 255, 255, 0.12);
    }
    .wfs-popover dropdown > button,
    .wfs-popover fontbutton > button {
        background-image: none;
        background-color: #f1f5f9;
        color: #111827;
        border: none;
        border-radius: 8px;
        box-shadow: none;
        min-height: 30px;
        padding: 2px 10px;
    }
    .wfs-popover dropdown > button:hover,
    .wfs-popover fontbutton > button:hover {
        background-color: #ffffff;
    }
    .wfs-popover dropdown > button label,
    .wfs-popover fontbutton > button label {
        color: inherit;
    }
    popover.wfs-popover separator.horizontal {
        background-color: rgba(255, 255, 255, 0.18);
        min-height: 1px;
        margin: 2px 6px;
    }
    .wfs-popover label.wfs-caption {
        color: rgba(255, 255, 255, 0.78);
    }
    .wfs-popover button.wfs-emoji {
        font-size: 20px;
        min-width: 36px;
        min-height: 36px;
        padding: 2px;
        border-radius: 8px;
    }
    .wfs-popover button.wfs-emoji:hover {
        background-color: rgba(255, 255, 255, 0.12);
    }
    .wfs-popover button.wfs-chip {
        background-image: none;
        background-color: transparent;
        color: #ffffff;
        border: none;
        box-shadow: none;
        border-radius: 999px;
        min-width: 0;
        min-height: 0;
        padding: 3px;
    }
    .wfs-popover button.wfs-chip:hover {
        background-color: rgba(255, 255, 255, 0.18);
    }
    /* A tool family: the tool's button and its menu arrow, joined. */
    .wfs-bar .wfs-family > button.wfs-round:first-child {
        border-top-right-radius: 0;
        border-bottom-right-radius: 0;
    }
    .wfs-bar .wfs-family > menubutton > button.wfs-round,
    .wfs-bar .wfs-family > menubutton.wfs-round > button {
        border-top-left-radius: 0;
        border-bottom-left-radius: 0;
        border-left: none;
        padding-left: 1px;
        padding-right: 1px;
        min-width: 14px;
    }
    .wfs-bar .wfs-family image {
        -gtk-icon-size: 18px;
    }
    .wfs-bar separator.wfs-sep {
        background-color: rgba(255, 255, 255, 0.25);
        min-width: 1px;
        margin: 6px 3px;
    }
    .wfs-bar menubutton.wfs-style > button {
        padding: 4px 10px;
    }
    .wfs-size-label {
        font-weight: bold;
        min-width: 16px;
    }
    .wfs-toast {
        background-color: rgba(17, 24, 39, 0.96);
        color: #ffffff;
        border: 1px solid rgba(255, 255, 255, 0.24);
        border-radius: 9px;
        padding: 8px 18px;
    }
    .wfs-text-edit {
        background-color: rgba(0, 0, 0, 0);
        background-image: none;
        caret-color: #2f7ff5;
        padding: 0;
    }
    .wfs-text-edit text {
        background-color: rgba(0, 0, 0, 0);
    }
    .wfs-crop-bar {
        background-color: rgba(17, 24, 39, 0.96);
        border: 1px solid rgba(255, 255, 255, 0.24);
        border-radius: 11px;
        padding: 7px 10px;
    }
    .wfs-crop-bar button {
        color: #ffffff;
        background-image: none;
        background-color: rgba(255, 255, 255, 0.10);
        border: 1px solid rgba(255, 255, 255, 0.18);
    }
    .wfs-crop-bar button:checked,
    .wfs-crop-bar button.suggested-action {
        background-color: #2f7ff5;
        border-color: #2f7ff5;
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


_LIVE_TEXT_PROVIDER = None


def _load_live_css(view, css: str) -> None:
    """Replace the in-place text view's sizing CSS. One text is typed at a
    time, so one provider, reloaded per keystroke, serves them all."""
    global _LIVE_TEXT_PROVIDER
    if _LIVE_TEXT_PROVIDER is None:
        _LIVE_TEXT_PROVIDER = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            view.get_display(), _LIVE_TEXT_PROVIDER,
            Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
    if hasattr(_LIVE_TEXT_PROVIDER, "load_from_string"):     # GTK 4.12+
        _LIVE_TEXT_PROVIDER.load_from_string(css)
    else:
        _LIVE_TEXT_PROVIDER.load_from_data(css.encode())


def style_live_bubble(view, rgba, border_px: float, radius_px: float) -> None:
    """Dress the in-place text view as the speech bubble it will become: a
    white body with a border in the annotation colour (the tail is left
    out while typing)."""
    r, g, b = (round(c * 255) for c in rgba[:3])
    a = rgba[3]
    _load_live_css(view, (
        f".wfs-live-bubble {{ background-color: rgba(255, 255, 255, 0.96);"
        f" border: {border_px:.1f}px solid rgba({r}, {g}, {b}, {a:.3f});"
        f" border-radius: {radius_px:.1f}px; }}\n"))
    view.add_css_class("wfs-live-bubble")


def style_live_text(view, style_name: str, rgba, font_px: float) -> None:
    """Dress the in-place text view like the text it will become.

    Pango cannot stroke glyphs, so an outlined text's halo is drawn as a ring
    of CSS text shadows in the same contrasting colour and about the same
    width as the real one; boxed text gets the same dark box behind it.
    """
    r, g, b, a = rgba
    halo = 0 if 0.299 * r + 0.587 * g + 0.114 * b > 0.5 else 255
    colour = f"rgba({halo}, {halo}, {halo}, {a:.3f})"
    radius = max(1.0, max(2.0, font_px * 0.12) / 2)
    d = radius * 0.7
    rings = ", ".join(f"{dx:.2f}px {dy:.2f}px 0 {colour}" for dx, dy in (
        (radius, 0), (-radius, 0), (0, radius), (0, -radius),
        (d, d), (-d, -d), (d, -d), (-d, d)))
    _load_live_css(view, (
        f".wfs-live-outline {{ text-shadow: {rings}; }}\n"
        f".wfs-live-box {{ background-color: rgba(0, 0, 0, 0.45);"
        f" border-radius: {max(2.0, font_px * 0.25):.1f}px; }}\n"))
    for name in ("outline", "box"):
        if style_name == name:
            view.add_css_class(f"wfs-live-{name}")
        else:
            view.remove_css_class(f"wfs-live-{name}")
