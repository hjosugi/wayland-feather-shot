<!-- i18n: language-switcher -->
[English](README.md) | [日本語](README.ja.md)

# wayland-feather-shot

**Flameshot-style screenshot tool, built Wayland-first. 100% local — no
upload button, no accounts, no telemetry, no network code at all.**

Flameshot風のWayland専用スクリーンショットツール。クラウドアップロード機能は
存在しません(ネットワークコード自体がありません)。UIは日本語/英語自動切替。

![tools](data/icons/io.github.hjosugi.WaylandFeatherShot.svg)

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
  **Ctrl+O** opens the save folder, **Esc** cancels, **Enter** = copy & close.
- **Scrolling capture / スクロールキャプチャ** — records the screen while
  *you* scroll (ScreenCast portal + PipeWire), automatically keeps one frame
  per pause, and stitches them into one tall image. Sticky headers/footers
  are auto-detected and de-duplicated.
- **Wayland-native by design**: every capture goes through
  `org.freedesktop.portal.Screenshot` / `ScreenCast`. No X11 fallbacks, no
  compositor-specific hacks — works on GNOME, KDE Plasma, Hyprland, Sway and
  anything else with a portal backend.
- **Default hotkey: Ctrl+PrtSc** (see below).
- English / Japanese UI out of the box (follows `LANG`; override with
  `WFS_LANG`). More languages via gettext catalogs — see [po/](po/README.md).

## Install / インストール

On Arch / CachyOS, install the packaged release from the AUR once published:

```console
$ yay -S wayland-feather-shot
# or
$ paru -S wayland-feather-shot
```

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
$ ./install.sh --with-hotkey  # …and register Ctrl+PrtSc (GNOME: automatic)
```

Remove files installed by `install.sh`:

```console
$ wayland-feather-shot updater remove
```

(A `pyproject.toml` is also provided, so `pip install .` works if you prefer
pip — the GTK/GStreamer stack itself still comes from your distro.)

You also need `xdg-desktop-portal` plus a backend, which every mainstream
Wayland desktop already ships (`-gnome`, `-kde`, `-wlr`, `-hyprland`, `-gtk`).

Not sure what's missing? Run the built-in environment check:

```console
$ wayland-feather-shot diagnose
```

## Usage / 使い方

```console
$ wayland-feather-shot            # region capture (default)
$ wayland-feather-shot full       # whole screen straight into the editor
$ wayland-feather-shot window     # pick a window via the portal picker
$ wayland-feather-shot scroll     # scrolling capture (you scroll)
$ wayland-feather-shot scroll --auto  # auto-scroll via RemoteDesktop portal (experimental)
$ wayland-feather-shot gif        # record a region to an animated GIF
$ wayland-feather-shot edit x.png # open an existing image in the editor
$ wayland-feather-shot history    # gallery of recent screenshots
$ wayland-feather-shot settings   # edit the config in a window
$ wayland-feather-shot -d 3 gui   # 3-second delay
$ wayland-feather-shot daemon     # GlobalShortcuts-portal hotkey daemon
$ wayland-feather-shot diagnose   # check portals/GTK/GStreamer availability
$ wayland-feather-shot updater remove  # remove install.sh-managed files
```

The editor toolbar adds a **step-arrow** (numbered), **speech bubble** and
**emoji sticker**, colour/width **presets**, a **flatten-blur** toggle, and —
when `tesseract` / `zbarimg` are installed — **OCR / QR** extraction that
copies recognized text to the clipboard. `Ctrl+Shift+C` copies the saved file
path; `Ctrl+O` opens the save folder; images save as PNG/JPEG/WebP/AVIF by
extension.

### Scripting / スクリプト

`gui` and `full` take non-interactive options so captures can be automated:

```console
$ wayland-feather-shot full --no-editor                 # save, print the path, exit
$ wayland-feather-shot full --region 0,0,1280,720 -o a.png --no-editor
$ wayland-feather-shot full -o ~/shot.png               # open editor, Ctrl+S → that path
```

`--region X,Y,W,H` crops the capture (clamped to the screen), `--output/-o PATH`
chooses the file (PNG/JPEG/WebP by extension), `--no-editor` skips the UI and
prints the saved path. Exit codes: `0` ok, `1` error, `2` bad usage,
`130` cancelled — suitable for shell scripts.

### Region capture / 範囲キャプチャ

1. The screen freezes. Drag to select (click or Enter = full screen).
2. Annotate right on the selection — toolbar keys:
   `V` move/resize, `P` pen, `L` line, `A` arrow, `R` rect, `E` ellipse,
   `H` highlighter, `T` text, `B` blur, `X` pixelate, `M` numbered marker,
   `W` open in a full editor window (adds crop).
3. `Ctrl+S` save • `Ctrl+O` open save folder • `Ctrl+C` / `Enter` copy •
   `Ctrl+Z` undo • `Esc` cancel.

### Scrolling capture / スクロールキャプチャ

1. `wayland-feather-shot scroll` — pick the window/screen in the portal dialog.
2. Scroll the content slowly top→bottom, pausing briefly after each scroll
   (each pause is captured automatically — watch the frame counter).
3. Press **Finish & stitch**. The stitched tall image opens in the editor;
   `Ctrl+S` / `Ctrl+C` as usual.

ゆっくりスクロールして、スクロールごとに一瞬止めるのがコツです。固定ヘッダー/
フッターは自動検出されて重複除去されます(`~/.config/wayland-feather-shot/config.json`
の `scroll_top_margin` / `scroll_bottom_margin` で手動指定も可能)。

#### Optional auto-scroll (experimental) / 自動スクロール

`wayland-feather-shot scroll --auto` — or the **Auto-scroll** checkbox in the
recording window — drives the scrolling for you through the
`org.freedesktop.portal.RemoteDesktop` portal instead of you scrolling by hand.
It is **opt-in and never the default**: injecting synthetic input needs a
per-session permission dialog, so manual scrolling stays the safe, portable
path. Hover the pointer over the scrollable content first — the portal delivers
the scroll wheel wherever the pointer sits. Auto-scroll stops on its own at the
bottom of the page (no new frames) or after `scroll_auto_steps` steps; tune
`scroll_auto_delta` / `scroll_auto_interval` / `scroll_auto_steps` in
`config.json`. It needs the GStreamer/PipeWire recorder too — the
GStreamer-free fallback cannot be auto-driven.

Portal support varies by desktop; run `wayland-feather-shot diagnose` to see
whether `scroll --auto` will work on your machine:

| Desktop | RemoteDesktop portal | Notes |
| --- | --- | --- |
| GNOME (Mutter) | yes | permission dialog once per session |
| KDE Plasma | yes | permission dialog once per session |
| Hyprland / wlroots (`xdg-desktop-portal-wlr`) | usually no | the checkbox stays disabled — scroll manually |
| Sway | usually no | scroll manually |

`--auto` はオプションです。RemoteDesktop ポータルが必要で、対応していない環境では
チェックボックスが無効のまま(手動スクロール)になります。

### Default hotkey: Ctrl+PrtSc

On Wayland there is **no** portable way for an app to grab a global key — the
compositor decides. Two mechanisms cover the field; pick the row for your
desktop (or just run `wayland-feather-shot diagnose`, which detects your
desktop and prints the exact command):

| Desktop | Recommended | How |
| --- | --- | --- |
| GNOME | native shortcut | `./scripts/setup-hotkey.sh` (gsettings, idempotent) |
| GNOME 46+ | portal daemon | autostarted `wayland-feather-shot daemon` |
| KDE Plasma | portal daemon | autostarted `wayland-feather-shot daemon` (approve once) |
| Hyprland | native shortcut | `bind = CTRL, Print, exec, wayland-feather-shot gui` |
| Sway / wlroots | native shortcut | `bindsym Ctrl+Print exec wayland-feather-shot gui` |
| other | native shortcut | bind `wayland-feather-shot gui` in your settings |

**If pressing the key does nothing**, first check the capture itself works:

```console
$ wayland-feather-shot gui        # if this opens the overlay, capture is fine
$ wayland-feather-shot diagnose   # detects your desktop + prints the binding
$ wayland-feather-shot daemon --bind-once   # test the portal binding, then exit
```

If `gui` works but the key doesn't, it's the binding mechanism — use the table
above. The daemon logs every activation and the exact command it launches to
stderr, so `wayland-feather-shot daemon` in a terminal shows what happens when
you press the key. You can override the portal trigger with
`wayland-feather-shot daemon --shortcut SUPER+Print`.

## Configuration

`~/.config/wayland-feather-shot/config.json` (created on first run):
save directory, filename pattern, default color/width, blur strength,
scroll-capture margins and limits. See `src/wayland_feather_shot/settings.py`.

`save_dir` defaults to empty = automatic: the OS/XDG Pictures directory
(localized, e.g. `~/画像`) plus `/Screenshots`. The `Ctrl+O` save-folder
button opens this same resolved folder. Set `save_dir` to a path to override.

## Troubleshooting

Start with `wayland-feather-shot diagnose` — it checks GTK, pycairo,
wl-clipboard, GStreamer/PipeWire and the portal interfaces, and tells you
what's missing.

- **Nothing happens / error dialog about the portal** — make sure
  `xdg-desktop-portal` and your desktop's backend are running
  (`systemctl --user status xdg-desktop-portal`). On wlroots compositors
  you need `xdg-desktop-portal-wlr` *and* `xdg-desktop-portal-gtk` (for the
  file chooser), plus `XDG_CURRENT_DESKTOP` exported to your session.
- **Copy disappears after closing** — the copy is kept alive by a bundled
  holder process (or `wl-copy` if installed), so it should survive closing
  the window. If neither can start, the UI says to keep the window open
  until you paste.
- **Scroll capture without GStreamer** — if the GStreamer PipeWire plugin
  (`gst-plugin-pipewire` / `gstreamer1.0-pipewire`) is missing, `scroll` falls
  back to a manual mode: pick an area, then scroll and press *Capture frame*
  for each step. Installing the plugin enables the smoother automatic
  frame-keeping instead.

## Development

```console
$ python3 tests/test_stitcher.py   # stitching engine unit tests (no GTK needed)
$ python3 tests/test_paths.py      # XDG paths + diagnostics tests (no GTK needed)
$ ./bin/wayland-feather-shot gui   # run from the repo without installing
```

Design notes live in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/SECURITY.md](docs/SECURITY.md). Known limitations and the roadmap are
tracked as [GitHub issues](https://github.com/hjosugi/wayland-feather-shot/issues)
(summary in [ISSUES.md](ISSUES.md)).

License: [MIT](LICENSE)
