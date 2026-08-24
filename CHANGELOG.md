# Changelog

## Unreleased

- **Text is typed on the canvas** (#31). The text tool used to open a popover;
  you typed into a widget-scale box and pressed Add, and after that the text
  was frozen — no re-editing, no cursor in the image, and no way to tell how
  the result would look at export size. Now clicking with the text tool puts a
  caret directly on the image at the right position, size and colour, and
  clicking existing text with the tool re-opens it. Clicking away commits;
  <kbd>Esc</kbd> or <kbd>Ctrl+Enter</kbd> finishes; an empty text shape is
  discarded along with the undo step that created it. Text gains **alignment**
  (left / centre / right) and an **auto-size → wrap** switch: the box hugs its
  text until a side handle is dragged, which sets a wrap width, while corner
  handles keep scaling the type. Growing text keeps its alignment anchor fixed,
  so centred text grows evenly to both sides and right-aligned text grows
  leftwards instead of everything shoving rightwards from where it was placed.

- **Arrows curve, and have heads worth choosing** (#32). An arrow was a
  straight shaft with one filled triangle at the far end, which is the wrong
  tool for a dense screenshot where a straight line to the thing you mean often
  crosses the thing you don't. Arrows now carry a **bend**: select one and drag
  its middle handle to bow it into an arc, with the head following the tangent
  rather than the chord, and a nearly-straight arrow snapping back to straight.
  Nine head styles — none, arrow, outlined triangle, chevron, square, dot,
  diamond, bar, inverted — selectable for each end independently, so a line is
  simply an arrow with no heads. A selected arrow shows start / middle / end
  handles instead of a resize frame, because its bounding box is mostly empty
  space; for the same reason it opts out of drag-from-the-inside. The shaft is
  trimmed by each head's own length instead of a flat fudge factor, so a heavy
  stroke no longer pokes out through the tip.

- **Freehand strokes have real ink** (#33). The pen joined raw pointer samples
  with a constant-width polyline, so a fast stroke came out visibly polygonal,
  a slow one lumpy, and both of them dead — circling a UI element looked like a
  rubber band. Strokes now go through a port of `perfect-freehand`: the samples
  are streamlined to remove hand jitter, pressure is simulated from speed so
  fast segments thin and slow ones thicken, each point gets a radius from that,
  and the resulting outline is filled as a smoothed polygon rather than stroked
  as a path. Hit-testing follows the streamlined centreline padded by the
  stroke's own half-width, so a wide stroke is grabbable anywhere in its ink
  and what you grab matches what you see. Committed strokes cache their
  outline, so redrawing ink that has not moved costs nothing.

- **Crop is now a rect over the pristine image, not a resample** (#30). Press
  `C` and the canvas shows the untouched capture with the current crop
  selected, so an earlier crop can be **widened** again and not only tightened
  — the pixels outside it are no longer thrown away. Eight drag handles, a
  rule-of-thirds grid, everything outside dimmed, and aspect presets:
  Freeform / Original / 1:1 / 16:9 / 9:16 / 4:3 / 3:2. Corner drags respect the
  lock, edge drags ignore it, <kbd>Alt</kbd> resizes about the centre. Crop is
  modal: <kbd>Enter</kbd> applies, <kbd>Esc</kbd> cancels, and other editing
  shortcuts are swallowed so they cannot act on the layer the overlay covers.
  Applying remaps the annotations and is one undo step, and the crop is stored
  in the sidecar so a reopened screenshot is still adjustable. The fit leaves
  room around the image while cropping, so a handle dragged to the very edge
  stays grabbable.

- **Annotations stay editable after saving** (#27). Saving a screenshot that
  has annotations now writes an editable document beside it as
  `<image>.wfs.json`, and `wayland-feather-shot edit x.png` picks the
  annotations back up exactly where they were left instead of opening flat
  pixels. The document carries the untouched base image as well as the shapes,
  because the saved PNG has the annotations burned in — so it is one extra
  file rather than two, and it cannot get separated from the image it
  describes. Screenshots with no annotations stay a single file. The format is
  versioned and tolerant: an unknown shape kind or field from a newer release
  is skipped rather than failing the whole document, and a document written by
  a newer version opens the flat image with a note instead of guessing. Turn it
  off with the new `save_sidecar` setting.

## 0.8.1 (2026-08-24)

- Fixed the region-overlay toolbar and sidebar jumping while a selection was
  moved or resized. The floating controls are positioned with widget margins,
  but `Gtk.Widget.measure()` reports a widget's size *including* its own
  margins — so every reposition fed the previous position back into the next
  size calculation and the controls oscillated. The measurement now subtracts
  the margins back out.
  Thanks to [@Vssblt](https://github.com/Vssblt) for the diagnosis and the fix
  (#19).

## 0.8.0 (2026-08-24)

Annotation editor rebuild, informed by a close read of
[screendrop](https://github.com/fayazara/screendrop) (#38):

- **Fixed: Japanese text and emoji stickers rendered as tofu boxes** (#20).
  Every text-bearing shape drew through cairo's toy font API, which selects a
  single face and does no fallback, so all CJK and every emoji collapsed to the
  same `.notdef` box. All text now goes through Pango, which does script
  itemization and font fallback — Japanese annotations are readable and the
  emoji palette works (in colour where `Noto Color Emoji` is installed).
- **Fixed: numbered markers and step arrows reused a number** after a delete or
  an undo (#21). Numbering counted existing badges instead of taking the
  maximum, so removing ① and adding a badge produced a second ③. Markers and
  step arrows now share one sequence and never collide.
- **Redaction strength is a property of each region** (#22, partial). Blur and
  pixelate take a 0…1 density that drives the radius and the mosaic block size,
  and blur runs two resample passes instead of one — a single pass left large
  text legible, which is the one thing a redaction must not do.
- **Shapes carry a transform** — position, rotation, opacity — with their
  payload in their own local space, over page space that is the capture's own
  pixel space (#23). This is what makes the rest of the list possible, and it
  keeps export a 1:1 draw.
- **Precise hit-testing** through a real geometry layer (#24). Clicking inside
  a hollow rectangle, or in the empty corner of a diagonal arrow's bounding
  box, now reaches whatever is actually there. Shift-click extends the
  selection and dragging on empty canvas rubber-band selects.
- **Resize and rotate** committed shapes (#25): eight handles plus rotate
  handles outside the corners, hit-tested in widget space so they stay the same
  size to grab at any zoom. <kbd>Shift</kbd> locks a corner resize to the
  aspect ratio and snaps rotation to 15°. Arrow keys nudge, `Ctrl+↑`/`Ctrl+↓`
  reorder, `Ctrl+A` selects all.
- **Zoom and pan** (#28): 10 %…1600 % with `Ctrl`+scroll or `Ctrl`+`+`/`-`,
  `Ctrl+1` to fit, `Ctrl+0` for actual size, scroll and middle-drag to pan.
  The canvas could previously only shrink an image, so a 4K capture was
  annotated at ~35 % and by eye.
- **Resolution-independent sizing** (#29): stroke widths, font sizes and badge
  diameters are authored against a reference edge and converted to page units,
  so the same settings look the same on a 1080p and a 4K capture, and resizing
  a shape no longer changes its stroke weight.
- **Refactor**: the editor is now a pure model (`shapes`, `geometry`,
  `document`, `interaction`) with a thin GTK layer (`canvas`, `render`) on top.
  The pointer handling is an explicit state machine instead of a tool-keyed
  cascade over five nullable fields, and 106 new unit tests cover it — the
  editor had none before.

## 0.7.9 (2026-07-09)

- Kept the `wayland-feather-shot updater remove` release green by making the
  optional AUR publish step warn instead of failing the GitHub release when
  AUR SSH credentials are missing or rejected.

## 0.7.8 (2026-07-09)

- Added `wayland-feather-shot updater remove`, a GTK-free maintenance command
  that removes files created by `install.sh` while keeping user config.
- Added an AUR publishing helper plus an optional release-workflow AUR publish
  step for maintainers who configure `AUR_SSH_PRIVATE_KEY`.

## 0.7.7 (2026-07-08)

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
