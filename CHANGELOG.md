# Changelog

## Unreleased

Auto-scroll follow-up (#3):

- Made optional auto-scroll discoverable from the UI: the scrolling-capture
  window now has an **Auto-scroll (experimental)** checkbox that is enabled
  only when the `org.freedesktop.portal.RemoteDesktop` portal is actually
  present, so the feature is offered exactly where it can work. Manual
  scrolling stays the default everywhere; `scroll --auto` still pre-ticks the
  box from the command line.
- Extracted the auto-scroll stop/stall policy into a pure, unit-tested
  `AutoScrollController` (no GTK), fixing untestable inline logic and clamping
  bad `scroll_auto_delta` / `scroll_auto_steps` config values so a typo can
  never cause a runaway or zero-distance scroll loop.
- `wayland-feather-shot diagnose` now reports the RemoteDesktop portal and a
  derived `scroll --auto` line telling you whether auto-scroll can run
  (needs the RemoteDesktop portal **and** the GStreamer/PipeWire recorder).
- Documented per-desktop auto-scroll behavior in the README.

## 0.7.6 (2026-07-08)

Overlay toolbar readability fix:

- Made the region-overlay annotation toolbar theme-independent. Under
  Adwaita-dark and some third-party GTK themes the tool-button labels
  (Pen, Line, Arrow, …) rendered as white text on white pills and the
  buttons collapsed into ovals, because the theme's button `background-image`
  and label colour overrode the low-specificity custom CSS. The styling now
  uses higher-specificity selectors installed at user priority, neutralizes
  the theme background layers and pins the label colour, so the buttons stay
  high-contrast rounded pills in every theme.
- Restored the intended blue highlight for the active tool and gave the
  line-width spin button a matching high-contrast style on the toolbar.

## 0.7.5 (2026-07-08)

Theme and release cleanup:

- Synced GTK's dark-theme preference with the desktop portal appearance
  setting so app windows and file dialogs follow the same light/dark mode.
- Centralized Feather Shot's custom CSS and strengthened overlay, toast and
  pin-window contrast so toolbar text stays readable across themes.
- Reduced the region-selection dim layer so light-theme content remains easier
  to inspect while choosing a capture area.
- Removed the stale `claude/merge-implementation-versions-20trmn` remote
  branch after confirming its commits were already included in `main`.

## 0.7.4 (2026-07-06)

Release and packaging completion pass for the on-device verification issue
(#17):

- Added a reusable release-asset builder that produces the host-runtime
  AppImage, Python wheel, Python sdist, corrected AUR source bundle and
  `SHA256SUMS` from a tag.
- Updated the GitHub release workflow so future releases publish the same
  asset set automatically instead of creating source-only releases.
- Fixed the committed AUR `PKGBUILD` version metadata and made the release
  builder stamp the real GitHub tag tarball checksum into the uploaded AUR
  package.
- Checked in the AppImage wrapper and documented that it intentionally uses
  `/usr/bin/python3` so distro GTK/PyGObject/portal integrations stay intact.

## 0.7.3 (2026-07-06)

Real Wayland runtime pass:

- Added an **Open save folder** action to the region-capture overlay and the
  editor toolbar. The folder button and `Ctrl+O` open the configured
  screenshot destination immediately from the screenshot UI; when `save_dir`
  is empty this remains the OS/XDG Pictures directory plus `Screenshots`.
- Fixed source/install launches when `python3` on `PATH` is a pyenv/mise-style
  interpreter without distro GTK bindings: the bundled launcher now uses the
  distro Python at `/usr/bin/python3`, matching the documented package
  dependencies.
- Added explicit GI version pins for GDK, GdkPixbuf and Pango imports so real
  PyGObject runs no longer emit version-selection warnings.
- Fixed a `daemon --bind-once` race where an immediate portal rejection could
  print the fallback instructions but leave the daemon running; source-tree
  GNOME runs now also explain the portal's desktop-app-id requirement.
- Verified on a real GNOME Wayland session: `diagnose` passes with GTK,
  pycairo, wl-clipboard, GStreamer/PipeWire and portal interfaces available;
  scripted portal screenshot capture saved a 2240x1400 PNG; opening the save
  folder launched the desktop file manager.

## 0.7.2 (2026-07-06)

Release hygiene:

- Standardized user-facing default-shortcut wording as `Ctrl+PrtSc` while
  keeping compositor/portal trigger examples in their required `Print` syntax.
- Fixed the settings round-trip unit test so it closes the temporary
  `config.json` file handle. This keeps warning-sensitive CI/test runs clean.
- Re-ran the full headless validation suite after syncing to the latest
  released codebase.

## 0.7.1 (2026-07-06)

Bug fixes found by a static review of the 0.3.0–0.7.0 GTK code:

- **Auto-scroll no longer crashes**: `scroll --auto` called a non-existent
  `toast()` on the recorder window when the RemoteDesktop portal was
  unavailable/denied — the "scroll manually" fallback message now shows
  correctly instead of a swallowed AttributeError.
- **No more zombie process**: closing the GIF/scroll/manual capture window with
  the window-manager close button (rather than Cancel/Esc) left the app held
  with no windows and hung. `release()` is now wired to the window's destroy
  signal, so it fires however the window closes.
- Added a CI workflow (compile + unit tests on 3.10/3.12 + po-sync check).

## 0.7.0 (2026-07-06)

Backlog sweep (#16) — the editor and capture goodies:

- **New annotations**: numbered step-arrow (G), speech bubble (U), emoji
  sticker (J) — all movable/restyle-able via the select tool.
- **Toolbar presets**: colour-swatch + stroke-size popover.
- **Export formats**: save PNG/JPEG/WebP/AVIF/TIFF/BMP by extension;
  `Ctrl+Shift+C` copies the saved file path.
- **OCR / QR** (local): when `tesseract` / `zbarimg` are installed, extract
  text or QR/barcode contents from the capture to the clipboard.
- **Capture history**: `history` mode — a gallery of recent screenshots.
- **Settings window**: `settings` mode edits config.json.
- **GIF recording**: `gif` mode records a region to an animated GIF via a
  dependency-free GIF89a encoder (unit-tested LZW).
- **Cursor hints**: per-resize-handle Wayland cursor shapes in the overlay.

## 0.6.0 (2026-07-06)

First cuts of the remaining hardware-dependent issues (verify on real
hardware — tracked in #17):

- **Multi-monitor edge snapping** (#6): the selection snaps to monitor
  boundaries, computed by mapping each `GdkMonitor` geometry into the
  combined-image buffer coordinates. Single-monitor behaviour is untouched.
- **Fractional-scaling hairline** (#11): under 125%/150% scaling the selection
  outline aligns to device-pixel boundaries so it stays crisp; integer scale is
  unchanged, and the saved crop was already exact buffer pixels.
- **Auto-scroll** (#3, experimental): `scroll --auto` drives scrolling through
  the RemoteDesktop portal and auto-finishes at the bottom. Opt-in; falls back
  to manual if the portal is unavailable or denied — never bypasses the
  compositor security model.

## 0.5.0 (2026-07-06)

- **Scrolling capture without GStreamer** (#1): when the GStreamer/PipeWire
  plugin is missing, `scroll` falls back to a manual mode — pick an area, then
  scroll and press *Capture frame* per step; the frames feed the same
  unit-tested stitcher and open in the editor. PipeWire stays the default when
  present. No new dependency (GdkPixbuf, not PIL).

GTK/portal features shipped in 0.3.0–0.5.0 are runtime-verified on a real
Wayland session — tracked in the on-device checklist (#17).

## 0.4.0 (2026-07-06)

Reliability and reach (GitHub issues #2, #5, #15).

Global shortcuts (#5)
- **Reliable Ctrl+PrtSc**: the capture spawn now inherits the full session
  environment and fixes PYTHONPATH so it launches in any install layout, and
  logs what it runs — no more silent "I pressed the key and nothing happened".
- **Desktop-aware setup**: `diagnose` detects your desktop (GNOME/KDE/Hyprland/
  Sway/other) and prints the exact Ctrl+PrtSc binding steps; the daemon logs
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
- Default hotkey Ctrl+PrtSc (GlobalShortcuts portal daemon + setup script)
- 100% local: no upload, no accounts, no telemetry, no network code
