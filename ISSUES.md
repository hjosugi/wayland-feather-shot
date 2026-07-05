# Issues

The backlog lives in the GitHub issue tracker:
<https://github.com/hjosugi/wayland-feather-shot/issues>

バックログは GitHub Issues に移行しました。以下は 0.2.0 統合時に起票した
一覧です(両実装ラインの ISSUES.md を統合・重複排除したもの)。

| # | Area | Summary |
| --- | --- | --- |
| [#1](https://github.com/hjosugi/wayland-feather-shot/issues/1) | scroll | GStreamer-free fallback (user-assisted repeated screenshots) |
| [#2](https://github.com/hjosugi/wayland-feather-shot/issues/2) | capture | First-class window capture mode |
| [#3](https://github.com/hjosugi/wayland-feather-shot/issues/3) | scroll | Optional auto-scroll via RemoteDesktop / InputCapture portal |
| [#4](https://github.com/hjosugi/wayland-feather-shot/issues/4) | scroll | Stitcher robustness (horizontal, animated content, overshoot) |
| [#5](https://github.com/hjosugi/wayland-feather-shot/issues/5) | hotkeys | Per-desktop status, clean daemon fallback, first-run hints |
| [#6](https://github.com/hjosugi/wayland-feather-shot/issues/6) | ui | Multi-monitor selection overlay (per-monitor windows) |
| [#7](https://github.com/hjosugi/wayland-feather-shot/issues/7) | clipboard | Bundled holder process to drop the wl-clipboard dependency |
| [#8](https://github.com/hjosugi/wayland-feather-shot/issues/8) | editor | Flatten & blur composite mode |
| [#9](https://github.com/hjosugi/wayland-feather-shot/issues/9) | editor | Text tool upgrades (multi-line, font, outline, reposition) |
| [#10](https://github.com/hjosugi/wayland-feather-shot/issues/10) | editor | Select tool — move/edit committed shapes |
| [#11](https://github.com/hjosugi/wayland-feather-shot/issues/11) | hidpi | Fractional scaling: per-monitor scale-factor pass |
| [#12](https://github.com/hjosugi/wayland-feather-shot/issues/12) | packaging | Flatpak (no network), AUR, deb/rpm |
| [#13](https://github.com/hjosugi/wayland-feather-shot/issues/13) | ui | Pin-to-screen |
| [#14](https://github.com/hjosugi/wayland-feather-shot/issues/14) | performance | Pure-Python stitching speed without numpy |
| [#15](https://github.com/hjosugi/wayland-feather-shot/issues/15) | i18n | Migrate dict-based strings to gettext |
| [#16](https://github.com/hjosugi/wayland-feather-shot/issues/16) | backlog | Capture goodies (history, OCR, QR, exports, CLI, GIF, settings UI) |

Wayland/portal constraints that are *by design* (no portable workaround
exists) are explained inside the relevant issues: global hotkeys are a
compositor decision (#5), apps cannot read off-screen content or inject
input (#1/#3), and Wayland clipboards are owned by a living client (#7).
