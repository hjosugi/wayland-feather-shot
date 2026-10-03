# Security / Privacy

wayland-feather-shot is local-only.

## Removed by design

- Cloud upload (no Imgur client, no upload button)
- Account login
- Telemetry / crash reporting
- Network sync or background network tasks
- Network code of any kind — there is nothing to disable

## Local actions only

- Read the screenshot file URI returned by xdg-desktop-portal, then delete
  the portal temp file after loading it.
- Save PNG/JPEG/WebP to a local directory chosen by the user.
- Copy the rendered image to the local Wayland clipboard (via `wl-copy`
  when available, otherwise a bundled local holder process, otherwise the
  in-process GDK clipboard). The holder only ever owns the clipboard — it
  opens no files beyond the temp PNG it is handed, and no sockets.
- Optional GlobalShortcuts portal session for Ctrl+PrtSc.
- Optional ScreenCast portal + PipeWire session for scrolling capture,
  started only on explicit user action and closed when done.

## Wayland security model

The app never bypasses the compositor. All screen access goes through
XDG Desktop Portal request/permission flows. Scrolling capture reads
visible frames only — it cannot and does not read other windows'
off-screen content or inject input.
