"""Unit tests for the editable sidecar document (GTK-free).

Run:  python3 tests/test_editor_sidecar.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.editor import shapes as S  # noqa: E402
from wayland_feather_shot.editor import sidecar  # noqa: E402

STYLE = S.Style(rgba=(0.9, 0.15, 0.12, 1.0), width=4.0, font_size=24.0,
                font_family="Cantarell")


def every_kind():
    """One shape of each kind the editor can produce."""
    return [
        S.Pen([(10, 10), (20, 30), (40, 35)], STYLE),
        S.Line((0, 0), (50, 50), STYLE),
        S.Arrow((5, 5), (80, 40), STYLE),
        S.StepArrow((0, 0), (30, 30), 2, STYLE),
        S.RectShape((10, 10, 100, 50), STYLE),
        S.RectShape((10, 10, 100, 50), STYLE, filled=True),
        S.EllipseShape((0, 0, 40, 40), STYLE),
        S.Highlight((5, 5, 60, 20), STYLE),
        S.Obscure((0, 0, 30, 30), density=0.8, pixelate=True),
        S.Text((12, 14), "日本語 mixed\nsecond line", STYLE),
        S.Marker((60, 60), 3, STYLE),
        S.SpeechBubble((0, 0, 120, 60), "hi", STYLE),
        S.EmojiSticker((7, 8), "🔥", STYLE),
    ]


class RoundTripTests(unittest.TestCase):
    def test_every_kind_survives_a_round_trip(self):
        originals = every_kind()
        restored = sidecar.decode(sidecar.encode(originals)).shapes
        self.assertEqual(len(restored), len(originals))
        for before, after in zip(originals, restored):
            self.assertEqual(before.kind, after.kind)
            self.assertEqual(before.props, after.props)
            self.assertEqual((before.x, before.y), (after.x, after.y))

    def test_the_transform_survives(self):
        shape = S.RectShape((10, 20, 30, 40), STYLE).rotated(0.7, (25, 40))
        restored = sidecar.decode(sidecar.encode([shape])).shapes[0]
        self.assertAlmostEqual(restored.rotation, shape.rotation)
        self.assertAlmostEqual(restored.x, shape.x)
        self.assertAlmostEqual(restored.y, shape.y)

    def test_the_style_survives_in_full(self):
        restored = sidecar.decode(sidecar.encode(
            [S.RectShape((0, 0, 1, 1), STYLE)])).shapes[0]
        self.assertEqual(restored.style, STYLE)

    def test_pen_points_come_back_as_tuples(self):
        restored = sidecar.decode(sidecar.encode(
            [S.Pen([(0, 0), (5, 9)], STYLE)])).shapes[0]
        self.assertEqual(restored.props.points, ((0.0, 0.0), (5.0, 9.0)))

    def test_a_step_arrow_keeps_its_number(self):
        restored = sidecar.decode(sidecar.encode(
            [S.StepArrow((0, 0), (9, 9), 7, STYLE)])).shapes[0]
        self.assertEqual(restored.props.number, 7)

    def test_an_empty_document_round_trips(self):
        self.assertEqual(sidecar.decode(sidecar.encode([])).shapes, ())

    def test_the_document_is_json_serializable(self):
        json.dumps(sidecar.encode(every_kind(), b"\x89PNG..."))


class BaseImageTests(unittest.TestCase):
    def test_the_base_image_round_trips(self):
        payload = bytes(range(256))
        restored = sidecar.decode(sidecar.encode([], payload))
        self.assertEqual(restored.base_png, payload)

    def test_no_base_image_is_not_an_error(self):
        self.assertIsNone(sidecar.decode(sidecar.encode([])).base_png)

    def test_an_empty_base_image_reads_as_absent(self):
        data = sidecar.encode([], b"")
        self.assertIsNone(sidecar.decode(data).base_png)

    def test_a_corrupt_base_image_is_reported(self):
        data = sidecar.encode([], b"payload")
        data["base"]["data"] = "not valid base64!!"
        with self.assertRaises(sidecar.SidecarError):
            sidecar.decode(data)


class CropTests(unittest.TestCase):
    """The crop is stored as a rect over the pristine image, so a reopened
    screenshot can have its crop widened again."""

    def test_the_crop_round_trips(self):
        restored = sidecar.decode(sidecar.encode([], crop=(0.1, 0.2, 0.5, 0.6)))
        self.assertEqual(restored.crop, (0.1, 0.2, 0.5, 0.6))

    def test_a_document_without_a_crop_covers_the_whole_image(self):
        self.assertEqual(sidecar.decode(sidecar.encode([])).crop, (0, 0, 1, 1))

    def test_a_crop_outside_the_image_falls_back_to_the_whole_image(self):
        data = sidecar.encode([])
        data["crop"] = [0.0, 0.0, 5.0, 5.0]
        self.assertEqual(sidecar.decode(data).crop, (0, 0, 1, 1))

    def test_an_empty_crop_falls_back_to_the_whole_image(self):
        data = sidecar.encode([])
        data["crop"] = [0.5, 0.5, 0.0, 0.0]
        self.assertEqual(sidecar.decode(data).crop, (0, 0, 1, 1))

    def test_a_malformed_crop_does_not_take_the_annotations_with_it(self):
        data = sidecar.encode([S.RectShape((0, 0, 9, 9), STYLE)])
        data["crop"] = "nonsense"
        document = sidecar.decode(data)
        self.assertEqual(document.crop, (0, 0, 1, 1))
        self.assertEqual(len(document.shapes), 1)

    def test_the_crop_survives_a_file(self):
        directory = tempfile.mkdtemp()
        try:
            image = os.path.join(directory, "shot.png")
            sidecar.save(image, [S.RectShape((0, 0, 9, 9), STYLE)],
                         crop=(0.25, 0.25, 0.5, 0.5))
            self.assertEqual(sidecar.load(image).crop, (0.25, 0.25, 0.5, 0.5))
        finally:
            shutil.rmtree(directory, ignore_errors=True)


class BackgroundTests(unittest.TestCase):
    """The framing is part of the document, so a composition reopens as it was."""

    def _settings(self):
        from wayland_feather_shot.editor import background as B
        return B.BackgroundSettings(
            fill="gradient", gradient="ocean", padding=0.12, shadow=0.5,
            aspect="16:9", alignment="bottom-right",
            border=B.Border(enabled=True, thickness=0.02),
            watermark=B.Watermark(enabled=True, text="DRAFT", density=3))

    def test_it_round_trips(self):
        restored = sidecar.decode(sidecar.encode([], background=self._settings()))
        self.assertEqual(restored.background, self._settings())

    def test_a_document_without_one_has_no_background(self):
        self.assertEqual(sidecar.decode(sidecar.encode([])).background.fill,
                         "none")

    def test_a_malformed_background_degrades_to_none(self):
        data = sidecar.encode([S.RectShape((0, 0, 9, 9), STYLE)])
        data["background"] = "nonsense"
        document = sidecar.decode(data)
        self.assertEqual(document.background.fill, "none")
        # ...and does not take the annotations with it.
        self.assertEqual(len(document.shapes), 1)

    def test_one_bad_field_does_not_lose_the_rest(self):
        data = sidecar.encode([], background=self._settings())
        data["background"]["padding"] = "wide"
        data["background"]["fill"] = "hologram"
        restored = sidecar.decode(data).background
        self.assertEqual(restored.fill, "none")
        self.assertEqual(restored.gradient, "ocean")

    def test_it_survives_a_file(self):
        directory = tempfile.mkdtemp()
        try:
            image = os.path.join(directory, "shot.png")
            sidecar.save(image, [], background=self._settings())
            self.assertEqual(sidecar.load(image).background, self._settings())
        finally:
            shutil.rmtree(directory, ignore_errors=True)


class ToleranceTests(unittest.TestCase):
    """A document from a newer minor release still has to open."""

    def test_an_unknown_shape_kind_is_skipped(self):
        data = sidecar.encode([S.RectShape((0, 0, 10, 10), STYLE)])
        data["shapes"].append({"kind": "hologram", "x": 0, "y": 0, "props": {}})
        self.assertEqual(len(sidecar.decode(data).shapes), 1)

    def test_an_unknown_field_is_ignored(self):
        data = sidecar.encode([S.RectShape((0, 0, 10, 10), STYLE)])
        data["shapes"][0]["props"]["sparkle"] = True
        self.assertEqual(len(sidecar.decode(data).shapes), 1)

    def test_a_missing_optional_field_falls_back_to_the_default(self):
        data = sidecar.encode([S.Obscure((0, 0, 10, 10), density=0.9)])
        del data["shapes"][0]["props"]["density"]
        restored = sidecar.decode(data).shapes[0]
        self.assertEqual(restored.props.density, S.ObscureProps.density)

    def test_a_malformed_shape_entry_is_skipped(self):
        data = sidecar.encode([S.RectShape((0, 0, 10, 10), STYLE)])
        data["shapes"].insert(0, "not a shape")
        self.assertEqual(len(sidecar.decode(data).shapes), 1)

    def test_a_newer_version_refuses_rather_than_guessing(self):
        data = sidecar.encode([])
        data["version"] = sidecar.SIDECAR_VERSION + 1
        with self.assertRaises(sidecar.UnsupportedVersion):
            sidecar.decode(data)

    def test_a_versionless_document_is_rejected(self):
        with self.assertRaises(sidecar.SidecarError):
            sidecar.decode({"shapes": []})

    def test_a_non_object_document_is_rejected(self):
        with self.assertRaises(sidecar.SidecarError):
            sidecar.decode([1, 2, 3])

    def test_a_document_without_shapes_is_rejected(self):
        with self.assertRaises(sidecar.SidecarError):
            sidecar.decode({"version": sidecar.SIDECAR_VERSION})


class FileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.image = os.path.join(self.dir, "shot.png")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_sidecar_sits_next_to_the_image(self):
        self.assertEqual(sidecar.sidecar_path("/tmp/a/shot.png"),
                         "/tmp/a/shot.png.wfs.json")

    def test_save_then_load(self):
        shapes = every_kind()
        path = sidecar.save(self.image, shapes, b"base-bytes")
        self.assertTrue(os.path.exists(path))
        document = sidecar.load(self.image)
        self.assertEqual(len(document.shapes), len(shapes))
        self.assertEqual(document.base_png, b"base-bytes")
        self.assertEqual(document.base_image, "shot.png")

    def test_saving_leaves_no_temporary_behind(self):
        sidecar.save(self.image, [S.RectShape((0, 0, 5, 5), STYLE)])
        self.assertEqual(sorted(os.listdir(self.dir)), ["shot.png.wfs.json"])

    def test_saving_twice_replaces_the_document(self):
        sidecar.save(self.image, every_kind())
        sidecar.save(self.image, [S.RectShape((0, 0, 5, 5), STYLE)])
        self.assertEqual(len(sidecar.load(self.image).shapes), 1)

    def test_loading_a_missing_sidecar_returns_none(self):
        self.assertIsNone(sidecar.load(self.image))

    def test_loading_invalid_json_is_reported(self):
        with open(sidecar.sidecar_path(self.image), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        with self.assertRaises(sidecar.SidecarError):
            sidecar.load(self.image)

    def test_remove(self):
        sidecar.save(self.image, [S.RectShape((0, 0, 5, 5), STYLE)])
        self.assertTrue(sidecar.remove(self.image))
        self.assertFalse(sidecar.remove(self.image))
        self.assertIsNone(sidecar.load(self.image))

    def test_a_document_with_non_ascii_text_round_trips_through_a_file(self):
        sidecar.save(self.image, [S.Text((0, 0), "秘匿情報 🔥", STYLE)])
        self.assertEqual(sidecar.load(self.image).shapes[0].props.text,
                         "秘匿情報 🔥")


if __name__ == "__main__":
    unittest.main()
