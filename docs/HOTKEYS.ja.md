# ホットキー

スクリーンショットツールで「ショートカット」と呼ばれるものは 2 種類あります。

- **グローバルキー**: Ctrl+PrtSc のように、どこからでもキャプチャを起動するキー。
  Wayland ではアプリ自身がキーを掴むことはできず、デスクトップ側が決めます。
- **アプリ内キー**: 範囲オーバーレイやエディタが開いている間に効くキー。

このページは両方を扱います。`wayland-feather-shot diagnose` を実行すると、
デスクトップを検出してそれ用のコマンドをそのまま表示します。

## グローバルキー

Feather Shot には 2 つの仕組みがあり、デスクトップごとにどちらかを選びます。

| 仕組み | 動き方 | 向いている環境 |
| --- | --- | --- |
| ネイティブ設定 | デスクトップ自身のキーボード設定で `wayland-feather-shot gui` を実行する。常駐プロセスは不要。 | GNOME、Hyprland、Sway、その他すべて |
| ポータル daemon | `wayland-feather-shot daemon` が GlobalShortcuts ポータル経由でキーを登録し、常駐する。デスクトップ側の設定画面に表示され、初回に承認を求められることがある。 | KDE Plasma、GNOME 46 以降 |

どちらの仕組みでも既定のキーは同じです。

| キー | 動作 |
| --- | --- |
| Ctrl+PrtSc | 範囲キャプチャ（`gui`） |
| Ctrl+Shift+PrtSc | スクロールキャプチャ（`scroll`） |
| Ctrl+Shift+F12 | 全画面（`full`）、ポータル daemon のみ |

### GNOME

**ネイティブ設定（推奨）。** ヘルパーを一度実行します。

```console
$ ./scripts/setup-hotkey.sh
```

`gsettings` でカスタムショートカットを 2 つ追加します（設定 → キーボード →
カスタムショートカット に「Feather Shot (region)」「Feather Shot (scroll)」として
表示）。何度実行しても安全です。コマンドはインストール済みの
`wayland-feather-shot`、未インストールならこのチェックアウトの
`bin/wayland-feather-shot` になります。戻すには設定画面でその 2 つを削除します。

GNOME は Print、Shift+Print、Alt+Print を自前のスクリーンショット UI に使っています。
Ctrl+Print は既定で空いているので、これが既定キーになっています。

**ポータル daemon（GNOME 46 以降）。** daemon には 2 つ必要です。

1. 常駐していること。パッケージでインストールすると autostart エントリ
   （`io.github.hjosugi.WaylandFeatherShot.Daemon.desktop`）が入り、ログイン時に
   起動します。git チェックアウトからは `scripts/install-desktop-entry.sh --autostart`
   でエントリを入れてから、ログインし直すか `./bin/wayland-feather-shot daemon` で
   一度手動起動します。
2. ポータルが app id を知っていること。Feather Shot は起動時に
   `org.freedesktop.host.portal.Registry`（xdg-desktop-portal 1.18 以降）で app id を
   登録しますが、ポータルはそれを
   `io.github.hjosugi.WaylandFeatherShot.desktop` という名前の desktop エントリが
   見える場所にあるときだけ受け付けます。パッケージなら入っています。
   チェックアウトでは `scripts/install-desktop-entry.sh` が入れます。

GNOME はダイアログなしでキーを割り当てます。daemon が登録したあと、設定 →
キーボード → アプリケーション に表示されます。

### KDE Plasma

Plasma は GlobalShortcuts ポータルを実装しています。daemon を起動し（autostart
エントリがログイン時に行います）、初回のショートカットダイアログを承認すると、
システム設定 → ショートカット → Feather Shot に表示され、そこで変更できます。
手動なら、カスタムショートカットにコマンド `wayland-feather-shot gui`、
キー Ctrl+PrtSc を追加します。

### Hyprland

```ini
# ~/.config/hypr/hyprland.conf
bind = CTRL, Print, exec, wayland-feather-shot gui
bind = CTRL SHIFT, Print, exec, wayland-feather-shot scroll
```

### Sway とその他の wlroots 系

```
# ~/.config/sway/config
bindsym Ctrl+Print exec wayland-feather-shot gui
bindsym Ctrl+Shift+Print exec wayland-feather-shot scroll
```

`xdg-desktop-portal-wlr` は GlobalShortcuts ポータルを実装していないため、
daemon は失敗を報告します。ネイティブ設定を使ってください。

### その他のデスクトップ

デスクトップのキーボード設定で `wayland-feather-shot gui` と
`wayland-feather-shot scroll` を割り当ててください。GlobalShortcuts ポータルを
実装していれば `wayland-feather-shot daemon` も使えます。

### daemon のキーを変える

範囲キャプチャのキーはコマンドラインで、ポータルのトリガー書式で上書きできます。

```console
$ wayland-feather-shot daemon --shortcut "CTRL+SHIFT+s"
```

恒久的に変えるなら autostart エントリの `Exec=` 行を編集するか、登録後に
デスクトップ側のショートカット設定で変更します。

### 動作確認

```console
$ wayland-feather-shot gui                 # キャプチャ自体の確認
$ wayland-feather-shot diagnose            # ポータル、検出したデスクトップ、その設定方法
$ wayland-feather-shot daemon --bind-once  # ポータル経由: キーを登録して終了
$ wayland-feather-shot daemon              # 常駐してキー押下をすべてログに出す
```

フォアグラウンドで動かすと、daemon はキー押下ごとに起動するコマンドをそのまま
表示します。autostart で起動した daemon のログはジャーナルにあります。

```console
$ journalctl --user -b -g "feather-shot daemon"
```

### トラブルシューティング

- **`could not bind shortcuts (... An app id is required)`** — どのアプリからの
  要求かポータルが判別できていません。app id と同名の desktop エントリが無い
  （git チェックアウトなら `scripts/install-desktop-entry.sh` を実行、AppImage を
  別名で統合しているなら `data/` のエントリを正しい名前で入れる）か、
  xdg-desktop-portal が 1.18 より古く Registry が無いかのどちらかです。ネイティブ
  設定にはどちらも不要です。
- **daemon は「shortcuts bound」と言うのにキーが効かない** — daemon が 1 つだけ
  動いているか確認し、ログに `activated` 行が出るか見てください。GNOME では
  設定 → キーボード → アプリケーション に割り当てがあるか、同じキーを使う
  カスタムショートカットが無いかを確認します。
- **Ctrl+PrtSc でデスクトップ標準のスクリーンショットが開く** — デスクトップ側が
  そのキーを使っています。キーボード設定で変更または削除してください。
- **`gui` は動くのにキーが効かない** — 問題はキャプチャではなく割り当ての仕組み
  です。上の自分のデスクトップの節を読み直してください。

## アプリ内キー

### 範囲オーバーレイ（`gui`）

範囲を選ぶ前:

| キー | 動作 |
| --- | --- |
| ドラッグ | 範囲を選ぶ |
| Enter | 画面全体を選んで編集に入る |
| Esc | 終了 |

範囲を選んだあと:

| キー | 動作 |
| --- | --- |
| V | 選択範囲の移動・リサイズ |
| P, L, A | ペン、直線、矢印 |
| R, E, H | 矩形、楕円、蛍光ペン |
| T, M | テキスト（クリックで配置）、番号マーカー（クリックで配置） |
| B, X | ぼかし、モザイク |
| W | 選択範囲をエディタで開く |
| Enter、Ctrl+C、選択範囲内をダブルクリック | クリップボードにコピーして閉じる |
| Ctrl+S | 保存して閉じる |
| Ctrl+Shift+S | 名前を付けて保存 |
| Ctrl+O | 保存フォルダを開く |
| Ctrl+Z、Ctrl+Shift+Z または Ctrl+Y | 元に戻す、やり直す |
| Esc | 保存せずに終了 |

### エディタ（`full`、`edit`、またはオーバーレイの W）

| キー | ツール |
| --- | --- |
| V | 図形の選択・移動 |
| P, L, A, G | ペン、直線、矢印、番号付きステップ矢印 |
| R, E, H, S | 矩形、楕円、蛍光ペン、スポットライト |
| T, U, J | テキスト、吹き出し、絵文字ステッカー |
| B, X, M | ぼかし、モザイク、番号マーカー |
| C | 切り抜き（Enter で確定、Esc で取り消し） |

| キー | 動作 |
| --- | --- |
| Ctrl+S | クイック保存 |
| Ctrl+Shift+S | 名前を付けて保存 |
| Ctrl+C | 画像をクリップボードにコピー |
| Ctrl+Shift+C | 保存したファイルのパスをコピー |
| Ctrl+O | 保存フォルダを開く |
| Ctrl+P | 画像を画面にピン留め |
| Ctrl+Z、Ctrl+Shift+Z または Ctrl+Y | 元に戻す、やり直す |
| Ctrl+A | すべての図形を選択 |
| Ctrl++、Ctrl+- | 拡大、縮小 |
| Ctrl+1、Ctrl+0 | ウィンドウに合わせる、100 % |
| Ctrl+Up、Ctrl+Down | 選択図形を前面へ、背面へ |
| 矢印キー、Shift+矢印キー | 選択を 1 px、10 px 動かす |
| Delete、Backspace | 選択図形を削除 |
| Esc | 閉じる |
