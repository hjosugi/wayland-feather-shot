"""Tiny English/Japanese UI localization.

The UI language follows LC_ALL / LC_MESSAGES / LANG (ja* -> Japanese,
anything else -> English).  Set WFS_LANG=en or WFS_LANG=ja to override.
Source strings are English; `_()` looks them up in the Japanese table.
"""

from __future__ import annotations

import os


def _detect_lang() -> str:
    forced = os.environ.get("WFS_LANG")
    if forced in ("en", "ja"):
        return forced
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return "ja" if value.lower().startswith("ja") else "en"
    return "en"


LANG = _detect_lang()

JA = {
    # window titles
    "Feather Shot": "Feather Shot",
    "Scrolling capture — Feather Shot": "スクロールキャプチャ — Feather Shot",
    # tool labels
    "Move": "移動", "Pen": "ペン", "Line": "直線", "Arrow": "矢印",
    "Rect": "矩形", "Ellipse": "楕円", "High": "蛍光", "Text": "文字",
    "Blur": "ぼかし", "Pixel": "モザイク", "Crop": "切抜",
    # tool tooltips
    "Move / resize selection (V)": "選択範囲の移動・リサイズ (V)",
    "Freehand pen (P)": "フリーハンドペン (P)",
    "Straight line (L)": "直線 (L)",
    "Arrow (A)": "矢印 (A)",
    "Rectangle (R)": "四角形 (R)",
    "Ellipse (E)": "楕円 (E)",
    "Highlighter (H)": "蛍光マーカー (H)",
    "Text — click to place (T)": "テキスト — クリックで配置 (T)",
    "Blur region (B)": "ぼかし (B)",
    "Pixelate region (X)": "モザイク (X)",
    "Numbered marker — click (M)": "番号マーカー — クリックで配置 (M)",
    "Numbered marker — click to place (M)": "番号マーカー — クリックで配置 (M)",
    "Crop image (C)": "画像を切り抜き (C)",
    # header/toolbar buttons
    "Annotation color": "注釈の色",
    "Line width": "線の太さ",
    "Undo (Ctrl+Z)": "元に戻す (Ctrl+Z)",
    "Redo (Ctrl+Shift+Z)": "やり直し (Ctrl+Shift+Z)",
    "Save (Ctrl+S)": "保存 (Ctrl+S)",
    "Save as… (Ctrl+Shift+S)": "名前を付けて保存… (Ctrl+Shift+S)",
    "Copy to clipboard (Ctrl+C)": "クリップボードへコピー (Ctrl+C)",
    "Copy to clipboard (Ctrl+C / Enter)":
        "クリップボードへコピー (Ctrl+C / Enter)",
    "Open in editor window (W)": "エディタウィンドウで開く (W)",
    "Cancel (Esc)": "キャンセル (Esc)",
    # toasts / messages
    "Saved  {path}": "保存しました  {path}",
    "Save failed: {error}": "保存に失敗しました: {error}",
    "Copy failed: {error}": "コピーに失敗しました: {error}",
    "Copied to clipboard via {how}": "クリップボードへコピーしました ({how})",
    "Copied — keep this window open while pasting (install wl-clipboard to copy & close)":
        "コピーしました — 貼り付けるまでこのウィンドウを開いたままにしてください"
        "(wl-clipboard を入れるとコピー後すぐ閉じられます)",
    "clipboard (valid while the editor stays open)":
        "クリップボード(エディタを開いている間有効)",
    "Text… (Enter to add)": "テキスト…(Enterで追加)",
    # selector hint
    "Drag: select area   •   Click / Enter: full screen   •   Esc: cancel":
        "ドラッグ: 範囲選択   •   クリック / Enter: 全画面   •   Esc: キャンセル",
    # close confirmation
    "Discard this screenshot?": "このスクリーンショットを破棄しますか?",
    "It has not been saved or copied.": "まだ保存もコピーもされていません。",
    "Cancel": "キャンセル",
    "Discard": "破棄",
    "Save & Close": "保存して閉じる",
    # scroll capture window
    "Choose the window or screen to record\nin the portal dialog…":
        "ポータルのダイアログで、録画するウィンドウ\nまたは画面を選んでください…",
    "frames kept: {n}": "取り込んだフレーム: {n}",
    "Finish && stitch": "終了して合成",
    "Recording.  Scroll the content slowly, top to bottom,\npausing briefly after each scroll.\nThen press “Finish & stitch”  (or Enter).":
        "録画中です。上から下へゆっくりスクロールし、\n"
        "スクロールごとに少し止めてください。\n"
        "終わったら「終了して合成」(または Enter)。",
    "Stitching {n} frames…": "{n} フレームを合成中…",
    "no frames captured — was anything scrolled?":
        "フレームを取得できませんでした — スクロールしましたか?",
    "stitching failed": "合成に失敗しました",
    "cancelled": "キャンセルされました",
    # app-level errors
    "Feather Shot could not capture the screen":
        "Feather Shot は画面をキャプチャできませんでした",
    "portal-hint":
        "xdg-desktop-portal と、お使いのデスクトップ用バックエンド"
        "(gtk / gnome / kde / wlr / hyprland)がインストールされ、"
        "起動していることを確認してから再試行してください。",
    "Quit": "終了",
    "Screenshot portal failed: {error}":
        "スクリーンショットポータルが失敗しました: {error}",
    "Could not read the captured image: {error}":
        "キャプチャ画像を読み込めませんでした: {error}",
    "Scrolling capture needs GStreamer (gst-plugins-base + pipewire plugin) with GObject introspection.":
        "スクロールキャプチャには GStreamer(gst-plugins-base と "
        "pipewire プラグイン、GObject introspection 対応)が必要です。",
    "Scrolling capture failed: {error}":
        "スクロールキャプチャに失敗しました: {error}",
}


def _(text: str) -> str:
    if LANG == "ja":
        return JA.get(text, text)
    return text


def tr(text: str, **kwargs) -> str:
    """Translate then .format()."""
    return _(text).format(**kwargs)
