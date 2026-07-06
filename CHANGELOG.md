# Changelog

## 0.4.0 (2026-07-06)

Reliability and reach (GitHub issues #2, #5, #15).

Global shortcuts (#5)
- **Reliable Ctrl+Print**: the capture spawn now inherits the full session
  environment and fixes PYTHONPATH so it launches in any install layout, and
  logs what it runs — no more silent "I pressed the key and nothing happened".
- **Desktop-aware setup**: `diagnose` detects your desktop (GNOME/KDE/Hyprland/
  Sway/other) and prints the exact Ctrl+Print binding steps; the daemon logs
  activations and, if the portal can't bind, prints the native-binding steps
  and exits cleanly. New `daemon --shortcut TRIGGER` and `--bind-once`.
- `setup-hotkey.sh` is idempotent and detects Hyprland/Sway; README has a
  per-desktop status table and a troubleshooting flow.

Capture
- **`window` mode** (#2): pick a window via the portal's own picker — uniform
  across desktops without the unreliable version-3 `target` key.

Localization (#15)
- **gettext backend**: any language via a `.mo` catalog, with the built-in
  Japanese table as the guaranteed fallback (en/ja unchanged). `WFS_LANG`
  accepts any code; `scripts/gen-po.py` produces the `.pot`/`.po` and compiles
  the shipped `ja.mo`. See `po/README.md`.

## 0.3.0 (2026-07-06)

Issue backlog work (GitHub issues #4, #7, #8, #9, #10, #12, #13, #14; part
of #16).

Editor
- **Select tool (V)**: click to select the topmost shape, drag to move it,
  Delete/Backspace to remove it, and change colour/width/font to restyle the
  selection — committed shapes are no longer immutable (#10).
- **Multi-line text** with a contrasting readability outline and an optional
  background chip, plus a font-family/size picker in the header (#9).
- **Flatten & blur** toggle: blur/pixelate can cover annotations, not just the
  photo, by flattening the stack first (#8).
- **Pin to screen** (Ctrl+P / toolbar): float the capture in a frameless,
  draggable window; Esc or middle-click closes, Ctrl+C re-copies (#13).

Capture / scripting
- **Scriptable capture**: `--region X,Y,W,H`, `--output/-o PATH`,
  `--no-editor`, and stable exit codes (0/1/2/130) for `gui`/`full` (part of
  #16).

Scrolling capture
- **Faster stitching**: coarse-to-fine shift search speeds up the pure-Python
  (no-numpy) path on large captures (#14).
- **More robust stitching**: overshoot / scroll-back and horizontal-scroll
  frames are dropped instead of duplicating a strip, and the editor shows a
  warning listing skipped frames (#4).

Clipboard
- **Bundled clipboard holder** so Ctrl+C survives closing the window without
  wl-clipboard installed (#7).

Packaging
- Flatpak manifest (no network permission), AppStream metainfo, AUR PKGBUILD
  (#12).

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
