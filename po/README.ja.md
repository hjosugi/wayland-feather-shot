<!-- i18n: language-switcher -->
[English](README.md) | [日本語](README.ja.md)

# 翻訳

UIの文字列はソース内で英語で存在し、gettextを通じて翻訳されます。組み込みの日本語テーブルが保証されたフォールバックとして機能します（したがって、en/jaはカタログがインストールされていなくても動作します）。

## ファイル

- `wayland-feather-shot.pot` — すべてのソース文字列を含むテンプレート（生成済み）。
- `ja.po` — 組み込みテーブルから生成された日本語ファイル。
- コンパイルされたカタログは
  `src/wayland_feather_shot/locale/<lang>/LC_MESSAGES/wayland-feather-shot.mo`
  から読み込まれます（`WFS_LOCALEDIR`で検索ディレクトリをオーバーライドできます）。

UIの文字列を変更した後、テンプレート、`ja.po`、および出荷された`ja.mo`を再生成します：

```console
$ python3 scripts/gen-po.py
```

`gen-po.py`は`.mo`自体をコンパイルするため、GNU gettextツールはビルドに必要ありません。`xgettext`は、ソースから直接文字列を抽出したい場合にのみ必要です。

## 言語を追加する

```console
$ cp po/wayland-feather-shot.pot po/de.po      # その後、各msgstrを翻訳します
$ msgfmt po/de.po -o src/wayland_feather_shot/locale/de/LC_MESSAGES/wayland-feather-shot.mo
$ WFS_LANG=de wayland-feather-shot gui
```

`WFS_LANG`は任意の言語コードを受け入れます（en/jaだけではありません）。カタログが欠落しているか部分的な場合は、英語（または`ja`の場合は組み込みの日本語テーブル）にフォールバックします。