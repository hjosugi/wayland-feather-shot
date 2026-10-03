# Changelog

## Unreleased

- **Ctrl+Shift+PrtSc copies a region straight to the clipboard.** A new
  `copy` mode opens the region overlay, and selecting is the whole job:
  releasing the drag (a click takes the whole screen, a click in Screen mode
  a whole monitor) copies the selection and closes. The portal daemon and
  `scripts/setup-hotkey.sh` bind it next to Ctrl+PrtSc and Ctrl+Shift+F12.

## 0.11.0 (2026-10-03)

- **Faster from key press to overlay.** The portal needs about a second to
  take the screenshot; the request is now sent before the GTK stack loads, so
  our own start-up overlaps with the portal's work instead of preceding it.
  The editor window's modules load only when the editor opens, and the
  screenshot reaches the overlay without being copied twice on the way (about
  40 ms on a 4K screen). Blurred regions are remembered per image, so adding
  or undoing annotations after a blur no longer redoes the blur (tens of
  milliseconds each without numpy), and a blur being dragged out is shown as a
  footprint until release.

- **Text is typed on the canvas.** The overlay's text tool opened a popover,
  so the words were visible but their size on the capture was anyone's guess.
  Clicking with the text tool now puts a caret on the canvas and the text
  appears at its final size, weight and colour as it is typed, following zoom.
  Enter is a newline, Ctrl+Enter finishes, Esc cancels, and a press anywhere
  else finishes too, as in the editor window.
- **Selection or Screen, as in GNOME's screenshot UI.** While nothing is
  selected, a bar at the bottom of the region overlay switches between
  dragging out a region (as before) and taking a whole monitor: in Screen
  mode the monitor under the pointer lights up and a click selects all of
  it, ready to annotate.
- **Text styles, and plain text by default.** Every text used to get a
  contrasting outline. The text tool now offers plain letters (the new
  default), outlined letters, or letters on a dark box, in the overlay's
  toolbar and next to the alignment buttons in the editor, where the choice
  also restyles the selected text and is remembered. The text being typed
  shows the style it will have.
- **One size control that says what it sizes.** The spinner in the toolbar
  now carries an icon and follows the tool: line width for the drawing tools,
  text size for the text tool. `[` and `]` step it from the keyboard.

- **Zoom in the region overlay.** Precise work on a small selection meant
  squinting at it at screen size. Ctrl+wheel, a touchpad pinch, Ctrl++ and
  Ctrl+- zoom around the pointer, Ctrl+1 fills the window with the selection,
  Ctrl+0 goes back to the whole screen, and the wheel pans while zoomed in.
  Everything else — handles, tools, the hand, the controls — follows the
  zoomed view.
- **Resizing past the opposite edge flips the selection** instead of
  pinning it to a one-pixel sliver.
- **The action bar hangs from the selection's top edge everywhere.** For a
  short, wide selection it used to share the selection's bottom edge and
  stick up above it, alone. Now it reaches down from the top-right corner
  like everywhere else, and the toolbar's right end lines up with the
  selection's right edge (as in Lightshot and Snipaste), so the two bars
  always meet at the selection's corner and a toolbar wider than the
  selection sticks out on one side only.

- **One capture at a time.** Pressing the hotkey while the overlay was already
  up stacked another fullscreen capture on top of it, and another, each one a
  screenshot of the previous. A capture now holds a lock in the runtime
  directory for as long as its overlay (or scroll or GIF capture window) is
  open; a second launch says so and exits with status 1. An editor window does
  not hold it, so capturing again with one open still works. The lock is an
  flock, so a crash cannot leave it behind.
- **Fixed: the portal's capture file piled up in $HOME** (#52). Some portal
  backends write the capture into the Pictures folder or straight into the
  home directory rather than a temp directory, and the cleanup only ever
  removed files from temp locations. A file elsewhere is now removed too, but
  only when its timestamp shows it was written for this very request, so a
  stale path can never delete a real picture. Thanks to
  [@fenix0xf](https://github.com/fenix0xf) for the report.
- **Moving a blur with the hand no longer stutters.** The dragged blur used
  to be re-rendered from the screenshot on every frame; while it moves it is
  shown as a translucent footprint instead, and the real blur is rendered once
  on release.

- **A hand tool in the region overlay** (S). Until now an annotation was
  fixed where it landed; moving a rectangle or a text by a few pixels meant
  undoing it and drawing it again. The hand grabs the topmost shape under the
  pointer, moves it live, and records the move in the undo history. While it
  moves, the shape is drawn as a live preview instead of through the cached
  annotation composite, so dragging stays as cheap as drawing a new shape.
- **Fixed: the hotkey daemon left a zombie process per key press.** Each
  capture it launched was never waited for; it is reaped now.

- **The region overlay has no edit mode any more.** The "edit mode" was only
  a flag that meant "a selection exists", and it got in the way: the resize
  handles already worked with every tool but the cursor only said so with the
  move tool, and changing the selection could not be undone. Now everything
  follows from the selection itself. Handles show their resize cursor with
  any tool, and selection changes (a new selection, a move, a resize, the
  first selection itself) go into the same undo history as the annotations,
  so Ctrl+Z brings the previous selection back and undoing past the first one
  returns to the empty overlay.

- **The documentation is in English only.** The Japanese copies of the
  README and the docs are gone; the app itself still speaks English and
  Japanese.

- **Scrolling capture moves from a key to the app's menu.** Only the two
  everyday captures have keys now: Ctrl+PrtSc for a region and Ctrl+Shift+F12
  for the full screen, with the portal daemon and with the native bindings
  `scripts/setup-hotkey.sh` makes. Scrolling capture is in the app's menu
  (right-click Feather Shot in the dock or app grid). A scroll binding the
  helper made earlier stays until you delete it in Settings → Keyboard.
- **Fixed: declining the screen-share dialog showed an error.** Cancelling
  the portal's dialog at the start of a scrolling capture now just ends it,
  instead of saying the screen could not be captured and to check the portal
  installation.

- **Signed pacman repository for Arch / CachyOS.** The AUR is not accepting
  new accounts, so the package is now also served as a pacman repository from
  the assets of the `pacman-repo` GitHub release: trust the signing key, add
  the repository to `pacman.conf`, and `pacman -S wayland-feather-shot` installs
  it and `pacman -Syu` keeps it current. `scripts/publish-pacman-repo.sh`
  builds and signs the package and database, and the release workflow
  publishes them when `PACMAN_REPO_GPG_PRIVATE_KEY` is set.

- **Hotkey guide.** `docs/HOTKEYS.md` explains how to
  bind the capture keys on each desktop, what the portal daemon needs, and
  lists every in-app key. A shared `.vscode/` adds launch configurations for
  debugging.

- **Fixed: `wayland-feather-shot daemon` failed on GNOME with "An app id is
  required"**. The GlobalShortcuts portal only opens a session for a client it
  can name, and a process running outside a sandbox has no app id unless it
  says so; xdg-desktop-portal does not derive one from the launching desktop
  entry or the systemd scope, so the autostart entry failed the same way as a
  terminal run. The daemon now opens a private D-Bus connection and registers
  the app id through `org.freedesktop.host.portal.Registry` before any other
  portal call (GTK's own settings lookup on the shared connection used to get
  there first). Only the daemon registers: a registered app id makes the
  Screenshot portal ask for per-app permission through a dialog it cannot show
  for a windowless client, which would turn every capture into the interactive
  dialog, so the capture path keeps the plain connection. The portal insists
  that a desktop entry named after the app id exists, which a package install
  provides; for a git checkout, the new `scripts/install-desktop-entry.sh`
  installs the entries with `Exec=` pointing at the checkout (`--autostart`
  adds the daemon at login). The daemon's failure message now says exactly
  that instead of pointing at the autostart entry.

## 0.10.2 (2026-10-01)

- **The overlay's annotation tools have icons** (#41). The bottom toolbar of
  the region overlay mixed text buttons for the drawing tools with the icon
  buttons for undo and redo, and short labels like "High" and "Pixel" were
  hard to read at a glance. The eleven tool buttons now use symbolic SVG icons
  drawn in one visual language, matching undo/redo and the action bar. The
  icons ship inside the package and are registered with `Gtk.IconTheme` at
  startup, so they do not depend on a system icon theme — many wlroots
  desktops have none installed. Tooltips still name the tool and its shortcut,
  every button carries an accessible label, and the colour and line-width
  controls are unchanged. The standalone editor keeps its text labels for now.
  Thanks to [@Vssblt](https://github.com/Vssblt) for the proposal and the
  implementation (#45).
- **Double-click a selection to copy it** (#42). Copying a finished region
  meant reaching for the action bar or a keyboard shortcut. With the
  move/resize tool active, double-clicking inside the completed selection now
  does what the Copy button does: copy the image to the clipboard and close
  the overlay. The gesture ignores resize handles, annotation tools, clicks
  outside the selection and any press that turns into a drag, so single clicks
  and the existing shortcuts behave exactly as before.
  Thanks to [@Vssblt](https://github.com/Vssblt) for the proposal and the
  implementation (#46).
- **Fixed: creating, moving and resizing a selection stuttered** (#47). Every
  pointer move repainted the whole screenshot through Cairo — once dimmed,
  then again inside the selection — which on a 2560 × 1440 display capped
  selection updates at about 21–23 per second. The overlay is now a
  snapshot-based canvas: the screenshot lives in a persistent GTK texture, the
  composite of completed annotations is rebuilt only when the annotation
  history changes, and the dim mask, selection border and handles are GTK
  render nodes. Only the live annotation preview and the small labels still go
  through Cairo. Per-frame drawing time fell from about 20 ms to under 1 ms in
  the contributor's measurements. A new CI job runs the rendering regressions
  under Xvfb, covering scales from 1 to 2, mask seams, handle positions,
  letterboxing and undo/redo invalidation. Fractional compositor scaling and
  mixed-scale multi-monitor setups have not been verified by hand yet.
  Thanks to [@Vssblt](https://github.com/Vssblt) for the investigation, the
  measurements and the fix (#48).

## 0.10.1 (2026-09-29)

- **Fixed: GUI processes lingered after the last window closed** (#43). Every
  window released the application's manual hold from its `destroy` signal, a
  GTK 3 habit that no longer works: in GTK 4 `gtk_window_destroy()` only drops
  the toplevel reference, and the Python signal closures inside a window keep
  it alive, so `destroy` never fired and `wayland-feather-shot gui` stayed
  running after Copy or Esc — on every desktop, not just Sway. Holds are now
  released on `Gtk.Application::window-removed`, which fires synchronously when
  the window closes.
  Thanks to [@Vssblt](https://github.com/Vssblt) for the report and the fix
  (#39).
- **Fixed: the overlay toolbar and action bar overlapped for small
  selections** (#40). The two bars were placed independently and only checked
  against the screen edges, so any selection shorter than the vertical action
  bar had the bars crossing. Placement now lives in a pure `overlay_layout`
  module that keeps the usual L-shaped arrangement whenever it fits, aligns the
  action bar to the bottom of a short selection, and turns it into a second
  horizontal row under the toolbar when a screen corner leaves no room. The
  dimension label moves out of the way of the controls too.
  Thanks to [@Vssblt](https://github.com/Vssblt) for the report and the fix
  (#44).

## 0.10.0 (2026-08-25)

- **Background and framing** (#36). A screenshot can now be handed back as a
  finished image rather than raw pixels: padded on a **solid colour, a
  gradient, or an image**, with rounded corners, a real **drop shadow** (soft /
  long / glow / crisp), an optional **border**, a canvas **aspect ratio**
  (1:1 / 4:3 / 3:2 / 16:9 / 9:16) with nine-point alignment inside it, and a
  **watermark** that can sit in the corner or tile across the whole thing. All
  of it stays live in the document — nothing is flattened into the image — and
  it is saved in the sidecar, so a composition reopens exactly as it was.
  Everything is expressed as a fraction of the screenshot rather than in
  pixels, so one setting looks the same on a 1080p capture and a 4K one. Off by
  default: a screenshot tool should hand back what you captured unless you ask
  for more.

- **Smart redaction** (#35). Redacting a screenshot before sharing meant
  finding every token, email address and IP by eye, and missing one is the
  whole risk — the failure is silent. The editor can now scan a capture with
  the OCR that already ships and **propose** blur regions over anything that
  looks sensitive: email addresses, URLs, IPv4 (validated octet by octet, so
  version numbers do not match), phone numbers by digit count, payment cards
  **checked with Luhn**, JWTs, the known key prefixes (`sk_`/`pk_`, `ghp_`,
  `xoxb-`, `AKIA`, `AIza`, `ya29.`, …), long opaque tokens, and
  `password: …`-style labels — where it redacts the value, not the label.
  Overlapping matches merge into one region and near-duplicates are dropped, so
  a key that is also an opaque token gets one box rather than three. The scan
  runs off the UI thread, and the results arrive as **ordinary redaction
  shapes**: selected, movable, resizable and undoable in one step. Nothing is
  ever applied silently, and a scan that finds nothing says so rather than
  implying the image is clean.

- **Redaction finishes the job** (#22). Blur is now a real Gaussian — three
  running-sum box passes, which converge on one — over a **padded** sample of
  the source, so a region no longer smears its own edge inwards instead of the
  pixels that actually surround it. It is applied to a downsampled copy, which
  keeps it fast and, for a redaction, is the point: throwing the detail away
  before smoothing it is what makes the result unrecoverable rather than merely
  softened. The resample-based blur that came before left the *positions* of
  text lines visible as banding; this does not. numpy is used when present and
  the pure-Python path is the fallback, as the scroll stitcher already does.
  **Redaction strength is adjustable from the toolbar**, and applies to an
  already-drawn region as well as to new ones — "this token needs more" no
  longer means redrawing it.

- **The editor remembers where you left off** (#37). Tool, colour, stroke
  width, font, text alignment, arrowheads, redaction strength and spotlight dim
  all come back the way you last had them, instead of resetting to the
  configured defaults on every capture. Kept in its own
  `editor-preset.json`, deliberately not in `config.json`: those are the
  defaults you chose, and overwriting them with wherever the last session ended
  would make "reset to defaults" meaningless. A preset that cannot be read
  falls back field by field, so a version change or a hand-edit typo costs at
  most one setting rather than all of them, and failing to save one never
  surfaces in front of someone who just wanted to save a screenshot.

- **Spotlight tool** (`S`) (#34). Drag a region and everything outside it is
  dimmed, so the eye lands where you are pointing — the common need when
  explaining a screenshot, and the opposite of what the highlighter does.
  Several spotlights leave a single bright **union**: the scrim is painted once
  and each region cleared out of it, rather than dimmed per shape, so two
  overlapping spotlights do not double-darken where they meet. The scrim sits
  between the base image and the annotation layer, so an arrow or a label drawn
  over a dimmed area keeps its full contrast. How dark it goes is adjustable,
  for new spotlights and for any selected one. The existing highlighter keeps
  its own tool and is now labelled **Marker**.

## 0.9.0 (2026-08-25)

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
