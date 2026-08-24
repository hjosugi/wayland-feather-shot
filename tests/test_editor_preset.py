"""Unit tests for the remembered editor style (GTK-free).

Run:  python3 tests/test_editor_preset.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.editor import preset as P  # noqa: E402


class PresetFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "editor-preset.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, data):
        with open(self.path, "w", encoding="utf-8") as fh:
            if isinstance(data, str):
                fh.write(data)
            else:
                json.dump(data, fh)

    def test_a_round_trip_keeps_every_field(self):
        original = P.EditorPreset(tool="arrow", rgba=(1.0, 0.8, 0.0, 1.0),
                                  width=8.0, font_size=31.0,
                                  font_family="Cantarell",
                                  redaction_density=0.9, spotlight_scrim=0.3,
                                  text_align="center", head_start="dot",
                                  head_end="diamond")
        self.assertTrue(P.save(original, self.path))
        self.assertEqual(P.load(self.path), original)

    def test_no_preset_yet_gives_the_defaults(self):
        self.assertEqual(P.load(os.path.join(self.dir, "absent.json")),
                         P.EditorPreset())

    def test_saving_leaves_no_temporary_behind(self):
        P.save(P.EditorPreset(), self.path)
        self.assertEqual(os.listdir(self.dir), ["editor-preset.json"])

    def test_saving_somewhere_unwritable_does_not_raise(self):
        self.assertFalse(P.save(P.EditorPreset(),
                                os.path.join(self.dir, "no", "\0bad")))

    def test_the_file_is_readable_json(self):
        P.save(P.EditorPreset(text_align="right"), self.path)
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["text_align"], "right")


class ToleranceTests(unittest.TestCase):
    """A preset is a convenience; a bad one must never cost anything."""

    def _decoded(self, data):
        directory = tempfile.mkdtemp()
        try:
            path = os.path.join(directory, "p.json")
            with open(path, "w", encoding="utf-8") as fh:
                if isinstance(data, str):
                    fh.write(data)
                else:
                    json.dump(data, fh)
            return P.load(path)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_invalid_json_falls_back_to_the_defaults(self):
        self.assertEqual(self._decoded("{not json"), P.EditorPreset())

    def test_a_non_object_falls_back(self):
        self.assertEqual(self._decoded([1, 2, 3]), P.EditorPreset())

    def test_one_bad_field_does_not_lose_the_others(self):
        preset = self._decoded({"width": "wide", "text_align": "center"})
        self.assertEqual(preset.width, P.EditorPreset().width)
        self.assertEqual(preset.text_align, "center")

    def test_an_unknown_tool_falls_back(self):
        self.assertEqual(self._decoded({"tool": "teleport"}).tool, "pen")

    def test_a_modal_tool_is_not_restored(self):
        # Reopening straight into crop mode would be a surprise.
        self.assertEqual(self._decoded({"tool": "crop"}).tool, "pen")

    def test_colours_are_clamped(self):
        self.assertEqual(self._decoded({"rgba": [5, -5, 0.5, 2]}).rgba,
                         (1.0, 0.0, 0.5, 1.0))

    def test_a_short_colour_is_ignored(self):
        self.assertEqual(self._decoded({"rgba": [1, 0]}).rgba,
                         P.EditorPreset().rgba)

    def test_numbers_are_clamped_to_something_usable(self):
        preset = self._decoded({"width": 10_000, "font_size": 0.001,
                                "redaction_density": 5,
                                "spotlight_scrim": -3})
        self.assertLessEqual(preset.width, 200.0)
        self.assertGreaterEqual(preset.font_size, 4.0)
        self.assertEqual(preset.redaction_density, 1.0)
        self.assertEqual(preset.spotlight_scrim, 0.0)

    def test_nan_is_rejected(self):
        self.assertEqual(self._decoded('{"width": NaN}').width,
                         P.EditorPreset().width)

    def test_an_unknown_arrowhead_falls_back(self):
        self.assertEqual(self._decoded({"head_end": "harpoon"}).head_end,
                         "arrow")

    def test_a_known_arrowhead_is_kept(self):
        self.assertEqual(self._decoded({"head_end": "diamond"}).head_end,
                         "diamond")

    def test_an_empty_font_family_falls_back(self):
        self.assertEqual(self._decoded({"font_family": "  "}).font_family,
                         "Sans")

    def test_an_unknown_alignment_falls_back(self):
        self.assertEqual(self._decoded({"text_align": "justify"}).text_align,
                         "left")


class SettingsSeedTests(unittest.TestCase):
    class FakeSettings:
        def __init__(self, values):
            self._values = values

        def get(self, key, default=None):
            return self._values.get(key, default)

    def test_the_configured_defaults_seed_the_preset(self):
        preset = P.from_settings(self.FakeSettings({"pen_width": 9,
                                                    "font_size": 40}))
        self.assertEqual(preset.width, 9.0)
        self.assertEqual(preset.font_size, 40.0)

    def test_nonsense_settings_do_not_break_the_seed(self):
        preset = P.from_settings(self.FakeSettings({"pen_width": None}))
        self.assertEqual(preset.width, P.EditorPreset().width)

    def test_the_preset_is_not_the_settings_file(self):
        # Overwriting config.json with wherever the last session ended would
        # make "reset to defaults" meaningless.
        from wayland_feather_shot.settings import CONFIG_PATH
        self.assertNotEqual(P.PRESET_PATH, CONFIG_PATH)


if __name__ == "__main__":
    unittest.main()
