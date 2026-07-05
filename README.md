# wayland-feather-shot

**Flameshot-style screenshot tool, built Wayland-first. 100% local — no
upload button, no accounts, no telemetry, no network code at all.**

Flameshot風のWayland専用スクリーンショットツール。クラウドアップロード機能は
存在しません(ネットワークコード自体がありません)。UIは日本語/英語自動切替。

![tools](data/icons/wayland-feather-shot.svg)

## Features / 機能

- **Region capture with in-place annotation** — the screen is frozen via the
  xdg-desktop-portal, you drag a selection (with resize handles), and a
  Flameshot-style floating toolbar appears under it.
  範囲選択+その場で注釈(Flameshot風フローティングツールバー)。
- **Tools**: pen, line, arrow, rectangle, ellipse, highlighter, text,
  **blur / ぼかし**, pixelate / モザイク, auto-numbered markers (①②③),
  crop, undo/redo, color & line-width pickers.
- **Ctrl+S** saves instantly to `~/Pictures/Screenshots/`,
  **Ctrl+C** copies to the clipboard, **Ctrl+Shift+S** = save-as,
  **Esc** cancels, **Enter** = copy & close.
- **Scrolling capture / スクロールキャプチャ** — records the screen while
  *you* scroll (ScreenCast portal + PipeWire), automatically keeps one frame
  per pause, and stitches them into one tall image. Sticky headers/footers
  are auto-detected and de-duplicated.
- **Wayland-native by design**: every capture goes through
  `org.freedesktop.portal.Screenshot` / `ScreenCast`. No X11 fallbacks, no
  compositor-specific hacks — works on GNOME, KDE Plasma, Hyprland, Sway and
  anything else with a portal backend.
- **Default hotkey: Ctrl+Print** (see below).
- English / Japanese UI (follows `LANG`; override with `WFS_LANG=en|ja`).

## Install / インストール

Dependencies (the only hard ones are GTK4 + PyGObject + pycairo):

| Distro | Command |
| --- | --- |
| Arch / CachyOS | `sudo pacman -S --needed python-gobject gtk4 python-cairo wl-clipboard gst-plugins-base gst-plugin-pipewire python-numpy` |
| Debian / Ubuntu | `sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 wl-clipboard gstreamer1.0-pipewire gir1.2-gst-plugins-base-1.0 python3-numpy` |
| Fedora | `sudo dnf install python3-gobject gtk4 python3-cairo wl-clipboard pipewire-gstreamer python3-numpy` |

`wl-clipboard`, GStreamer and numpy are optional but recommended:
`wl-clipboard` lets a copy outlive the app window; GStreamer powers the
scrolling capture; numpy makes stitching fast.

Then:

```console
$ ./install.sh                # user install into ~/.local
$ ./install.sh --with-hotkey  # …and register Ctrl+Print (GNOME: automatic)
```

You also need `xdg-desktop-portal` plus a backend, which every mainstream
Wayland desktop already ships (`-gnome`, `-kde`, `-wlr`, `-hyprland`, `-gtk`).

## Usage / 使い方

```console
$ wayland-feather-shot            # region capture (default)
$ wayland-feather-shot full       # whole screen straight into the editor
$ wayland-feather-shot scroll     # scrolling capture
$ wayland-feather-shot -d 3 gui   # 3-second delay
$ wayland-feather-shot daemon     # GlobalShortcuts-portal hotkey daemon
```

### Region capture / 範囲キャプチャ

1. The screen freezes. Drag to select (click or Enter = full screen).
2. Annotate right on the selection — toolbar keys:
   `V` move/resize, `P` pen, `L` line, `A` arrow, `R` rect, `E` ellipse,
   `H` highlighter, `T` text, `B` blur, `X` pixelate, `M` numbered marker,
   `W` open in a full editor window (adds crop).
3. `Ctrl+S` save • `Ctrl+C` / `Enter` copy • `Ctrl+Z` undo • `Esc` cancel.

### Scrolling capture / スクロールキャプチャ

1. `wayland-feather-shot scroll` — pick the window/screen in the portal dialog.
2. Scroll the content slowly top→bottom, pausing briefly after each scroll
   (each pause is captured automatically — watch the frame counter).
3. Press **Finish & stitch**. The stitched tall image opens in the editor;
   `Ctrl+S` / `Ctrl+C` as usual.

ゆっくりスクロールして、スクロールごとに一瞬止めるのがコツです。固定ヘッダー/
フッターは自動検出されて重複除去されます(`~/.config/wayland-feather-shot/config.json`
の `scroll_top_margin` / `scroll_bottom_margin` で手動指定も可能)。

### Default hotkey: Ctrl+Print

- **GNOME**: `./scripts/setup-hotkey.sh` registers it automatically
  (`Ctrl+Print` → region, `Ctrl+Shift+Print` → scroll).
- **KDE / GNOME 46+**: the autostarted `wayland-feather-shot daemon` binds it
  through the GlobalShortcuts portal (approve the dialog once).
- **Hyprland**: `bind = CTRL, Print, exec, wayland-feather-shot gui`
- **Sway**: `bindsym Ctrl+Print exec wayland-feather-shot gui`

## Configuration

`~/.config/wayland-feather-shot/config.json` (created on first run):
save directory, filename pattern, default color/width, blur strength,
scroll-capture margins and limits. See `src/wayland_feather_shot/settings.py`.

## Troubleshooting

- **Nothing happens / error dialog about the portal** — make sure
  `xdg-desktop-portal` and your desktop's backend are running
  (`systemctl --user status xdg-desktop-portal`). On wlroots compositors
  you need `xdg-desktop-portal-wlr` *and* `xdg-desktop-portal-gtk` (for the
  file chooser), plus `XDG_CURRENT_DESKTOP` exported to your session.
- **Copy disappears after closing** — install `wl-clipboard`.
- **Scroll capture button greyed out** — install the GStreamer PipeWire
  plugin (`gst-plugin-pipewire` / `gstreamer1.0-pipewire`).

## Development

```console
$ python3 tests/test_stitcher.py   # stitching engine unit tests (no GTK needed)
$ ./bin/wayland-feather-shot gui   # run from the repo without installing
```

Known limitations and the roadmap live in [ISSUES.md](ISSUES.md).

License: [MIT](LICENSE)
