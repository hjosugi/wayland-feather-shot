# Architecture

One GTK 4 / PyGObject / cairo application. Everything screen-related goes
through xdg-desktop-portal; there are no X11 fallbacks and no
compositor-private protocols.

```text
src/wayland_feather_shot/
  cli.py                 argument parsing; import-light so `diagnose` and
                         `--help` work even when GTK is missing
  app.py                 Gtk.Application, mode dispatch (gui/full/scroll/edit/daemon)
  portal.py              async portal Request/Response helpers:
                         Screenshot, ScreenCast (+ PipeWire fd), GlobalShortcuts
  select_overlay.py      Flameshot-style fullscreen overlay: drag selection,
                         resize handles, floating annotation toolbar
  editor/                full editor window (canvas, tools, crop)
  scrollcap/recorder.py  ScreenCast + GStreamer/PipeWire recording,
                         damage-driven frame keeping
  scrollcap/stitcher.py  GUI-free vertical stitcher (pure Python, optional
                         numpy fast path, sticky header/footer detection)
  save.py                PNG/JPEG/WebP save + clipboard (wl-copy preferred so
                         the copy survives the app; GDK clipboard fallback)
  settings.py            ~/.config/wayland-feather-shot/config.json
  paths.py               XDG helpers (localized Pictures dir, e.g. ~/画像)
  diagnostics.py         `diagnose` runtime checks, import-light
  i18n.py                dict-based English/Japanese strings (LANG / WFS_LANG)
```

## Capture flow

1. `portal.Portal.screenshot()` calls `org.freedesktop.portal.Screenshot`
   (non-interactive first, portal-interactive retry if refused).
2. `gui` mode freezes that image under `select_overlay.OverlayWindow`;
   annotation happens directly on the selection. `full` and `edit` skip the
   overlay and open `editor.window.EditorWindow`.
3. Saving/copying goes through `save.py`; the portal temp file is deleted.

## Scrolling capture

`scrollcap.recorder` opens a ScreenCast session, receives frames over
PipeWire while *the user* scrolls, keeps one frame per pause, and feeds raw
RGBA buffers to `scrollcap.stitcher`, which aligns overlap strips and appends
only newly revealed rows. The stitcher is deliberately GUI-free and unit
tested (`tests/test_stitcher.py`).

## Shortcuts

`app.run_daemon()` binds Ctrl+Print (region), Ctrl+Shift+Print (scroll) and
Shift+Ctrl+F12 (full) through `org.freedesktop.portal.GlobalShortcuts` where
the desktop implements it; `scripts/setup-hotkey.sh` covers the rest with
native desktop shortcuts.

## Design rules

- portal-first, Wayland-first; never bypass the compositor security model
- no network code of any kind (see docs/SECURITY.md)
- heavy pixel work stays out of the GTK main loop where possible
- stitching/diagnostics stay importable without GTK for tests and broken
  environments
