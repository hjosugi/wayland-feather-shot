#!/usr/bin/env python3
"""Generate gettext catalogs from the embedded translation table.

Writes:
  po/wayland-feather-shot.pot   (template: every source string, empty msgstr)
  po/ja.po                      (Japanese, filled from i18n.JA)

The embedded table in ``i18n.JA`` stays the source of truth for en/ja; this
just exposes those strings to translators in standard PO form.  Run after
changing UI strings:

    python3 scripts/gen-po.py
    msgfmt po/ja.po -o src/wayland_feather_shot/locale/ja/LC_MESSAGES/wayland-feather-shot.mo
"""

import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.i18n import DOMAIN, JA  # noqa: E402

PO_DIR = os.path.join(os.path.dirname(__file__), "..", "po")
LOCALE_DIR = os.path.join(os.path.dirname(__file__), "..", "src",
                          "wayland_feather_shot", "locale")

_MO_HEADER = (
    "Project-Id-Version: wayland-feather-shot\n"
    "MIME-Version: 1.0\n"
    "Content-Type: text/plain; charset=UTF-8\n"
    "Content-Transfer-Encoding: 8bit\n"
    "Language: {lang}\n")


def esc(s: str) -> str:
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t"))


def header(language: str) -> str:
    return (
        'msgid ""\n'
        'msgstr ""\n'
        '"Project-Id-Version: wayland-feather-shot\\n"\n'
        '"MIME-Version: 1.0\\n"\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n'
        '"Content-Transfer-Encoding: 8bit\\n"\n'
        f'"Language: {language}\\n"\n\n')


def write_catalog(path: str, language: str, translated: bool) -> None:
    lines = [header(language)]
    for msgid, msgstr in JA.items():
        value = msgstr if translated else ""
        lines.append(f'msgid "{esc(msgid)}"\n')
        lines.append(f'msgstr "{esc(value)}"\n\n')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(lines))
    print(f"wrote {path} ({len(JA)} strings)")


def write_mo(path: str, lang: str, catalog: dict) -> None:
    """Compile a minimal GNU .mo (no plurals) — avoids needing msgfmt."""
    entries = {"": _MO_HEADER.format(lang=lang)}
    entries.update(catalog)
    keys = sorted(entries, key=lambda k: k.encode("utf-8"))
    n = len(keys)
    key_table_off = 28
    val_table_off = key_table_off + 8 * n
    ids_off = val_table_off + 8 * n

    ids, strs = b"", b""
    kmeta, vmeta = [], []
    for k in keys:
        kb = k.encode("utf-8")
        kmeta.append((len(kb), ids_off + len(ids)))
        ids += kb + b"\x00"
    strs_off = ids_off + len(ids)
    for k in keys:
        vb = entries[k].encode("utf-8")
        vmeta.append((len(vb), strs_off + len(strs)))
        strs += vb + b"\x00"

    out = struct.pack("<Iiiiiii", 0x950412DE, 0, n,
                      key_table_off, val_table_off, 0, 0)
    for length, off in kmeta:
        out += struct.pack("<ii", length, off)
    for length, off in vmeta:
        out += struct.pack("<ii", length, off)
    out += ids + strs

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(out)
    print(f"wrote {path} ({n} strings)")


def main() -> int:
    os.makedirs(PO_DIR, exist_ok=True)
    write_catalog(os.path.join(PO_DIR, "wayland-feather-shot.pot"), "", False)
    write_catalog(os.path.join(PO_DIR, "ja.po"), "ja", True)
    write_mo(os.path.join(LOCALE_DIR, "ja", "LC_MESSAGES", f"{DOMAIN}.mo"),
             "ja", JA)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
