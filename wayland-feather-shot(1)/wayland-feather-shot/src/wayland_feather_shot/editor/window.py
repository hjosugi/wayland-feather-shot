"""GTK4 screenshot editor.

The editor is deliberately local-only.  Save writes PNG files under the user's
Pictures/Screenshots directory by default; Copy puts an image texture on the
local clipboard.  There is no upload button and no network path.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image

from .. import APP_ID, APP_NAME
from ..image_ops import CanvasState, DrawOp, crop_to_rect
from ..paths import default_screenshot_path

try:
    import cairo
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gio, GLib, Gtk
except Exception as exc:  # pragma: no cover - depends on Linux desktop runtime
    cairo = None
    gi = None
    Gdk = Gio = GLib = Gtk = None
    _GTK_IMPORT_ERROR = exc
else:  # pragma: no cover
    _GTK_IMPORT_ERROR = None


_GTK_WINDOW_BASE = Gtk.ApplicationWindow if Gtk is not None else object
_GTK_APP_BASE = Gtk.Application if Gtk is not None else object


TOOLS = ["pen", "arrow", "line", "rect", "ellipse", "blur", "text", "crop"]
TOOL_LABELS = {
    "pen": "Pen",
    "arrow": "Arrow",
    "line": "Line",
    "rect": "Rect",
    "ellipse": "Ellipse",
    "blur": "Blur",
    "text": "Text",
    "crop": "Crop",
}


def ensure_gtk() -> None:
    if _GTK_IMPORT_ERROR is not None:
        raise RuntimeError(
            "GTK4/PyGObject/Pycairo is not available. Install python3-gi, gir1.2-gtk-4.0, and python3-cairo."
        ) from _GTK_IMPORT_ERROR


def pil_to_cairo_surface(image: Image.Image):
    """Convert PIL RGBA to a Cairo ARGB32 surface.

    Cairo's ARGB32 memory layout is native-endian premultiplied BGRA on common
    little-endian Linux systems.  The conversion keeps a reference to the byte
    buffer on the surface so Cairo can safely paint it.
    """
    rgba = image.convert("RGBA")
    w, h = rgba.size
    src = rgba.tobytes()
    data = bytearray(w * h * 4)
    for i in range(0, len(src), 4):
        r, g, b, a = src[i], src[i + 1], src[i + 2], src[i + 3]
        if a != 255:
            r = (r * a) // 255
            g = (g * a) // 255
            b = (b * a) // 255
        data[i] = b
        data[i + 1] = g
        data[i + 2] = r
        data[i + 3] = a
    surface = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_ARGB32, w, h, w * 4)
    return surface, data


class EditorWindow(_GTK_WINDOW_BASE):
    def __init__(self, app: Gtk.Application, image_path: Path):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(1100, 760)
        self.image_path = Path(image_path)
        self.state = CanvasState(base=Image.open(self.image_path).convert("RGBA"))
        self.redo_stack: list[DrawOp] = []
        self.tool = "pen"
        self.stroke_width = 4
        self.blur_radius = 10
        self.color = (255, 45, 45, 255)
        self.start_point: Optional[tuple[float, float]] = None
        self.current_points: list[tuple[float, float]] = []
        self.preview_op: Optional[DrawOp] = None
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._last_surface = None
        self._last_surface_data = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(6)
        toolbar.set_margin_start(6)
        toolbar.set_margin_end(6)
        root.append(toolbar)

        self.tool_buttons: dict[str, Gtk.ToggleButton] = {}
        for name in TOOLS:
            button = Gtk.ToggleButton(label=TOOL_LABELS[name])
            button.connect("clicked", self.on_tool_clicked, name)
            toolbar.append(button)
            self.tool_buttons[name] = button
        self.tool_buttons[self.tool].set_active(True)

        save = Gtk.Button(label="Save  Ctrl+S")
        save.connect("clicked", lambda *_: self.save_default())
        toolbar.append(save)

        copy = Gtk.Button(label="Copy  Ctrl+C")
        copy.connect("clicked", lambda *_: self.copy_to_clipboard())
        toolbar.append(copy)

        undo = Gtk.Button(label="Undo")
        undo.connect("clicked", lambda *_: self.undo())
        toolbar.append(undo)

        redo = Gtk.Button(label="Redo")
        redo.connect("clicked", lambda *_: self.redo())
        toolbar.append(redo)

        spacer = Gtk.Label(label="")
        spacer.set_hexpand(True)
        toolbar.append(spacer)

        self.status = Gtk.Label(label="Ctrl+S saves PNG / Ctrl+C copies image / Esc closes")
        toolbar.append(self.status)

        self.area = Gtk.DrawingArea()
        self.area.set_hexpand(True)
        self.area.set_vexpand(True)
        self.area.set_draw_func(self.draw)
        root.append(self.area)

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        drag.connect("drag-end", self.on_drag_end)
        self.area.add_controller(drag)

        click = Gtk.GestureClick.new()
        click.connect("pressed", self.on_click)
        self.area.add_controller(click)

        key = Gtk.EventControllerKey.new()
        key.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key)

    def on_tool_clicked(self, button: Gtk.ToggleButton, name: str) -> None:
        if not button.get_active():
            button.set_active(True)
            return
        self.tool = name
        for other_name, other in self.tool_buttons.items():
            if other_name != name:
                other.set_active(False)
        self.status.set_text(f"Tool: {TOOL_LABELS[name]}")

    def render_preview(self) -> Image.Image:
        image = self.state.render()
        if self.preview_op is not None:
            from ..image_ops import apply_op
            apply_op(image, self.preview_op)
        return image

    def draw(self, area: Gtk.DrawingArea, cr, width: int, height: int) -> None:
        image = self.render_preview()
        iw, ih = image.size
        self.scale = min(width / iw, height / ih, 1.0) if iw and ih else 1.0
        draw_w, draw_h = iw * self.scale, ih * self.scale
        self.offset_x = max(0.0, (width - draw_w) / 2)
        self.offset_y = max(0.0, (height - draw_h) / 2)

        cr.save()
        cr.set_source_rgb(0.10, 0.10, 0.10)
        cr.paint()
        cr.translate(self.offset_x, self.offset_y)
        cr.scale(self.scale, self.scale)
        self._last_surface, self._last_surface_data = pil_to_cairo_surface(image)
        cr.set_source_surface(self._last_surface, 0, 0)
        cr.paint()
        cr.restore()

    def view_to_image(self, x: float, y: float) -> tuple[float, float]:
        ix = (x - self.offset_x) / max(self.scale, 0.0001)
        iy = (y - self.offset_y) / max(self.scale, 0.0001)
        w, h = self.state.base.size
        return max(0, min(ix, w)), max(0, min(iy, h))

    def on_drag_begin(self, gesture: Gtk.GestureDrag, x: float, y: float) -> None:
        self.start_point = self.view_to_image(x, y)
        self.current_points = [self.start_point]
        self.preview_op = None

    def on_drag_update(self, gesture: Gtk.GestureDrag, dx: float, dy: float) -> None:
        if self.start_point is None:
            return
        sx, sy = gesture.get_start_point()[1:]
        end = self.view_to_image(sx + dx, sy + dy)
        if self.tool == "pen":
            self.current_points.append(end)
            self.preview_op = DrawOp("pen", self.current_points.copy(), self.color, self.stroke_width)
        elif self.tool == "crop":
            self.preview_op = DrawOp("rect", [self.start_point, end], (255, 255, 255, 255), 2)
        else:
            self.preview_op = DrawOp(
                self.tool,
                [self.start_point, end],
                self.color,
                self.stroke_width,
                radius=self.blur_radius,
            )
        self.area.queue_draw()

    def on_drag_end(self, gesture: Gtk.GestureDrag, dx: float, dy: float) -> None:
        if self.start_point is None:
            return
        sx, sy = gesture.get_start_point()[1:]
        end = self.view_to_image(sx + dx, sy + dy)
        if self.tool == "crop":
            rect_op = DrawOp("crop", [self.start_point, end])
            rendered = self.state.render()
            self.state.base = crop_to_rect(rendered, rect_op.normalized_rect())
            self.state.ops.clear()
            self.redo_stack.clear()
            self.preview_op = None
            self.status.set_text("Cropped")
        elif self.tool != "text":
            op = self.preview_op or DrawOp(self.tool, [self.start_point, end], self.color, self.stroke_width, radius=self.blur_radius)
            self.state.ops.append(op)
            self.redo_stack.clear()
            self.preview_op = None
        self.start_point = None
        self.current_points = []
        self.area.queue_draw()

    def on_click(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        if self.tool != "text" or n_press != 1:
            return
        point = self.view_to_image(x, y)
        self.ask_text(point)

    def ask_text(self, point: tuple[float, float]) -> None:
        dialog = Gtk.Dialog(title="Add text", transient_for=self, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Add", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        entry = Gtk.Entry()
        entry.set_placeholder_text("Text")
        entry.set_activates_default(True)
        box.append(entry)
        dialog.set_default_response(Gtk.ResponseType.OK)

        def on_response(dlg, response):
            if response == Gtk.ResponseType.OK:
                text = entry.get_text()
                if text:
                    self.state.ops.append(DrawOp("text", [point], self.color, self.stroke_width, text=text))
                    self.redo_stack.clear()
                    self.area.queue_draw()
            dlg.destroy()

        dialog.connect("response", on_response)
        dialog.present()

    def on_key_pressed(self, controller, keyval, keycode, state) -> bool:
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if ctrl and keyval in (Gdk.KEY_s, Gdk.KEY_S):
            if shift:
                self.save_as()
            else:
                self.save_default()
            return True
        if ctrl and keyval in (Gdk.KEY_c, Gdk.KEY_C):
            self.copy_to_clipboard()
            return True
        if ctrl and keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            if shift:
                self.redo()
            else:
                self.undo()
            return True
        if ctrl and keyval in (Gdk.KEY_y, Gdk.KEY_Y):
            self.redo()
            return True
        return False

    def undo(self) -> None:
        if not self.state.ops:
            return
        self.redo_stack.append(self.state.ops.pop())
        self.status.set_text("Undo")
        self.area.queue_draw()

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.state.ops.append(self.redo_stack.pop())
        self.status.set_text("Redo")
        self.area.queue_draw()

    def save_default(self) -> Path:
        path = default_screenshot_path("wfs")
        self.state.render().save(path, "PNG")
        self.status.set_text(f"Saved: {path}")
        return path

    def save_as(self) -> None:
        dialog = Gtk.FileChooserNative.new(
            "Save screenshot as PNG",
            self,
            Gtk.FileChooserAction.SAVE,
            "Save",
            "Cancel",
        )
        dialog.set_current_name(default_screenshot_path("wfs").name)
        dialog.set_do_overwrite_confirmation(True)

        def on_response(dlg, response):
            if response == Gtk.ResponseType.ACCEPT:
                file = dlg.get_file()
                if file is not None:
                    path = Path(file.get_path())
                    if path.suffix.lower() != ".png":
                        path = path.with_suffix(".png")
                    self.state.render().save(path, "PNG")
                    self.status.set_text(f"Saved: {path}")
            dlg.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def copy_to_clipboard(self) -> None:
        image = self.state.render()
        tmp = tempfile.NamedTemporaryFile(prefix="wfs_clip_", suffix=".png", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        image.save(tmp_path, "PNG")
        texture = Gdk.Texture.new_from_filename(str(tmp_path))
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set_texture(texture)
        self.status.set_text("Copied image to clipboard")


class EditorApp(_GTK_APP_BASE):
    def __init__(self, image_path: Path):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.image_path = Path(image_path)

    def do_activate(self):
        win = EditorWindow(self, self.image_path)
        win.present()


def run_editor(image_path: Path) -> int:
    ensure_gtk()
    app = EditorApp(Path(image_path))
    return app.run([])
