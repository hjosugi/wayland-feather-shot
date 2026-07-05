# Issues

Known limitations of v0.1.0 and the improvement backlog, written as
ready-to-file GitHub issues. 実装しきれなかった点と今後のブラッシュアップ項目。

Legend: `bug` = wrong/fragile behavior, `limitation` = Wayland/portal
constraint we work around by design, `enhancement` = future polish.

---

## #1 GlobalShortcuts portal is not available on every desktop
`limitation` `hotkeys`

`wayland-feather-shot daemon` binds Ctrl+Print through
`org.freedesktop.portal.GlobalShortcuts`. KDE Plasma and GNOME 46+ implement
it; wlroots-based desktops (Sway, older Hyprland setups without XDPH
shortcuts support) generally do not. There is **no** portable way for a
Wayland client to grab a global key by itself — that's a compositor
decision, not an app bug.

**Workaround (shipped):** `scripts/setup-hotkey.sh` registers a native
desktop shortcut (automatic on GNOME, snippets for Hyprland/Sway/KDE).

**Done when:** daemon falls back cleanly everywhere and the README table
lists per-desktop status.

---

## #2 Multi-monitor: selection happens on the combined virtual screen
`limitation` `ui`

The Screenshot portal returns one image spanning all monitors. The overlay
fullscreens on the *current* monitor and scales that combined image to fit,
so with very different monitor geometries the selection UI feels small and
mixed-DPI setups may show slight softness (the saved pixels are still the
original, unscaled ones — only the preview is scaled).

**Ideas:** per-monitor overlay windows fed by cropping the combined image
using GdkMonitor geometry; snap selection to monitor edges.

---

## #3 Scrolling capture cannot auto-scroll the target window
`limitation` `scroll-capture`

Wayland apps cannot read another window's off-screen content, and synthetic
input needs the RemoteDesktop portal (permission dialog every session, uneven
compositor support). So scroll mode records while **the user** scrolls and
stitches the pauses. This is intentional for v0.1.

**Enhancement:** optional auto-scroll via the RemoteDesktop/EIS portal where
available, with the manual mode as fallback.

---

## #4 Scroll stitching assumptions
`bug` `scroll-capture`

The stitcher assumes: vertical, top-to-bottom scrolling; content that doesn't
animate while you pause; a scroll step smaller than ~85% of the viewport.
Known failure modes:

- horizontal scrolling: unsupported (frames are dropped)
- parallax/animated backgrounds, videos, blinking carets: can misalign or
  duplicate a strip
- elastic "rubber-band" overshoot at page ends: pause until it settles
- windows moved/resized mid-recording: restart the capture

Auto-detected sticky headers/footers can also miss translucent toolbars —
set `scroll_top_margin`/`scroll_bottom_margin` in the config for those.

---

## #5 Clipboard copy without wl-clipboard dies with the window
`limitation` `clipboard`

Wayland clipboards are owned by a living client. With `wl-copy` installed we
hand the data to its forked holder process and can exit immediately; without
it we must keep the overlay/editor open until the user pastes (the UI says
so). Bundling a tiny holder process of our own would remove the dependency.

---

## #6 Blur/pixelate operate on the original pixels only
`enhancement` `editor`

`Obscure` samples the *base* image, so blurring over an arrow you drew leaves
the arrow crisp. Flameshot behaves the same way in most paths, but a
"flatten & blur composite" mode would be nicer for redacting annotations.

---

## #7 Text tool is single-line, fixed font
`enhancement` `editor`

The popover entry commits one line of Sans Bold at the configured size.
Wanted: multi-line editing, font picker, outline/background chip for
readability on busy screenshots, drag-to-reposition existing text.

---

## #8 No shape move/edit after commit
`enhancement` `editor`

Committed shapes can only be undone, not selected/moved/recolored later.
Needs hit-testing + a select tool; the immutable-shape model
(`translate()` copies) was designed so this can be added cleanly.

---

## #9 Fractional scaling produces non-1:1 preview
`limitation` `hidpi`

With fractional scaling (e.g. 125%), the portal returns buffer pixels while
GTK works in logical pixels; the overlay preview is scaled accordingly.
Saved images are always the full-resolution buffer. Cursor-position hairline
accuracy under fractional scaling needs a per-monitor scale-factor pass.

---

## #10 Window-capture mode is indirect
`enhancement` `capture`

`gui`/`full` capture the whole screen (interactive portal mode lets some
desktops pick a window, but the flow varies). A first-class
`wayland-feather-shot window` mode using ScreenCast window selection +
single-frame grab would make it uniform on all desktops.

---

## #11 Packaging: Flatpak / AUR / deb / rpm
`enhancement` `packaging`

v0.1 ships `install.sh`. Backlog: Flatpak manifest (portals make sandboxing
natural; **no** network permission on purpose), AUR `PKGBUILD`, deb/rpm
specs, `pyproject.toml` for pip installs.

---

## #12 No pin-to-screen
`enhancement` `ui`

Flameshot's "pin" floats a capture above all windows. On Wayland,
always-on-top isn't universally available to regular clients; a plain
frameless window (compositor decides stacking) would cover most uses.

---

## #13 Pure-Python stitching is slow without numpy
`limitation` `performance`

Without numpy, stitching ~30 frames of a 4K capture takes several seconds
(sampled pure-Python path). numpy is optional-but-recommended; consider a
tiny C extension or making numpy a hard dependency.

---

## #14 Localization beyond en/ja
`enhancement` `i18n`

Strings go through a small dict-based `_()`; migrating to gettext (`.po`)
would open the door to more languages. UI follows `LANG`, override with
`WFS_LANG`.

---

## #15 More capture goodies (brush-up backlog)
`enhancement`

- capture history / recent screenshots gallery
- OCR of the selection (tesseract, local-only)
- QR decode of the selection (zbar, local-only)
- annotation: step-arrow (numbered arrows), speech bubbles, sticker emoji
- export: WebP/AVIF toggle in the save dialog, "copy as file path"
- CLI: `--region x,y,w,h`, `--output PATH`, exit codes for scripting
- GIF/short video capture of a region (PipeWire already provides frames)
- settings UI (currently JSON only)
- Wayland cursor-shape hints per resize handle on the selection border
