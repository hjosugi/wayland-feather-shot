<!-- i18n: language-switcher -->
[English](ARCHITECTURE.md) | [日本語](ARCHITECTURE.ja.md)

# アーキテクチャ

GTK 4 / PyGObject / cairo アプリケーション。すべての画面関連は xdg-desktop-portal を通過します。X11 のフォールバックやコンポジタ専用プロトコルはありません。

```text
src/wayland_feather_shot/
  cli.py                 引数解析; import-light なので `diagnose` と
                         `--help` は GTK が欠けていても動作します
  app.py                 Gtk.Application、モードディスパッチ (gui/full/scroll/edit/daemon)
  portal.py              非同期ポータルリクエスト/レスポンスヘルパー:
                         スクリーンショット、スクリーンキャスト (+ PipeWire fd)、グローバルショートカット
  select_overlay.py      Flameshotスタイルの全画面オーバーレイ: ドラッグ選択、
                         サイズ変更ハンドル、浮遊注釈ツールバー
  editor/                完全なエディタウィンドウ (キャンバス、ツール、トリミング)
  scrollcap/recorder.py  スクリーンキャスト + GStreamer/PipeWire 録画、
                         ダメージ駆動のフレーム保持
  scrollcap/stitcher.py  GUIなしの垂直ステッチャー (純粋なPython、オプションの
                         numpy 高速パス、スティッキーヘッダー/フッター検出)
  save.py                PNG/JPEG/WebP 保存 + クリップボード (wl-copy が推奨されるので
                         コピーがアプリを超えて生き残る; GDK クリップボードフォールバック)
  settings.py            ~/.config/wayland-feather-shot/config.json
  paths.py               XDG ヘルパー (ローカライズされた画像ディレクトリ、例: ~/画像)
  diagnostics.py         `diagnose` ランタイムチェック、import-light
  i18n.py                辞書ベースの英語/日本語文字列 (LANG / WFS_LANG)
```

## キャプチャフロー

1. `portal.Portal.screenshot()` が `org.freedesktop.portal.Screenshot` を呼び出します
   （非対話的に最初、拒否された場合はポータル対話的に再試行）。
2. `gui` モードはその画像を `select_overlay.OverlayWindow` の下でフリーズさせます;
   注釈は選択に直接行われます。`full` と `edit` はオーバーレイをスキップし、
   `editor.window.EditorWindow` を開きます。
3. 保存/コピーは `save.py` を通じて行われます; ポータルの一時ファイルは削除されます。

## スクロールキャプチャ

`scrollcap.recorder` はスクリーンキャストセッションを開き、ユーザーがスクロールしている間に
PipeWire 経由でフレームを受信し、ポーズごとに1フレームを保持し、生の RGBA バッファを
`scrollcap.stitcher` に供給します。これにより、オーバーラップストリップが整列され、
新たに明らかになった行のみが追加されます。ステッチャーは意図的に GUI なしであり、
ユニットテストされています (`tests/test_stitcher.py`)。

## ショートカット

`app.run_daemon()` は Ctrl+PrtSc (領域)、Ctrl+Shift+PrtSc (スクロール) および
Shift+Ctrl+F12 (全画面) を `org.freedesktop.portal.GlobalShortcuts` を通じてバインドします。
デスクトップがそれを実装している場合; `scripts/setup-hotkey.sh` は
ネイティブデスクトップショートカットで残りをカバーします。

## デザインルール

- ポータルファースト、Waylandファースト; コンポジタのセキュリティモデルを決してバイパスしない
- いかなる種類のネットワークコードもなし (docs/SECURITY.md を参照)
- 重いピクセル作業は可能な限り GTK メインループの外に留める
- ステッチング/診断はテストや壊れた環境のために GTK なしでインポート可能であること