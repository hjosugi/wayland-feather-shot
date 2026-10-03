# Translations

The UI strings live in English in the source and are translated through
gettext, with a built-in Japanese table as the guaranteed fallback (so en/ja
work with no catalog installed).

## Files

- `wayland-feather-shot.pot` — template with every source string (generated).
- `ja.po` — Japanese, generated from the embedded table.
- Compiled catalogs load from
  `src/wayland_feather_shot/locale/<lang>/LC_MESSAGES/wayland-feather-shot.mo`
  (override the search dir with `WFS_LOCALEDIR`).

Regenerate the template, `ja.po` and the shipped `ja.mo` after changing UI
strings:

```console
$ python3 scripts/gen-po.py
```

`gen-po.py` compiles the `.mo` itself, so GNU gettext tools are not required
to build. `xgettext` is only needed if you prefer extracting strings from the
source directly.

## Add a language

```console
$ cp po/wayland-feather-shot.pot po/de.po      # then translate each msgstr
$ msgfmt po/de.po -o src/wayland_feather_shot/locale/de/LC_MESSAGES/wayland-feather-shot.mo
$ WFS_LANG=de wayland-feather-shot gui
```

`WFS_LANG` accepts any language code (not just en/ja). A missing or partial
catalog falls back to English (or the embedded Japanese table for `ja`).
