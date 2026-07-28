<!-- i18n: language-switcher -->
[English](README.md) | [日本語](README.ja.md)

# wayland-feather-shot

**Flameshot風のスクリーンショットツール。Wayland専用設計。完全ローカル動作 —
アップロードボタンなし、アカウントなし、テレメトリーなし、ネットワークコードなし。**

Flameshot風のWayland専用スクリーンショットツール。クラウドアップロード機能は
存在しません（ネットワークコード自体がありません）。UIは日本語/英語自動切替。

![tools](data/icons/io.github.hjosugi.WaylandFeatherShot.svg)

## 機能

- **範囲選択＋その場で注釈** — xdg-desktop-portalで画面を凍結し、
  選択範囲をドラッグ（リサイズハンドル付き）、Flameshot風のフローティングツールバーが下に表示されます。
- **ツール**: ペン、直線、矢印、四角形、楕円、ハイライト、テキスト、
  **ぼかし / Blur**、モザイク / Pixelate、自動番号付きマーカー（①②③）、
  クロップ、元に戻す/やり直し、色・線幅選択。
- **Ctrl+S** で `~/Pictures/Screenshots/` に即保存、
  **Ctrl+C** でクリップボードにコピー、**Ctrl+Shift+S** = 名前を付けて保存、
  **Ctrl+O** で保存フォルダを開く、**Esc** でキャンセル、**Enter** = コピーして閉じる。
- **スクロールキャプチャ** — 画面を録画しながら
  *自分で*スクロール（ScreenCast portal + PipeWire）、スクロールごとに一時停止すると自動でフレームを取得し、
  それらを縦長画像に合成します。固定ヘッダー/フッターは自動検出・重複除去。
- **Waylandネイティブ設計**: 全てのキャプチャは
  `org.freedesktop.portal.Screenshot` / `ScreenCast` を経由。X11フォールバックや
  コンポジタ固有のハックなし — GNOME, KDE Plasma, Hyprland, Swayなど
  ポータルバックエンドがあれば動作。
- **デフォルトホットキー: Ctrl+PrtSc**（下記参照）。
- 英語/日本語UI（`LANG`に従う；`WFS_LANG`で上書き可能）。他言語はgettextカタログで追加 — [po/](po/README.md)参照。

## インストール

Arch / CachyOSでは、AURにリリースされたパッケージをインストールできます:

```console
$ yay -S wayland-feather-shot
# または
$ paru -S wayland-feather-shot
```

依存パッケージ（必須はGTK4 + PyGObject + pycairoのみ）:

| ディストリビューション | コマンド |
| --- | --- |
| Arch / CachyOS | `sudo pacman -S --needed python-gobject gtk4 python-cairo wl-clipboard gst-plugins-base gst-plugin-pipewire python-numpy` |
| Debian / Ubuntu | `sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 wl-clipboard gstreamer1.0-pipewire gir1.2-gst-plugins-base-1.0 python3-numpy` |
| Fedora | `sudo dnf install python3-gobject gtk4 python3-cairo wl-clipboard pipewire-gstreamer python3-numpy` |

`wl-clipboard`, GStreamer, numpyはオプションですが推奨です：
`wl-clipboard`はコピーをウィンドウ終了後も保持、GStreamerはスクロールキャプチャを、
numpyは合成を高速化します。

次に:

```console
$ ./install.sh                # ~/.local にユーザーインストール
$ ./install.sh --with-hotkey  # …Ctrl+PrtSc ホットキー登録（GNOMEは自動）
```

`install.sh`でインストールしたファイルを削除するには:

```console
$ wayland-feather-shot updater remove
```

（`pyproject.toml`もあるので、pipが好みなら `pip install .` も可能ですが、
GTK/GStreamerスタック自体はディストリから取得します。）

また、`xdg-desktop-portal`とバックエンドが必要です。主流Waylandデスクトップは
すでに同梱しています（`-gnome`, `-kde`, `-wlr`, `-hyprland`, `-gtk`）。

不足が分からない場合は、組み込み環境チェックを実行してください:

```console
$ wayland-feather-shot diagnose
```

## 使い方

```console
$ wayland-feather-shot            # 範囲キャプチャ（デフォルト）
$ wayland-feather-shot full       # 画面全体をエディタに直接
$ wayland-feather-shot window     # ポータルピッカーでウィンドウ選択
$ wayland-feather-shot scroll     # スクロールキャプチャ（自分でスクロール）
$ wayland-feather-shot scroll --auto  # RemoteDesktopポータルで自動スクロール（実験的）
$ wayland-feather-shot gif        # 範囲をアニメGIF録画
$ wayland-feather-shot edit x.png # 既存画像をエディタで開く
$ wayland-feather-shot history    # 最近のスクリーンショットギャラリー
$ wayland-feather-shot settings   # 設定をウィンドウで編集
$ wayland-feather-shot -d 3 gui   # 3秒遅延
$ wayland-feather-shot daemon     # GlobalShortcutsポータルホットキーデーモン
$ wayland-feather-shot diagnose   # ポータル/GTK/GStreamerの可用性チェック
$ wayland-feather-shot updater remove  # install.sh管理ファイル削除
```

エディタツールバーには**ステップ矢印**（番号付き）、**吹き出し**、
**絵文字ステッカー**、色/線幅**プリセット**、**ぼかし合成**トグル、
`tesseract` / `zbarimg`インストール時は**OCR / QR**抽出（認識テキストをクリップボードへ）。
`Ctrl+Shift+C`で保存ファイルパスコピー、`Ctrl+O`で保存フォルダを開く、
画像は拡張子でPNG/JPEG/WebP/AVIF保存。

### スクリプト

`gui`や`full`は非対話オプションで自動化可能です:

```console
$ wayland-feather-shot full --no-editor                 # 保存、パス出力、終了
$ wayland-feather-shot full --region 0,0,1280,720 -o a.png --no-editor
$ wayland-feather-shot full -o ~/shot.png               # エディタ起動、Ctrl+Sでそのパスに保存
```

`--region X,Y,W,H`でキャプチャ範囲を指定（画面に合わせて調整）、`--output/-o PATH`
でファイル指定（拡張子でPNG/JPEG/WebP）、`--no-editor`でUI省略・保存パス出力。
終了コード: `0` 正常, `1` エラー, `2` 誤用, `130` キャンセル — シェルスクリプト向け。

### 範囲キャプチャ

1. 画面が凍結。ドラッグで選択（クリックまたはEnterで全画面）。
2. 選択範囲上で注釈 — ツールバーキー:
   `V` 移動/リサイズ, `P` ペン, `L` 線, `A` 矢印, `R` 四角, `E` 楕円,
   `H` ハイライト, `T` テキスト, `B` ぼかし, `X` モザイク, `M` 番号マーカー,
   `W` フルエディタウィンドウで開く（クロップ追加）。
3. `Ctrl+S` 保存 • `Ctrl+O` 保存フォルダを開く • `Ctrl+C` / `Enter` コピー •
   `Ctrl+Z` 元に戻す • `Esc` キャンセル。

### スクロールキャプチャ

1. `wayland-feather-shot scroll` — ポータルダイアログでウィンドウ/画面選択。
2. コンテンツをゆっくり上から下へスクロールし、スクロールごとに一瞬止める
   （停止ごとに自動でフレーム取得 — フレームカウンターを確認）。
3. **終了＆合成**を押す。合成された縦長画像がエディタで開く；
   `Ctrl+S` / `Ctrl+C`は通常通り。

ゆっくりスクロールして、スクロールごとに一瞬止めるのがコツです。固定ヘッダー/
フッターは自動検出されて重複除去されます（`~/.config/wayland-feather-shot/config.json`
の `scroll_top_margin` / `scroll_bottom_margin` で手動指定も可能）。

#### 自動スクロール（実験的）

`wayland-feather-shot scroll --auto` — または録画ウィンドウの**自動スクロール**チェック —
`org.freedesktop.portal.RemoteDesktop`ポータル経由でスクロールを自動化します。
**オプションでデフォルトにはなりません**：合成入力にはセッションごとの許可ダイアログが必要なので、
手動スクロールが安全・汎用です。まずポインタをスクロール可能コンテンツ上に置いてください —
ポータルはポインタ位置にスクロールホイールを送ります。自動スクロールはページ下端（新フレームなし）か
`scroll_auto_steps`回で自動停止；`scroll_auto_delta` / `scroll_auto_interval` /
`scroll_auto_steps`は`config.json`で調整可能。GStreamer/PipeWire録画が必要 —
GStreamerなしのフォールバックでは自動化不可。

ポータル対応状況はデスクトップごとに異なります。`wayland-feather-shot diagnose`で
`scroll --auto`が動作するか確認できます:

| デスクトップ | RemoteDesktopポータル | 備考 |
| --- | --- | --- |
| GNOME (Mutter) | 対応 | セッションごとに許可ダイアログ |
| KDE Plasma | 対応 | セッションごとに許可ダイアログ |
| Hyprland / wlroots (`xdg-desktop-portal-wlr`) | 通常非対応 | チェックボックス無効 — 手動スクロール |
| Sway | 通常非対応 | 手動スクロール |

`--auto`はオプションです。RemoteDesktopポータルが必要で、非対応環境では
チェックボックスが無効のまま（手動スクロール）になります。

### デフォルトホットキー: Ctrl+PrtSc

Waylandではアプリがグローバルキーを取得する汎用的な方法は**ありません** —
コンポジタが決定します。2つの仕組みがあり、デスクトップごとに選択します
（または`wayland-feather-shot diagnose`を実行すると、環境検出＆具体的なコマンド表示）:

| デスクトップ | 推奨方法 | 方法 |
| --- | --- | --- |
| GNOME | ネイティブショートカット | `./scripts/setup-hotkey.sh`（gsettings、冪等） |
| GNOME 46+ | ポータルデーモン | 自動起動`wayland-feather-shot daemon` |
| KDE Plasma | ポータルデーモン | 自動起動`wayland-feather-shot daemon`（一度承認） |
| Hyprland | ネイティブショートカット | `bind = CTRL, Print, exec, wayland-feather-shot gui` |
| Sway / wlroots | ネイティブショートカット | `bindsym Ctrl+Print exec wayland-feather-shot gui` |
| その他 | ネイティブショートカット | 設定で`wayland-feather-shot gui`をバインド |

**キーを押しても何も起きない場合**、まずキャプチャ自体が動作するか確認してください:

```console
$ wayland-feather-shot gui        # オーバーレイが開けばキャプチャは正常
$ wayland-feather-shot diagnose   # デスクトップ検出＋バインド方法表示
$ wayland-feather-shot daemon --bind-once   # ポータルバインドをテストして終了
```

`gui`が動作するのにキーが効かない場合はバインド方法の問題です — 上記表を参照。
デーモンは全ての起動と実行コマンドをstderrに記録するので、
ターミナルで`wayland-feather-shot daemon`を実行するとキー押下時の動作が分かります。
ポータルトリガーは`wayland-feather-shot daemon --shortcut SUPER+Print`で上書き可能。

## 設定

`~/.config/wayland-feather-shot/config.json`（初回起動時作成）:
保存ディレクトリ、ファイル名パターン、デフォルト色/線幅、ぼかし強度、
スクロールキャプチャのマージン・制限など。`src/wayland_feather_shot/settings.py`参照。

`save_dir`は空の場合自動：OS/XDGのPicturesディレクトリ
（ローカライズ例：`~/画像`）＋`/Screenshots`。`Ctrl+O`保存フォルダボタンは
この解決済みフォルダを開きます。`save_dir`にパスを指定すると上書き可能。

## トラブルシューティング

まず`wayland-feather-shot diagnose`を実行 — GTK, pycairo,
wl-clipboard, GStreamer/PipeWire, ポータルインターフェースをチェックし、
不足を教えてくれます。

- **何も起きない／ポータルのエラーダイアログ** — `xdg-desktop-portal`と
  デスクトップのバックエンドが起動しているか確認
  （`systemctl --user status xdg-desktop-portal`）。wlroots系では
  `xdg-desktop-portal-wlr` *と* `xdg-desktop-portal-gtk`（ファイル選択用）が必要、
  さらに`XDG_CURRENT_DESKTOP`をセッションにエクスポート。
- **ウィンドウ終了後コピーが消える** — コピーはバンドルホルダープロセス
  （または`wl-copy`インストール時）で保持されるので、ウィンドウ終了後も
  残るはずです。どちらも起動できない場合、UIが「貼り付けまでウィンドウを開いたままに」と表示。
- **GStreamerなしのスクロールキャプチャ** — GStreamer PipeWireプラグイン
  （`gst-plugin-pipewire` / `gstreamer1.0-pipewire`）がない場合、
  `scroll`は手動モードにフォールバック：範囲選択後、スクロールごとに
  *Capture frame*を押します。プラグインをインストールすると自動フレーム取得が可能。

## 開発

```console
$ python3 tests/test_stitcher.py   # 合成エンジンのユニットテスト（GTK不要）
$ python3 tests/test_paths.py      # XDGパス＋診断テスト（GTK不要）
$ ./bin/wayland-feather-shot gui   # リポジトリからインストールなしで実行
```

設計ノートは [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) と
[docs/SECURITY.md](docs/SECURITY.md) にあります。既知の制限やロードマップは
[GitHub issues](https://github.com/hjosugi/wayland-feather-shot/issues)
（概要は [ISSUES.md](ISSUES.md)）で管理。

ライセンス: [MIT](LICENSE)
