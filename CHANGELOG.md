# Changelog

## 0.2.0 (2026-07-05)

Merged the two development lines of the project into one app: the richer
GTK runtime (overlay, editor, i18n, PipeWire scroll capture) stays, and the
project hygiene of the alternate implementation was adopted on top.

- New `edit FILE` mode: open an existing image straight in the editor
- New `diagnose` mode: environment checks for GTK, pycairo, wl-clipboard,
  GStreamer/PipeWire and the portal interfaces — works even when GTK
  itself is broken, and every GTK-dependent mode now points to it instead
  of crashing with a traceback
- Default save directory now honours localized XDG user dirs
  (e.g. `~/画像/Screenshots`); `save_dir` in config.json overrides it
- `pyproject.toml`: `pip install .` now works (console script included);
  numpy available as the `fast` extra
- Proper reverse-DNS app ID `io.github.hjosugi.WaylandFeatherShot`
  (desktop entries and icon renamed to match; install.sh/uninstall.sh
  clean up files installed under the 0.1.0 names)
- Added `docs/ARCHITECTURE.md`, `docs/SECURITY.md` and GitHub issue
  templates with local-only safety checkboxes
- The backlog moved from ISSUES.md to the GitHub issue tracker
- Removed the duplicate `wayland-feather-shot(1)/` source tree and the
  committed `dist/` build artifact

## 0.1.0 (2026-07-06)

First release.

- Portal-based capture (works on GNOME, KDE, Hyprland, Sway, …)
- Flameshot-style fullscreen overlay: drag-select with resize handles,
  in-place annotation toolbar attached to the selection
- Tools: pen, line, arrow, rectangle, ellipse, highlighter, text,
  **blur**, pixelate, auto-numbered markers, crop (editor window)
- Ctrl+S save / Ctrl+Shift+S save-as / Ctrl+C copy / Ctrl+Z undo
- Scrolling capture: ScreenCast portal + PipeWire recording with
  automatic frame keeping and overlap-detected vertical stitching
- English / Japanese UI (follows LANG, override with WFS_LANG)
- Default hotkey Ctrl+Print (GlobalShortcuts portal daemon + setup script)
- 100% local: no upload, no accounts, no telemetry, no network code
