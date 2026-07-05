# Issues / Future Work

このファイルは GitHub Issues にそのまま分割投入できる形の backlog です。

## Issue 1: Fully automatic generic scroll capture through RemoteDesktop/InputCapture

Labels: `enhancement`, `wayland`, `scroll-capture`

Current state:

- Implemented: user-assisted scroll stitch mode.
- Not default: automatic scrolling of arbitrary apps.

Reason:

- On Wayland, a normal app should not freely read off-screen content or inject input into another app.
- A fully automatic mode needs compositor-supported permission flow, likely through RemoteDesktop/InputCapture/libei style APIs.
- Behavior differs across GNOME, KDE, Hyprland, Sway, and wlroots backends.

Acceptance criteria:

- Keep current user-assisted mode as the safe default.
- Add optional automatic mode only when the compositor exposes a supported input portal.
- Show a clear permission dialog/path.
- Never bypass the compositor security model.

## Issue 2: PipeWire ScreenCast continuous-frame backend

Labels: `enhancement`, `pipewire`, `wayland`

Current state:

- Implemented: Screenshot portal frame capture.
- Planned: ScreenCast portal + PipeWire frame stream for faster repeated capture.

Acceptance criteria:

- Create ScreenCast session through portal.
- Select one monitor/window source.
- Open PipeWire remote.
- Read frames and feed them into `scrollcap.stitcher`.
- Prefer `pipewire-serial` over reusable PipeWire node IDs when available.

## Issue 3: More brush tools

Labels: `enhancement`, `editor`, `brush`

Current tools:

- Pen
- Arrow
- Line
- Rectangle
- Ellipse
- Blur
- Text
- Crop

Future tools:

- Highlighter
- Pixelate
- Numbered marker
- Color picker
- Stroke size UI
- Color palette UI

Acceptance criteria:

- All tools must render through local PIL operations.
- No upload/network dependency.
- Undo/redo support for every tool.

## Issue 4: Flatpak packaging with no network permission

Labels: `packaging`, `flatpak`, `security`

Acceptance criteria:

- Flatpak manifest must not include network permission.
- Portal permissions only for Screenshot, FileChooser, and optional GlobalShortcuts/ScreenCast.
- App metadata must clearly state local-only behavior.

## Issue 5: Desktop-specific shortcut polish

Labels: `shortcut`, `ux`, `wayland`

Current state:

- Default trigger target is `CTRL+Print`.
- GlobalShortcuts portal daemon is implemented best-effort.
- Manual binding instructions are documented.

Future work:

- Detect GNOME/KDE/Hyprland/Sway and show one-click setup hints.
- Avoid overwriting existing screenshot shortcuts.
- Add a small first-run setup window.

## Issue 6: Better visual overlay capture UX

Labels: `ux`, `editor`, `wayland`

Current state:

- Selection is delegated to the compositor portal.
- Editing happens in the app window after capture.

Future work:

- Investigate layer-shell based overlay for wlroots compositors.
- Keep portal-first capture as the portable default.
- Do not make overlay a hard dependency.
