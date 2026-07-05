# Security / Privacy

Wayland Feather Shot is local-only.

## Removed by design

- Cloud upload
- Imgur upload
- Account login
- Telemetry
- Network sync
- Background network task

## Local actions only

- Read screenshot URI returned by xdg-desktop-portal.
- Save PNG to local disk.
- Copy rendered image to local clipboard.
- Optional GlobalShortcuts portal session for Ctrl+Print.

## Wayland security model

The app does not try to bypass the compositor. Screen access goes through XDG Desktop Portal. Generic scroll capture uses visible frames only.
