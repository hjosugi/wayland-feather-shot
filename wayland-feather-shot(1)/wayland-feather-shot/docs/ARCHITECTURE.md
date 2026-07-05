# Architecture

## Capture

`capture/portal.py` calls `org.freedesktop.portal.Screenshot` on `org.freedesktop.portal.Desktop`.

Default target:

```text
area
```

Target mapping:

```text
screen        -> 1
window        -> 2
area          -> 4
active-window -> 8
```

If the portal does not support the version-3 `target` key, the code retries without that key.

## Editor

`editor/window.py` is GTK4. It keeps a base PIL image plus a list of operations. Export is a flattened PNG.

Operations:

- pen
- line
- arrow
- rectangle
- ellipse
- blur
- text
- crop

`Ctrl+S` always saves. `Ctrl+C` always copies a rendered PNG texture to the local clipboard.

## Scroll capture

`scrollcap/session.py` uses repeated visible screenshots and fixed crop. `scrollcap/stitcher.py` aligns overlap strips and appends new rows.

This avoids browser extensions and avoids hidden content reads.

## Shortcuts

`shortcuts/daemon.py` uses `org.freedesktop.portal.GlobalShortcuts` with preferred trigger:

```text
CTRL+Print
```

The fallback is a desktop keyboard shortcut bound to:

```bash
wayland-feather-shot capture --target area
```
