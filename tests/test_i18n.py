"""Tests for the gettext-backed localization (no GTK needed).

Run:  python3 tests/test_i18n.py
"""

import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

LOCALE_DIR = os.path.join(os.path.dirname(__file__), "..", "src",
                          "wayland_feather_shot", "locale")


def load_i18n(**env):
    """(Re)import i18n with a controlled environment."""
    for key in ("WFS_LANG", "WFS_LOCALEDIR", "LC_ALL", "LC_MESSAGES", "LANG"):
        os.environ.pop(key, None)
    os.environ.update(env)
    import wayland_feather_shot.i18n as i18n
    return importlib.reload(i18n)


class FallbackTableTests(unittest.TestCase):
    def tearDown(self):
        load_i18n()  # reset to a clean default for other tests

    def test_english_is_identity(self):
        i18n = load_i18n(WFS_LANG="en")
        self.assertEqual(i18n._("Blur"), "Blur")

    def test_japanese_uses_embedded_table(self):
        i18n = load_i18n(WFS_LANG="ja", WFS_LOCALEDIR="/nonexistent")
        self.assertIsNone(i18n._catalog)  # no catalog there
        self.assertEqual(i18n._("Blur"), "ぼかし")

    def test_tr_formats(self):
        i18n = load_i18n(WFS_LANG="en")
        self.assertEqual(i18n.tr("Saved  {path}", path="/x.png"),
                         "Saved  /x.png")


class DetectLocaleLangTests(unittest.TestCase):
    def tearDown(self):
        load_i18n()

    def test_wfs_lang_any_code(self):
        i18n = load_i18n(WFS_LANG="de")
        self.assertEqual(i18n.LOCALE_LANG, "de")
        self.assertEqual(i18n.LANG, "en")  # no built-in de table -> en fallback

    def test_strips_region_and_encoding(self):
        i18n = load_i18n(LANG="de_DE.UTF-8")
        self.assertEqual(i18n.LOCALE_LANG, "de")


class GettextCatalogTests(unittest.TestCase):
    def tearDown(self):
        load_i18n()

    def test_shipped_ja_mo_is_loaded_and_used(self):
        # The committed ja.mo should load and take precedence for ja.
        i18n = load_i18n(WFS_LANG="ja", WFS_LOCALEDIR=LOCALE_DIR)
        self.assertIsNotNone(i18n._catalog)
        self.assertEqual(i18n._("Save (Ctrl+S)"), "保存 (Ctrl+S)")

    def test_catalog_preferred_over_table(self):
        i18n = load_i18n(WFS_LANG="ja")

        class FakeCatalog:
            def gettext(self, msgid):
                return "CATALOG" if msgid == "Blur" else msgid

        i18n._catalog = FakeCatalog()
        self.assertEqual(i18n._("Blur"), "CATALOG")           # from catalog
        self.assertEqual(i18n._("Save (Ctrl+S)"), "保存 (Ctrl+S)")  # table fallback


if __name__ == "__main__":
    unittest.main(verbosity=2)
