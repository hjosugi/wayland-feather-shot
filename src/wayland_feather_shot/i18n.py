"""UI localization.

Source strings are English.  Lookups go through gettext first — drop a
compiled catalog at ``locale/<lang>/LC_MESSAGES/wayland-feather-shot.mo``
(override the search dir with ``WFS_LOCALEDIR``) and any language works.  The
built-in Japanese table below is the guaranteed fallback, so ``ja`` needs no
catalog and en/ja behave exactly as before.

Language follows LC_ALL / LC_MESSAGES / LANG; ``WFS_LANG`` overrides it and may
be any code (e.g. ``de``), not just en/ja.  See ``po/README.md`` to add one.
"""

from __future__ import annotations

import gettext as _gettext
import os

DOMAIN = "wayland-feather-shot"


def _detect_locale_lang() -> str:
    """Full 2-letter language code for catalog lookup (e.g. 'de', 'ja')."""
    forced = os.environ.get("WFS_LANG")
    if forced:
        return forced.split("_")[0].split(".")[0].lower()
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value and value not in ("C", "POSIX"):
            return value.split("_")[0].split(".")[0].lower()
    return "en"


def _detect_lang() -> str:
    """Which built-in table to use as fallback: 'ja' or 'en'."""
    forced = os.environ.get("WFS_LANG")
    if forced in ("en", "ja"):
        return forced
    return "ja" if LOCALE_LANG == "ja" else "en"


def _localedir() -> str:
    return (os.environ.get("WFS_LOCALEDIR")
            or os.path.join(os.path.dirname(__file__), "locale"))


def _load_catalog(lang: str):
    if not lang:
        return None
    try:
        return _gettext.translation(DOMAIN, _localedir(), languages=[lang])
    except OSError:
        return None  # no catalog for this language; fall back to the table


LOCALE_LANG = _detect_locale_lang()
LANG = _detect_lang()
_catalog = _load_catalog(LOCALE_LANG)

JA = {
    # window titles
    "Feather Shot": "Feather Shot",
    "Scrolling capture — Feather Shot": "スクロールキャプチャ — Feather Shot",
    "Recent screenshots — Feather Shot": "最近のスクリーンショット — Feather Shot",
    "No screenshots yet in {dir}": "{dir} にはまだスクリーンショットがありません",
    "Settings — Feather Shot": "設定 — Feather Shot",
    "Save": "保存",
    "Invalid value for: {keys}": "無効な値: {keys}",
    "Could not save settings: {error}": "設定を保存できませんでした: {error}",
    # tool labels
    "Move": "移動", "Pen": "ペン", "Line": "直線", "Arrow": "矢印",
    "Rect": "矩形", "Ellipse": "楕円", "High": "蛍光", "Text": "文字",
    "Blur": "ぼかし", "Pixel": "モザイク", "Crop": "切抜", "Select": "選択",
    "Step": "手順", "Bubble": "吹出", "Emoji": "絵文字",
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
    "Select / move a shape (V)": "図形を選択・移動 (V)",
    # header/toolbar buttons
    "Annotation color": "注釈の色",
    "Line width": "線の太さ",
    "Colour & width presets": "色と太さのプリセット",
    "Blur/pixelate covers annotations too (flatten)":
        "ぼかし/モザイクで注釈も覆う(フラット化)",
    "Undo (Ctrl+Z)": "元に戻す (Ctrl+Z)",
    "Redo (Ctrl+Shift+Z)": "やり直し (Ctrl+Shift+Z)",
    "Save (Ctrl+S)": "保存 (Ctrl+S)",
    "Save as… (Ctrl+Shift+S)": "名前を付けて保存… (Ctrl+Shift+S)",
    "Copy to clipboard (Ctrl+C)": "クリップボードへコピー (Ctrl+C)",
    "Copy to clipboard (Ctrl+C / Enter)":
        "クリップボードへコピー (Ctrl+C / Enter)",
    "Open in editor window (W)": "エディタウィンドウで開く (W)",
    "Pin to screen (frameless window)": "画面にピン留め(枠なしウィンドウ)",
    "Pin to screen (Ctrl+P)": "画面にピン留め (Ctrl+P)",
    "Cancel (Esc)": "キャンセル (Esc)",
    # toasts / messages
    "Saved  {path}": "保存しました  {path}",
    "Copied path  {path}": "パスをコピーしました  {path}",
    "Save failed: {error}": "保存に失敗しました: {error}",
    "Copy failed: {error}": "コピーに失敗しました: {error}",
    "Copied to clipboard via {how}": "クリップボードへコピーしました ({how})",
    "Copied — keep this window open while pasting (install wl-clipboard to copy & close)":
        "コピーしました — 貼り付けるまでこのウィンドウを開いたままにしてください"
        "(wl-clipboard を入れるとコピー後すぐ閉じられます)",
    "clipboard (valid while the editor stays open)":
        "クリップボード(エディタを開いている間有効)",
    "holder process": "保持プロセス",
    "Text… (Enter to add)": "テキスト…(Enterで追加)",
    "Outline": "縁取り",
    "Background": "背景",
    "Add": "追加",
    "Enter: newline · Ctrl+Enter: add": "Enter: 改行 · Ctrl+Enter: 追加",
    "Text font": "テキストのフォント",
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
    "Auto-scroll unavailable — scroll manually.":
        "自動スクロールは使えません — 手動でスクロールしてください。",
    "Auto-scrolling…  it stops at the bottom.":
        "自動スクロール中…  最下部で停止します。",
    "Preparing…": "準備中…",
    "Choose the area to capture…": "キャプチャする範囲を選んでください…",
    "Drag to select the scrolling area, then press Enter.":
        "スクロールする範囲をドラッグで選び、Enter を押してください。",
    "Use this area": "この範囲を使う",
    "Selection too small — drag a larger area.":
        "範囲が小さすぎます — もっと大きくドラッグしてください。",
    "Scroll a little, then press “Capture frame”.  Frames: {n}":
        "少しスクロールして「フレームを取込」を押してください。 フレーム: {n}",
    "Capture frame": "フレームを取込",
    "Capture at least two frames first.":
        "先に 2 フレーム以上取り込んでください。",
    "Capture failed: {error}": "取り込みに失敗しました: {error}",
    "{n} frame(s) skipped while stitching: {detail}":
        "合成時に {n} フレームをスキップしました: {detail}",
    "scrolled back / overshoot": "上方向スクロール/行き過ぎ",
    "no vertical overlap (horizontal scroll or scene change)":
        "縦の重なりなし(横スクロールまたは画面変化)",
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
    if _catalog is not None:
        translated = _catalog.gettext(text)
        if translated != text:  # the catalog had an entry
            return translated
    if LANG == "ja":
        return JA.get(text, text)
    return text


def tr(text: str, **kwargs) -> str:
    """Translate then .format()."""
    return _(text).format(**kwargs)
