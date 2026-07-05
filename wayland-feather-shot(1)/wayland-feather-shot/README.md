# Wayland Feather Shot

Linux Wayland 専用の local-only スクリーンショットアプリです。Flameshot 風に「撮る → 編集する → Ctrl+S で保存 / Ctrl+C でコピー」を最短で行うための実装です。

## 方針

- Wayland first
- `xdg-desktop-portal` first
- cloud upload なし
- account なし
- telemetry なし
- network permission なし
- Ctrl+S は必ず PNG 保存
- Ctrl+C は画像を clipboard にコピー
- Ctrl+Print は default shortcut target
- blur tool あり
- browser extension なし
- scroll capture は user-assisted stitch mode

## Install

Ubuntu / Debian 系の例:

```bash
sudo apt update
sudo apt install -y python3 python3-gi python3-cairo gir1.2-gtk-4.0 python3-pil libglib2.0-bin
./install.sh
```

Fedora 系の例:

```bash
sudo dnf install -y python3 python3-gobject gtk4 python3-cairo python3-pillow glib2
./install.sh
```

Arch 系の例:

```bash
sudo pacman -S --needed python python-gobject gtk4 python-cairo python-pillow glib2
./install.sh
```

`~/.local/bin` が PATH に入っていない場合:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Usage

Area capture + editor:

```bash
wayland-feather-shot
```

明示的に area capture:

```bash
wayland-feather-shot capture --target area
```

画面全体:

```bash
wayland-feather-shot capture --target screen
```

既存画像を編集:

```bash
wayland-feather-shot edit ~/Pictures/Screenshots/example.png
```

診断:

```bash
wayland-feather-shot diagnose
```

## Editor keys

| Key | Action |
|---|---|
| Ctrl+S | Save PNG to `~/Pictures/Screenshots` |
| Ctrl+Shift+S | Save As dialog |
| Ctrl+C | Copy current image to clipboard |
| Ctrl+Z | Undo |
| Ctrl+Shift+Z / Ctrl+Y | Redo |
| Esc | Close |

## Tools

- Pen
- Arrow
- Line
- Rectangle
- Ellipse
- Blur
- Text
- Crop

## Ctrl+Print default shortcut

Default target is:

```text
CTRL+Print
```

The installer creates an autostart entry for:

```bash
wayland-feather-shot daemon --shortcut CTRL+Print
```

The daemon uses the XDG Desktop Portal GlobalShortcuts API. Some compositors still do not expose this portal. In that case, bind this command manually in your desktop shortcut settings:

```bash
wayland-feather-shot capture --target area
```

Examples:

Hyprland:

```ini
bind = CTRL, PRINT, exec, wayland-feather-shot capture --target area
```

Sway:

```ini
bindsym Control+Print exec wayland-feather-shot capture --target area
```

KDE / GNOME:

Use Settings → Keyboard → Custom Shortcuts and bind `Ctrl+Print` to:

```bash
wayland-feather-shot capture --target area
```

## Scroll capture without browser extension

Generic Wayland apps cannot expose off-screen content to another app. This project therefore uses a user-assisted visible-frame stitch mode:

1. Capture the screen through the portal.
2. Select the scrollable viewport once.
3. Scroll the target app yourself between frames.
4. Capture the same on-screen region repeatedly.
5. Stitch frames vertically.
6. Open the stitched PNG in the editor.

Example:

```bash
wayland-feather-shot scroll --frames 5 --delay 2.5
```

With a known crop rectangle:

```bash
wayland-feather-shot scroll --frames 6 --delay 2 --crop 120,160,900,700
```

## No upload guarantee

There is no upload button, no Imgur client, no cloud API dependency, no telemetry module, and no network dependency. The app only writes local PNG files and uses the local clipboard.

## Project layout

```text
src/wayland_feather_shot/
  capture/portal.py        xdg-desktop-portal Screenshot client
  editor/window.py         GTK4 editor
  image_ops.py             pure PIL drawing and blur operations
  scrollcap/stitcher.py    pure vertical scroll stitcher
  scrollcap/session.py     user-assisted scroll capture mode
  shortcuts/daemon.py      best-effort GlobalShortcuts portal daemon
  diagnostics.py           environment and portal checks
```

## Tests

Pure Python tests:

```bash
PYTHONPATH=src python3 tests/test_stitcher.py
PYTHONPATH=src python3 tests/test_image_ops.py
```

GTK / portal behavior must be tested on a real Wayland desktop session.

## Official specs used

- XDG Desktop Portal Screenshot: `org.freedesktop.portal.Screenshot`
- XDG Desktop Portal ScreenCast: future continuous-frame backend reference
- XDG Desktop Portal GlobalShortcuts: default `CTRL+Print` binding path
- Freedesktop Shortcuts Specification: `CTRL+Print` trigger syntax
- GTK4 `GdkClipboard`: image clipboard support through texture/content APIs
