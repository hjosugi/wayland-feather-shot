"""Pixel regressions for the overlay's mask, retained scene, and window.

Scene tests work without a display; window and renderer tests need GTK to
connect to a display. GPU tests skip only when their renderer cannot initialize.
"""

import math
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import cairo
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("Gsk", "4.0")
    from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gsk, Gtk
    HAVE_GTK = True
except (ImportError, ValueError):
    HAVE_GTK = False

HAVE_DISPLAY = HAVE_GTK and Gdk.Display.get_default() is not None

if HAVE_GTK:
    from wayland_feather_shot.overlay.canvas import (
        OverlayScene, color, dim_outside, rect, warm_up_renderer,
    )
    from wayland_feather_shot.editor.shapes import (
        Arrow, EllipseShape, Highlight, Line, Marker, Obscure, Pen,
        RectShape, Style, Text,
    )

if HAVE_DISPLAY:
    from wayland_feather_shot.overlay.window import OverlayWindow
    from wayland_feather_shot.util.settings import Settings


class PixelImage:
    """Read a rendered surface once, including its native byte order."""

    def __init__(self, surface):
        surface.flush()
        self.width, self.height = surface.get_width(), surface.get_height()
        self.stride = surface.get_stride()
        self.data = bytes(surface.get_data())

    def rgb(self, x, y):
        offset = y * self.stride + x * 4
        indices = (2, 1, 0) if sys.byteorder == "little" else (1, 2, 3)
        return tuple(self.data[offset + index] for index in indices)


def raster(snapshot, width, height, device_scale=1):
    surface = cairo.ImageSurface(
        cairo.FORMAT_ARGB32, math.ceil(width * device_scale),
        math.ceil(height * device_scale),
    )
    surface.set_device_scale(device_scale, device_scale)
    snapshot.to_node().draw(cairo.Context(surface))
    return PixelImage(surface)


def mask_snapshot(selection, device_scale=1):
    snapshot = Gtk.Snapshot()
    snapshot.scale(device_scale, device_scale)
    snapshot.append_color(color(1, 1, 1), rect(0, 0, 80, 60))
    dim_outside(snapshot, 80, 60, selection, .32)
    return snapshot


MASK_CASES = (
    (20.5, 15.5, 60.5, 45.5),
    (0, 0, 30.5, 25.5),
    (49.5, 0, 80, 25.5),
    (0, 34.5, 30.5, 60),
    (49.5, 34.5, 80, 60),
    (0, 0, 80, 60),
    None,
)


def assert_mask_pixels(case, image, selection, device_scale=1):
    """Check coverage away from the selection's antialiased boundary."""
    margin = 1 / device_scale
    for y in range(image.height):
        wy = (y + .5) / device_scale
        for x in range(image.width):
            wx = (x + .5) / device_scale
            if selection is None:
                outside, inside = True, False
            else:
                x0, y0, x1, y1 = selection
                outside = (wx < x0 - margin or wx > x1 + margin
                           or wy < y0 - margin or wy > y1 + margin)
                inside = (x0 + margin < wx < x1 - margin
                          and y0 + margin < wy < y1 - margin)
            if outside:
                for channel in image.rgb(x, y):
                    case.assertAlmostEqual(
                        channel, 173, delta=1, msg=f"Dimmed pixel {(x, y)}",
                    )
            elif inside:
                case.assertEqual(image.rgb(x, y), (255, 255, 255),
                                 f"Selected pixel {(x, y)}")


@unittest.skipUnless(HAVE_GTK, "GTK/Cairo not available")
class OverlayMaskTests(unittest.TestCase):
    def test_selection_stays_bright_at_center_and_four_corners(self):
        for selection in MASK_CASES:
            with self.subTest(selection=selection):
                image = raster(mask_snapshot(selection), 80, 60)
                assert_mask_pixels(self, image, selection)

    def test_fractional_selection_does_not_leave_bright_seams_outside(self):
        image = raster(mask_snapshot((20.5, 15.5, 60.5, 45.5)), 80, 60)
        for x in (5, 75):
            expected = image.rgb(x, 5)
            for y in range(60):
                self.assertEqual(image.rgb(x, y), expected, f"Seam at {(x, y)}")

    def test_mask_coverage_survives_device_scaling(self):
        for device_scale in (1.25, 1.5, 2):
            for selection in MASK_CASES:
                with self.subTest(scale=device_scale, selection=selection):
                    image = raster(mask_snapshot(selection, device_scale),
                                   80 * device_scale, 60 * device_scale)
                    assert_mask_pixels(self, image, selection, device_scale)

    def test_full_screen_selection_has_no_dimmed_strip(self):
        image = raster(mask_snapshot((0, 0, 80, 60)), 80, 60)
        for point in ((0, 0), (79, 0), (0, 59), (79, 59)):
            self.assertEqual(image.rgb(*point), (255, 255, 255))


@unittest.skipUnless(HAVE_GTK, "GTK/Cairo not available")
class OverlaySceneTests(unittest.TestCase):
    def setUp(self):
        self.base = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 80, 60)
        self.base.fill(0xffffffff)
        self.scene = OverlayScene(self.base)

    def render_scene(self, shapes=()):
        snapshot = Gtk.Snapshot()
        bounds = rect(0, 0, self.base.get_width(), self.base.get_height())
        snapshot.append_color(color(0, 0, 0), bounds)
        snapshot.append_texture(self.scene.content(shapes), bounds)
        return raster(snapshot, self.base.get_width(), self.base.get_height())

    def test_completed_scene_is_reused_while_selection_moves(self):
        shapes = [Highlight((5, 5, 20, 20), Style(rgba=(1, 0, 0, 1)))]
        first = self.scene.content(shapes)
        for selection in ((0, 0, 40, 40), (20, 20, 60, 60)):
            snapshot = Gtk.Snapshot()
            snapshot.append_texture(self.scene.content(shapes), rect(0, 0, 80, 60))
            dim_outside(snapshot, 80, 60, selection, .32)
            raster(snapshot, 80, 60)
        self.assertIs(self.scene.content(tuple(shapes)), first)

    def test_undo_and_redo_update_pixels_without_stale_annotations(self):
        shapes = [Highlight((5, 5, 20, 20), Style(rgba=(1, 0, 0, 1)))]
        before = self.render_scene(shapes).rgb(10, 10)
        self.assertEqual(before[0], 255)
        self.assertLess(before[1], 200)
        self.assertEqual(self.render_scene().rgb(10, 10), (255, 255, 255))
        self.assertEqual(self.render_scene(shapes).rgb(10, 10), before)

    def test_texture_keeps_pixbuf_rowstride_and_alpha(self):
        for alpha, fill, expected in ((False, 0xcc6633ff, (204, 102, 51)),
                                      (True, 0xcc663380, (102, 51, 26))):
            with self.subTest(alpha=alpha):
                self.base = GdkPixbuf.Pixbuf.new(
                    GdkPixbuf.Colorspace.RGB, alpha, 8, 7, 5,
                )
                self.base.fill(fill)
                self.scene = OverlayScene(self.base)
                for shapes in ((), (Highlight((2, 1, 2, 2), Style()),)):
                    image = self.render_scene(shapes)
                    for point in ((0, 0), (6, 0), (0, 4), (6, 4)):
                        for actual, want in zip(image.rgb(*point), expected):
                            self.assertAlmostEqual(actual, want, delta=1)

    def test_cached_annotations_preserve_direct_rendering(self):
        pixels = bytes(component for y in range(60) for x in range(80)
                       for component in ((x * 31) % 256, (y * 19) % 256,
                                         ((x + y) * 13) % 256))
        self.base = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(pixels), GdkPixbuf.Colorspace.RGB, False, 8, 80, 60, 240,
        )
        self.scene = OverlayScene(self.base)
        style = Style(rgba=(1, .2, .1, .65), width=4, font_size=14)
        shapes = [Pen(((10, 10), (20, 30), (40, 20)), style),
                  Line((5, 5), (65, 45), style),
                  Arrow((10, 40), (65, 15), style),
                  RectShape((15, 10, 45, 30), style),
                  EllipseShape((15, 10, 45, 30), style),
                  Highlight((5, 5, 45, 35), style),
                  Obscure((10, 15, 35, 30)),
                  Obscure((10, 15, 35, 30), pixelate=True),
                  Text((10, 10), "Test", style), Marker((40, 30), 1, style)]
        for group in [(shape,) for shape in shapes] + [tuple(shapes)]:
            with self.subTest(kinds=[shape.kind for shape in group]):
                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 80, 60)
                cr = cairo.Context(surface)
                Gdk.cairo_set_source_pixbuf(cr, self.base, 0, 0)
                cr.paint()
                for shape in group:
                    shape.draw(cr, self.base)
                expected = PixelImage(surface)
                actual = self.render_scene(group)
                self.assertLessEqual(max(abs(a - b) for a, b in
                                         zip(actual.data, expected.data)), 2)


@unittest.skipUnless(HAVE_DISPLAY, "GTK display unavailable")
class OverlayWindowRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(
            application_id="io.github.wfs.WindowRenderingTests",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        cls.app.register(None)

    def setUp(self):
        self.base = GdkPixbuf.Pixbuf.new(
            GdkPixbuf.Colorspace.RGB, False, 8, 240, 180,
        )
        self.base.fill(0xffffffff)

    def new_window(self, base=None):
        window = OverlayWindow(self.app, base or self.base, Settings())
        self.addCleanup(window.destroy)
        window.area.allocate(240, 180, -1, None)
        return window

    def render_window(self, window, device_scale=1):
        width, height = window.area.get_width(), window.area.get_height()
        snapshot = Gtk.Snapshot()
        with patch.object(window, "_device_scale", return_value=device_scale):
            window._snapshot(window.area, snapshot, width, height)
        return raster(snapshot, width, height, device_scale)

    def test_export_paints_only_the_selection_with_the_same_pixels(self):
        # Reference: composite the whole image, then crop (the old export).
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 200, 150)
        pixels = bytearray(pixbuf.get_pixels())
        stride = pixbuf.get_rowstride()
        for y in range(150):
            for x in range(200):
                o = y * stride + x * 4
                pixels[o:o + 4] = bytes(((x * 7) % 256, (y * 5) % 256,
                                         (x * y) % 256, 255))
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(bytes(pixels)), GdkPixbuf.Colorspace.RGB, True, 8,
            200, 150, stride)
        window = OverlayWindow(self.app, pixbuf, Settings())
        self.addCleanup(window.destroy)
        style = window.style
        window.shapes = [
            Obscure((30, 20, 80, 60), 0.55, pixelate=False),  # crosses the edge
            Text((70, 70), "hi", style),
            Pen(((60, 40), (90, 60), (120, 50)), style),
        ]
        window.sel = (50, 30, 100, 80)

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 150)
        cr = cairo.Context(surface)
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        cr.paint()
        for shape in window.shapes:
            shape.draw(cr, pixbuf)
        surface.flush()
        expected = Gdk.pixbuf_get_from_surface(surface, 0, 0, 200, 150)
        expected = expected.new_subpixbuf(50, 30, 100, 80).copy()

        exported = window._export_cropped()
        self.assertEqual((exported.get_width(), exported.get_height()), (100, 80))

        def rows(pb):   # the crop keeps its parent's row stride; compare pixels
            data, stride = pb.get_pixels(), pb.get_rowstride()
            return [data[r * stride:r * stride + 100 * 4] for r in range(80)]
        self.assertEqual(rows(exported), rows(expected))

    def test_selection_handles_and_hit_positions_survive_scaling(self):
        window = self.new_window()
        window.sel = (60, 45, 120, 90)
        for view_scale in (.5, 1, 1.5):
            window.area.allocate(int(240 * view_scale), int(180 * view_scale),
                                 -1, None)
            for device_scale in (1, 1.25, 1.5, 2):
                with self.subTest(view_scale=view_scale, device_scale=device_scale):
                    image = self.render_window(window, device_scale)
                    # Left midpoint derived from the literal selection fixture.
                    wx, wy = 60 * view_scale, 90 * view_scale
                    red, green, blue = image.rgb(
                        round(wx * device_scale), round(wy * device_scale),
                    )
                    self.assertGreater(blue, green + 80)
                    self.assertGreater(red, green + 60)
                    self.assertEqual(window._handle_at(wx, wy), "w")
                    self.assertEqual(window._to_image(wx, wy), (60, 90))

    def test_letterboxed_image_keeps_black_margins_and_bright_selection(self):
        base = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 240, 120)
        base.fill(0xffffffff)
        window = self.new_window(base)
        window.sel = (30, 20, 180, 80)
        image = self.render_window(window)
        self.assertEqual(image.rgb(20, 5), (0, 0, 0))
        self.assertEqual(image.rgb(120, 100), (255, 255, 255))
        for channel in image.rgb(10, 100):
            self.assertAlmostEqual(channel, 173, delta=1)

    def test_arrow_preview_does_not_clip_its_head_when_scaled(self):
        window = self.new_window()
        window.sel = (0, 0, 240, 180)
        for view_scale in (.5, 1, 1.5):
            width, height = int(240 * view_scale), int(180 * view_scale)
            window.area.allocate(width, height, -1, None)
            for stroke_width in (1, 4, 12):
                for device_scale in (1, 2):
                    with self.subTest(view_scale=view_scale, width=stroke_width,
                                      device_scale=device_scale):
                        window.style = Style(rgba=(1, 0, 0, 1), width=stroke_width)
                        window._preview = Arrow((50, 120), (190, 120), window.style)
                        actual = self.render_window(window, device_scale)
                        surface = cairo.ImageSurface(
                            cairo.FORMAT_ARGB32, math.ceil(width * device_scale),
                            math.ceil(height * device_scale),
                        )
                        surface.set_device_scale(device_scale, device_scale)
                        cr = cairo.Context(surface)
                        cr.set_source_rgb(1, 1, 1)
                        cr.paint()
                        cr.scale(view_scale, view_scale)
                        window._preview.draw(cr, self.base)
                        expected = PixelImage(surface)
                        # Exclude selection controls and the size label.
                        top = max(40, 80 * view_scale)
                        differences = (
                            abs(a - b)
                            for y in range(math.ceil(top * device_scale),
                                           int(160 * view_scale * device_scale))
                            for x in range(int(30 * view_scale * device_scale),
                                           int(210 * view_scale * device_scale))
                            for a, b in zip(actual.rgb(x, y), expected.rgb(x, y))
                        )
                        # Replaying a GSK Cairo node can round edge coverage
                        # differently from drawing directly at device scale.
                        # Clipped arrowheads differ by far more than this.
                        self.assertLessEqual(max(differences), 16)


@unittest.skipUnless(HAVE_DISPLAY, "GTK display unavailable")
class OverlayRendererTests(unittest.TestCase):
    def check_renderer_mask(self, type_name):
        renderer_type = getattr(Gsk, type_name, None)
        if renderer_type is None:
            self.skipTest(f"{type_name} is not included in this GTK build")
        window = Gtk.Window()
        self.addCleanup(window.destroy)
        window.realize()
        renderer = renderer_type()
        try:
            renderer.realize(window.get_surface())
        except GLib.Error as error:
            self.skipTest(f"{type_name} could not initialize: {error}")
        self.addCleanup(renderer.unrealize)
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "mask.png")
            for device_scale in (1, 1.25, 1.5, 2):
                for selection in MASK_CASES:
                    with self.subTest(renderer=type_name, scale=device_scale,
                                      selection=selection):
                        snapshot = mask_snapshot(selection, device_scale)
                        texture = renderer.render_texture(
                            snapshot.to_node(),
                            rect(0, 0, 80 * device_scale, 60 * device_scale),
                        )
                        texture.save_to_png(filename)
                        image = PixelImage(cairo.ImageSurface.create_from_png(filename))
                        assert_mask_pixels(self, image, selection, device_scale)

    def test_cairo_renderer_keeps_mask_coverage(self):
        self.check_renderer_mask("CairoRenderer")

    def test_gl_renderer_keeps_mask_coverage(self):
        self.check_renderer_mask("GLRenderer")

    def test_vulkan_renderer_keeps_mask_coverage(self):
        self.check_renderer_mask("VulkanRenderer")

    def test_the_warm_up_draws_off_screen_and_leaves_no_window(self):
        before = set(Gtk.Window.list_toplevels())
        warm_up_renderer()
        self.assertEqual(set(Gtk.Window.list_toplevels()), before)


if __name__ == "__main__":
    unittest.main()
