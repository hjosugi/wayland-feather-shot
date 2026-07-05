"""User-assisted scroll capture mode.

The generic mode does not automate scrolling.  Wayland intentionally prevents
one application from freely controlling another application's input or reading
off-screen content.  This mode captures the same on-screen region repeatedly,
while the user scrolls the target app between frames, then stitches the frames.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from PIL import Image

from ..capture.portal import PortalScreenshot
from ..paths import default_screenshot_path
from .stitcher import ScrollStitcher, StitchOptions

try:
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio, Gtk
    from ..editor.window import pil_to_cairo_surface
except Exception:  # pragma: no cover - depends on Linux desktop runtime
    gi = None
    Gio = Gtk = None


_GTK_WINDOW_BASE = Gtk.ApplicationWindow if Gtk is not None else object


Crop = tuple[int, int, int, int]


def parse_crop(value: str | None) -> Crop | None:
    if not value:
        return None
    parts = [int(p.strip()) for p in value.split(",")]
    if len(parts) != 4:
        raise ValueError("crop must be x,y,width,height")
    x, y, w, h = parts
    if w <= 0 or h <= 0:
        raise ValueError("crop width/height must be positive")
    return x, y, w, h


def crop_image(image: Image.Image, crop: Crop | None) -> Image.Image:
    if crop is None:
        return image.convert("RGBA")
    x, y, w, h = crop
    return image.convert("RGBA").crop((x, y, x + w, y + h))


class CropSelector(_GTK_WINDOW_BASE):  # pragma: no cover - GUI runtime
    def __init__(self, app: Gtk.Application, image_path: Path, result: dict):
        super().__init__(application=app, title="Select scroll area")
        self.set_default_size(1100, 760)
        self.image = Image.open(image_path).convert("RGBA")
        self.result = result
        self.start: tuple[float, float] | None = None
        self.end: tuple[float, float] | None = None
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._surface = None
        self._surface_data = None

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(box)
        label = Gtk.Label(label="Drag the scrollable viewport. Press Enter to confirm, Esc to cancel.")
        box.append(label)
        self.area = Gtk.DrawingArea()
        self.area.set_vexpand(True)
        self.area.set_hexpand(True)
        self.area.set_draw_func(self.draw)
        box.append(self.area)

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self.on_begin)
        drag.connect("drag-update", self.on_update)
        drag.connect("drag-end", self.on_end)
        self.area.add_controller(drag)

        key = Gtk.EventControllerKey.new()
        key.connect("key-pressed", self.on_key)
        self.add_controller(key)

    def draw(self, area, cr, width, height):
        iw, ih = self.image.size
        self.scale = min(width / iw, height / ih, 1.0)
        self.offset_x = max(0, (width - iw * self.scale) / 2)
        self.offset_y = max(0, (height - ih * self.scale) / 2)
        cr.set_source_rgb(0.10, 0.10, 0.10)
        cr.paint()
        cr.save()
        cr.translate(self.offset_x, self.offset_y)
        cr.scale(self.scale, self.scale)
        self._surface, self._surface_data = pil_to_cairo_surface(self.image)
        cr.set_source_surface(self._surface, 0, 0)
        cr.paint()
        if self.start and self.end:
            x1, y1 = self.start
            x2, y2 = self.end
            left, right = sorted((x1, x2))
            top, bottom = sorted((y1, y2))
            cr.set_source_rgba(1, 0, 0, 0.25)
            cr.rectangle(left, top, right - left, bottom - top)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.set_line_width(2 / self.scale)
            cr.stroke()
        cr.restore()

    def view_to_image(self, x, y):
        ix = (x - self.offset_x) / max(self.scale, 0.0001)
        iy = (y - self.offset_y) / max(self.scale, 0.0001)
        w, h = self.image.size
        return max(0, min(ix, w)), max(0, min(iy, h))

    def on_begin(self, gesture, x, y):
        self.start = self.view_to_image(x, y)
        self.end = self.start
        self.area.queue_draw()

    def on_update(self, gesture, dx, dy):
        ok, sx, sy = gesture.get_start_point()
        if ok:
            self.end = self.view_to_image(sx + dx, sy + dy)
            self.area.queue_draw()

    def on_end(self, gesture, dx, dy):
        ok, sx, sy = gesture.get_start_point()
        if ok:
            self.end = self.view_to_image(sx + dx, sy + dy)
            self.area.queue_draw()

    def on_key(self, controller, keyval, keycode, state):
        from gi.repository import Gdk
        if keyval == Gdk.KEY_Escape:
            self.result["crop"] = None
            self.close()
            self.get_application().quit()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.confirm()
            return True
        return False

    def confirm(self):
        if not self.start or not self.end:
            return
        x1, y1 = self.start
        x2, y2 = self.end
        left, right = sorted((int(x1), int(x2)))
        top, bottom = sorted((int(y1), int(y2)))
        if right - left >= 10 and bottom - top >= 10:
            self.result["crop"] = (left, top, right - left, bottom - top)
        self.close()
        self.get_application().quit()


def select_crop(image_path: Path) -> Crop | None:  # pragma: no cover - GUI runtime
    if Gtk is None:
        raise RuntimeError("GTK4 is required for interactive crop selection")
    result: dict = {}
    app = Gtk.Application(application_id="io.github.hirosugi41.WaylandFeatherShot.Crop", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def activate(app):
        win = CropSelector(app, image_path, result)
        win.present()

    app.connect("activate", activate)
    app.run([])
    return result.get("crop")


def run_scroll_capture(args: argparse.Namespace) -> Path:
    portal = PortalScreenshot()
    first_path = portal.capture("screen", interactive=True)
    crop = parse_crop(args.crop)
    if crop is None:
        crop = select_crop(first_path)
        if crop is None:
            raise RuntimeError("scroll capture cancelled: no crop selected")

    frames = [crop_image(Image.open(first_path), crop)]
    frame_count = max(1, int(args.frames))
    delay = max(0.0, float(args.delay))

    for idx in range(1, frame_count):
        print(f"Frame {idx + 1}/{frame_count}: scroll the target area now. Capturing in {delay:.1f}s...")
        time.sleep(delay)
        path = portal.capture("screen", interactive=False)
        frames.append(crop_image(Image.open(path), crop))

    stitched, matches = ScrollStitcher(StitchOptions()).stitch(frames)
    output = Path(args.output) if args.output else default_screenshot_path("wfs_scroll")
    stitched.save(output, "PNG")
    sidecar = output.with_suffix(".matches.txt")
    sidecar.write_text("\n".join(f"{i+2}: overlap={m.overlap} score={m.score:.2f} accepted={m.accepted}" for i, m in enumerate(matches)))
    return output
