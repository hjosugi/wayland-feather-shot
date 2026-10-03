"""Flameshot-style capture overlay.

Wayland does not let arbitrary apps draw over other clients reliably across
compositors, so we do it the robust way: the portal hands us a frozen
full-screen image, we display it fullscreen, and everything happens on that
frozen image — drag-select with resize handles, then annotate in place with
a floating toolbar attached to the selection, then Ctrl+S / Ctrl+C.

This module holds the window, its pointer and key input, the undo history
and the outputs (save, copy, pin, editor). The rest is split by concern into
mixins: view (coordinates, zoom, handles), controls (the bars), text (typing
in place) and draw (each frame).
"""

from __future__ import annotations

import os
from typing import Callable, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

import cairo  # noqa: E402

from .. import save as save_mod
from ..editor import shapes as shape_model
from ..editor.shapes import (Arrow, EllipseShape, Highlight, Line, Marker,
                            Obscure, Pen, RectShape, Style)
from ..i18n import _, tr
from ..theme import install_custom_css
from .canvas import OverlayCanvas, OverlayScene
from .controls import OVERLAY_TOOLS, OverlayControlsMixin
from .draw import OverlayDrawMixin
from .text import OverlayTextMixin, TextLayer
from .view import ZOOM_MAX, ZOOM_STEP, OverlayViewMixin, Rect

# What other modules and the tests take from here.
__all__ = ["OverlayWindow", "OVERLAY_TOOLS", "ZOOM_MAX"]

TOOL_KEYS = {
    Gdk.KEY_v: "move", Gdk.KEY_p: "pen", Gdk.KEY_l: "line",
    Gdk.KEY_a: "arrow", Gdk.KEY_r: "rect", Gdk.KEY_e: "ellipse",
    Gdk.KEY_h: "highlight", Gdk.KEY_t: "text", Gdk.KEY_b: "blur",
    Gdk.KEY_x: "pixelate", Gdk.KEY_m: "marker", Gdk.KEY_s: "hand",
}

RECT_TOOLS = {"rect", "ellipse", "highlight", "blur", "pixelate"}


class OverlayWindow(OverlayViewMixin, OverlayControlsMixin, OverlayTextMixin,
                    OverlayDrawMixin, Gtk.ApplicationWindow):
    """Fullscreen frozen-image capture UI.

    Everything follows from ``sel``: with no selection the overlay waits for
    one to be dragged out (a click takes the whole screen); with one, the
    toolbar and action bar appear and the tools draw on the screenshot.
    With select_all (the `full` mode, Ctrl+PrtSc) it starts with the whole
    screen selected, so the handles can still cut a part out of it.

    open_editor(pixbuf, shapes) is an optional callback for the "open in
    editor window" button; it receives the cropped base image and the
    annotation shapes translated into its coordinates.

    With copy_on_select (the `copy` mode, Ctrl+Shift+PrtSc) the first
    selection is copied to the clipboard and the overlay closes: selecting
    a region is the whole job.
    """

    def __init__(self, app, pixbuf: GdkPixbuf.Pixbuf, settings,
                 open_editor: Optional[Callable] = None,
                 copy_on_select: bool = False, select_all: bool = False):
        super().__init__(application=app, title="Feather Shot")
        self.pixbuf = pixbuf
        self._scene = OverlayScene(pixbuf)
        self.settings = settings
        self.open_editor = open_editor
        self.copy_on_select = copy_on_select

        # The style new shapes get. The spinner shows the pen width in
        # screen-ish units; Style.width is in image pixels (_page_width).
        rgba = Gdk.RGBA()
        rgba.parse(settings.pen_color)
        self._pen_width = float(settings.pen_width)
        self.style = Style(rgba=(rgba.red, rgba.green, rgba.blue, rgba.alpha),
                           width=self._page_width(self._pen_width),
                           font_size=float(settings.font_size))
        self.redaction_density = shape_model.density_from_factor(
            settings.blur_factor)
        self.text_style = "plain"        # one of shape_model.TEXT_STYLES
        self._size_kind = "width"        # what the spinner sizes: width|text
        self._size_syncing = False       # set while the spinner is re-ranged

        # What the overlay holds: the selection (image coordinates, None
        # until one is made), the annotations, and their undo history.
        self.tool = "move"
        self.sel: Optional[Rect] = None
        self.shapes: List = []
        self._undo: List[tuple] = []     # (selection, shapes) to go back to
        self._redo: List[tuple] = []

        # The drag in progress, if any. _drag_kind says what it does:
        # select, move, resize, draw, shape (the hand), or None.
        self._drag_kind: Optional[str] = None
        self._drag_start_img: Optional[Tuple[float, float]] = None
        self._prev_sel: Optional[Rect] = None   # before a "select" drag
        self._drag_handle: Optional[str] = None
        self._drag_sel0: Optional[Rect] = None  # before a move or resize
        self._drag_shape = None          # (index, original) for the hand
        self._pen_points: List[Tuple[float, float]] = []
        self._preview = None             # the shape being drawn or moved

        # Double-click inside the selection copies it (see _on_click).
        self._copy_first_click = False
        self._copy_press_inside = False

        # The view: zoom 1 means the whole screenshot fits the window; pan
        # is in widget pixels, added to the fitted origin.
        self._mon_rects = self._monitor_rects_image()  # for edge snapping
        self._zoom = 1.0
        self._pan = (0.0, 0.0)
        self._pinch_zoom0 = 1.0          # zoom level when a pinch started
        self._pointer: Optional[Tuple[float, float]] = None

        self._bars_visible = False
        self._text_edit = None           # {"view", "pos"} while typing

        self._build_ui()
        self.set_decorated(False)
        self.fullscreen()
        if select_all:
            # Not in the undo history: there is no empty overlay to go back
            # to. The bars are placed again once the window has its size.
            self.sel = (0, 0, pixbuf.get_width(), pixbuf.get_height())
            self._selection_made()

    # ---------------------------------------------------------------- UI --

    def _build_ui(self):
        """The canvas, its input controllers, and the widgets laid over it.

        The canvas draws the screenshot, the selection and the annotations
        (see draw.py). Two gestures share its button 1: the drag gesture
        selects, moves, resizes and draws; the click gesture places text and
        markers and turns a double-click inside the selection into a copy.
        Over the canvas, in stacking order: the in-place text layer, the
        toolbar and action bar, and the toast.
        """
        self._root = Gtk.Overlay()
        self.set_child(self._root)
        self._bar_rects = ()
        self._action_sizes = None

        self.area = OverlayCanvas(self._snapshot,
                                  on_resize=self._on_canvas_resized)
        self.area.set_cursor(Gdk.Cursor.new_from_name("crosshair"))
        self._root.set_child(self.area)

        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.area.add_controller(drag)

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._on_click_pressed)
        click.connect("released", self._on_click)
        self.area.add_controller(click)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        self.area.add_controller(motion)

        scroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", self._on_scroll)
        self.area.add_controller(scroll)

        pinch = Gtk.GestureZoom()
        pinch.connect("begin", self._on_pinch_begin)
        pinch.connect("scale-changed", self._on_pinch_scale)
        self.area.add_controller(pinch)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        self._install_css()
        self._toolbar = self._build_toolbar()
        self._action_bar = self._build_action_bar()
        for bar in (self._toolbar, self._action_bar):
            self._keep_keys_on_the_overlay(bar)
        # GTK gives a new window's focus to its first focusable widget; with
        # the bars already showing (full mode) that is a toolbar button,
        # which would swallow Enter. The overlay takes the keys itself.
        self.connect("map", lambda *_: GLib.idle_add(self._drop_initial_focus))
        self._toast = Gtk.Label()
        self._toast.add_css_class("wfs-toast")
        self._toast.set_halign(Gtk.Align.CENTER)
        self._toast.set_valign(Gtk.Align.END)
        self._toast.set_margin_bottom(48)
        self._toast.set_visible(False)
        self._text_layer = TextLayer()
        self._text_layer.set_visible(False)
        for w in (self._text_layer, self._toolbar, self._action_bar,
                  self._toast):
            self._root.add_overlay(w)

    def _drop_initial_focus(self):
        if self._text_edit is None:
            self.set_focus(None)
        return False

    def _on_canvas_resized(self, _width, _height):
        # The bars sit around the selection in widget pixels; a selection
        # made before the window had its size (full mode) is placed now.
        if self.sel is not None and self._bars_visible:
            self._update_control_layout()

    def _install_css(self):
        install_custom_css()      # once per display; a no-op after that

    def _shape_at(self, ix, iy) -> Optional[int]:
        """Index of the topmost shape under an image point, within 8 screen px.

        Unlike the editor's select tool, the hand also takes the inside of an
        unfilled frame: grabbing a rectangle by its middle is what people try
        first.
        """
        scale = self._view_params()[0]
        margin = max(3.0, 8.0 / scale)
        for index in range(len(self.shapes) - 1, -1, -1):
            shape = self.shapes[index]
            local = shape.to_local((ix, iy))
            if shape.geometry().hit_test(local, margin, hit_inside=True):
                return index
        return None

    # Wayland cursor-shape hint per resize handle (#16).
    _HANDLE_CURSOR = {
        "nw": "nwse-resize", "se": "nwse-resize",
        "ne": "nesw-resize", "sw": "nesw-resize",
        "n": "ns-resize", "s": "ns-resize",
        "e": "ew-resize", "w": "ew-resize",
    }

    def _on_motion(self, _ctrl, x, y):
        """Track the pointer, and let the cursor say what a press would do:
        resize at a handle, move inside the selection, grab over a shape."""
        self._pointer = (x, y)
        name = "crosshair"
        if self.sel:
            handle = self._handle_at(x, y)
            if handle:
                name = self._HANDLE_CURSOR.get(handle, "crosshair")
            elif (self.tool == "move"
                  and self._inside_sel(*self._to_image(x, y))):
                name = "move"
            elif self.tool == "hand":
                hit = self._shape_at(*self._to_image(x, y))
                name = "grab" if hit is not None else "default"
        cursor = Gdk.Cursor.new_from_name(name, None)
        if cursor is None:
            cursor = Gdk.Cursor.new_from_name("crosshair", None)
        self.area.set_cursor(cursor)

    # ----------------------------------------------------------- history --

    # Default for _push_history's prev_sel: "the selection as it is now".
    # None is taken; it means "no selection" and is a state worth restoring.
    _CURRENT = object()

    def _push_history(self, prev_sel=_CURRENT):
        """Record the state to return to: the shapes as they are now, and the
        selection as it was before the change (*prev_sel*, default: as now)."""
        sel = self.sel if prev_sel is self._CURRENT else prev_sel
        self._undo.append((sel, tuple(self.shapes)))
        if len(self._undo) > 100:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self):
        if self._undo:
            self._redo.append((self.sel, tuple(self.shapes)))
            self.sel, shapes = self._undo.pop()
            self.shapes = list(shapes)
            self._after_history()

    def redo(self):
        if self._redo:
            self._undo.append((self.sel, tuple(self.shapes)))
            self.sel, shapes = self._redo.pop()
            self.shapes = list(shapes)
            self._after_history()

    def _after_history(self):
        # Undo can take the selection away or bring one back; the controls
        # follow the selection.
        if self.sel is None:
            self._set_bars_visible(False)
        else:
            self._set_bars_visible(True)
            self._update_control_layout()
        self.area.queue_draw()

    # ------------------------------------------------------------- input --

    def _on_drag_begin(self, gesture, x, y):
        """Decide what this drag does, from where it starts and the tool.

        With nothing selected it starts the selection. With a selection: a handle resizes
        it, the hand picks up the shape under the pointer, the move tool
        moves the selection (or starts a new one outside it), and the
        drawing tools draw. The press also finishes any text being typed.
        """
        self._end_text(commit=True)
        ix, iy = self._to_image(x, y)
        self._drag_start_img = (ix, iy)
        if self.sel is None:
            self._drag_kind = "select"
            self._prev_sel = None
            self.sel = self._clamp_rect(ix, iy, 1, 1)
        else:
            handle = self._handle_at(x, y)
            if handle:
                self._drag_kind = "resize"
                self._drag_handle = handle
                self._drag_sel0 = self.sel
            elif self.tool == "hand":
                index = self._shape_at(ix, iy)
                if index is None:
                    self._drag_kind = None
                else:
                    # Lift the shape out of the cached composite and draw it
                    # live as the preview while it moves.
                    self._drag_kind = "shape"
                    self._drag_shape = (index, self.shapes[index])
                    self._preview = self.shapes.pop(index)
                    self.area.set_cursor(Gdk.Cursor.new_from_name("grabbing"))
            elif self.tool == "move":
                if self._inside_sel(ix, iy):
                    self._drag_kind = "move"
                    self._drag_sel0 = self.sel
                else:
                    self._drag_kind = "select"   # start a fresh selection
                    self._prev_sel = self.sel
                    self._set_bars_visible(False)
            elif self.tool in RECT_TOOLS or self.tool in ("pen", "line",
                                                          "arrow"):
                self._drag_kind = "draw"
                if self.tool == "pen":
                    self._pen_points = [(ix, iy)]
            else:
                self._drag_kind = None
        self.area.queue_draw()

    def _on_drag_update(self, gesture, dx, dy):
        if self._drag_kind is None or self._drag_start_img is None:
            return
        # Movement means this was not a click: no double-click copy.
        self._copy_first_click = False
        self._copy_press_inside = False
        ok, sx, sy = gesture.get_start_point()
        if not ok:
            return
        ix, iy = self._to_image(sx + dx, sy + dy)
        self._apply_drag(ix, iy)
        self.area.queue_draw()

    def _on_drag_end(self, gesture, dx, dy):
        """Apply the last position and turn the drag into history: a new
        selection, a drawn shape, a moved shape, or a moved/resized
        selection. A drag that changed nothing records nothing."""
        kind, self._drag_kind = self._drag_kind, None
        if kind is None or self._drag_start_img is None:
            return
        ok, sx, sy = gesture.get_start_point()
        if ok:
            ix, iy = self._to_image(sx + dx, sy + dy)
            self._apply_drag(ix, iy)
        preview, self._preview = self._preview, None
        self._pen_points = []
        self._drag_start_img = None

        if kind == "select" and self.sel:
            if self.sel[2] >= 4 and self.sel[3] >= 4:
                self._push_history(prev_sel=self._prev_sel)
            elif self._prev_sel is None:
                # A simple click with nothing selected: grab the whole screen.
                self.sel = (0, 0, self.pixbuf.get_width(),
                            self.pixbuf.get_height())
                self._push_history(prev_sel=None)
            else:
                # A tiny drag outside the selection: keep the previous one.
                self.sel = self._prev_sel
            self._selection_made()
        elif kind == "draw" and preview is not None:
            self._push_history()
            self.shapes.append(preview)
        elif kind == "shape" and self._drag_shape:
            index, original = self._drag_shape
            self._drag_shape = None
            self.shapes.insert(index, original)
            if preview is not None and preview != original:
                self._push_history()
                self.shapes[index] = preview
            self.area.set_cursor(Gdk.Cursor.new_from_name("grab"))
        elif kind in ("move", "resize"):
            if self.sel != self._drag_sel0:
                self._push_history(prev_sel=self._drag_sel0)
            self._update_control_layout()
        self.area.queue_draw()

    def _apply_drag(self, ix, iy):
        """Follow the pointer, now at image point (ix, iy), for the current
        kind of drag. Called on every update and once more at the end."""
        sx, sy = self._drag_start_img
        kind = self._drag_kind
        if kind == "select":
            x0, y0, x1, y1 = min(sx, ix), min(sy, iy), max(sx, ix), max(sy, iy)
            x0, y0, x1, y1 = self._snap_selection(x0, y0, x1, y1,
                                                  thresh=14 / self._zoom)
            self.sel = self._clamp_rect(x0, y0, x1 - x0, y1 - y0)
        elif kind == "move" and self._drag_sel0:
            x, y, w, h = self._drag_sel0
            iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
            nx = max(0, min(int(x + ix - sx), iw - w))
            ny = max(0, min(int(y + iy - sy), ih - h))
            self.sel = (nx, ny, w, h)
            self._update_control_layout()
        elif kind == "resize" and self._drag_sel0:
            x, y, w, h = self._drag_sel0
            x0, y0, x1, y1 = x, y, x + w, y + h
            hd = self._drag_handle
            if "w" in hd:
                x0 = ix
            if "e" in hd:
                x1 = ix
            if "n" in hd:
                y0 = iy
            if "s" in hd:
                y1 = iy
            # Dragging past the opposite edge flips the rectangle instead of
            # pinning it to a one-pixel sliver.
            x0, x1 = min(x0, x1), max(x0, x1)
            y0, y1 = min(y0, y1), max(y0, y1)
            self.sel = self._clamp_rect(x0, y0, max(1, x1 - x0),
                                        max(1, y1 - y0))
            self._update_control_layout()
        elif kind == "draw":
            self._update_preview((ix, iy))
        elif kind == "shape" and self._drag_shape:
            _index, original = self._drag_shape
            self._preview = original.translate(ix - sx, iy - sy)

    def _update_preview(self, cur):
        """The shape the current tool would draw from the drag's start to
        *cur*; it is drawn live and committed when the drag ends."""
        start = self._drag_start_img
        tool = self.tool
        if tool == "pen":
            last = self._pen_points[-1]
            if abs(cur[0] - last[0]) + abs(cur[1] - last[1]) >= 1.0:
                self._pen_points.append(cur)
            self._preview = Pen(tuple(self._pen_points), self.style)
        elif tool == "line":
            self._preview = Line(start, cur, self.style)
        elif tool == "arrow":
            self._preview = Arrow(start, cur, self.style)
        elif tool in RECT_TOOLS:
            rect = shape_model.norm_rect(start[0], start[1], cur[0], cur[1])
            if tool == "rect":
                self._preview = RectShape(rect, self.style)
            elif tool == "ellipse":
                self._preview = EllipseShape(rect, self.style)
            elif tool == "highlight":
                self._preview = Highlight(rect, self.style)
            elif tool == "blur":
                self._preview = Obscure(rect, self.redaction_density,
                                        pixelate=False)
            elif tool == "pixelate":
                self._preview = Obscure(rect, self.redaction_density,
                                        pixelate=True)

    def _copy_hit(self, x, y):
        """Whether a click here can count towards the double-click copy:
        inside the selection, off its handles, with the move tool."""
        return (self.sel is not None and self.tool == "move"
                and self._inside_sel(*self._to_image(x, y))
                and not self._handle_at(x, y))

    def _on_click_pressed(self, gesture, n_press, x, y):
        # A press anywhere finishes the text being typed, as in the editor.
        self._end_text(commit=True)
        if n_press == 1:
            self._copy_first_click = False
        self._copy_press_inside = self._copy_hit(x, y)

    def _on_click(self, gesture, n_press, x, y):
        """A click (press and release without a drag).

        Two clicks inside the selection copy it and close. Otherwise, with
        the text tool a click starts typing there and with the marker tool
        it places the next numbered marker.
        """
        eligible = self._copy_press_inside and self._copy_hit(x, y)
        self._copy_press_inside = False
        if n_press == 1:
            self._copy_first_click = eligible
        elif n_press == 2 and self._copy_first_click and eligible:
            self._copy_first_click = False
            self.copy_and_close()
            return
        else:
            self._copy_first_click = False
        if self.sel is None or self.tool not in ("text", "marker"):
            return
        ix, iy = self._to_image(x, y)
        if self.tool == "marker":
            self._push_history()
            self.shapes.append(
                Marker((ix, iy), shape_model.next_number(self.shapes),
                       self.style))
            self.area.queue_draw()
        else:
            self._begin_text(ix, iy)

    def _on_key(self, _ctrl, keyval, _keycode, state):
        """The overlay's keys (docs/HOTKEYS.md has the full list).

        While text is being typed the text view gets the keys first and
        only Esc reaches here; mid-drag everything but Esc waits.
        """
        if self._text_edit is not None:
            if keyval == Gdk.KEY_Escape:
                # Reached here only when a toolbar control has the focus;
                # Esc still means "cancel the text", not "do nothing".
                self._end_text(commit=False)
                return True
            return False                      # the text view has the keys
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        key = Gdk.keyval_to_lower(keyval)

        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if self._drag_kind is not None:
            # Mid-drag the hand holds its shape out of self.shapes and a
            # preview belongs to the current tool: undo, export or a tool
            # change now would lose or duplicate the shape. Finish first.
            return True
        if not ctrl and keyval in (Gdk.KEY_bracketleft, Gdk.KEY_bracketright):
            self.step_size(1 if keyval == Gdk.KEY_bracketright else -1)
            return True
        if ctrl and keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.zoom_at(ZOOM_STEP)
            return True
        if ctrl and keyval in (Gdk.KEY_minus, Gdk.KEY_underscore,
                               Gdk.KEY_KP_Subtract):
            self.zoom_at(1 / ZOOM_STEP)
            return True
        if ctrl and keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.zoom_reset()
            return True
        if ctrl and keyval in (Gdk.KEY_1, Gdk.KEY_KP_1):
            self.zoom_to_selection()
            return True
        if ctrl and key == Gdk.KEY_s:
            self.save_as() if shift else self.save_and_close()
            return True
        if ctrl and key == Gdk.KEY_c:
            self.copy_and_close()
            return True
        if ctrl and key == Gdk.KEY_o:
            self.open_save_folder()
            return True
        if ctrl and key == Gdk.KEY_z:
            self.redo() if shift else self.undo()
            return True
        if ctrl and key == Gdk.KEY_y:
            self.redo()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.sel is None:
                self.sel = (0, 0, self.pixbuf.get_width(),
                            self.pixbuf.get_height())
                self._push_history(prev_sel=None)
                self._selection_made()
            else:
                self.copy_and_close()
            return True
        if self.sel is not None and not ctrl and not shift:
            if key in TOOL_KEYS:
                self.select_tool(TOOL_KEYS[key])
                return True
            if key == Gdk.KEY_w and self.open_editor:
                self._to_editor()
                return True
        return False

    # ---------------------------------------------------------- selection --

    def _selection_made(self):
        """A selection exists now (new or restored): show the controls.

        There is no separate edit mode; everything the overlay does follows
        from whether ``self.sel`` is set.
        """
        self.select_tool("move")
        self._set_bars_visible(True)
        self._update_control_layout()
        if self.copy_on_select:
            # Copy mode: the selection is the result. Deferred to idle, so
            # the window does not close inside the gesture handler that
            # made the selection.
            GLib.idle_add(lambda: (self.copy_and_close(), False)[1])

    # ------------------------------------------------------------ actions --

    def _export_cropped(self) -> GdkPixbuf.Pixbuf:
        """The selection with its annotations burnt in, at the screenshot's
        full resolution (the zoom does not matter)."""
        # The action bar takes the press that would otherwise have finished
        # the text being typed; it belongs in the result.
        self._end_text(commit=True)
        iw, ih = self.pixbuf.get_width(), self.pixbuf.get_height()
        x, y, w, h = self.sel or (0, 0, iw, ih)
        # Paint the selection only, shifted into place: a small selection on
        # a two-monitor screenshot used to composite the whole image first.
        # A blur still samples the screenshot around it, so its edges match.
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(surface)
        cr.translate(-x, -y)
        Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
        cr.paint()
        for shape in self.shapes:
            shape.draw(cr, self.pixbuf)
        surface.flush()
        return Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)

    def save_and_close(self):
        path = save_mod.timestamp_path(self.settings)
        try:
            path = save_mod.save_pixbuf(self._export_cropped(), path)
        except Exception as e:
            self.toast(tr("Save failed: {error}", error=e))
            return
        print(path)
        self.close()

    def save_as(self):
        dialog = Gtk.FileDialog()
        dialog.set_initial_name(
            os.path.basename(save_mod.timestamp_path(self.settings)))
        dialog.set_initial_folder(
            Gio.File.new_for_path(self.settings.save_dir_path))

        def done(dlg, result):
            try:
                gfile = dlg.save_finish(result)
            except GLib.Error:
                return
            try:
                path = save_mod.save_pixbuf(self._export_cropped(),
                                            gfile.get_path())
            except Exception as e:
                self.toast(tr("Save failed: {error}", error=e))
                return
            print(path)
            self.close()

        dialog.save(self, None, done)

    def copy_and_close(self):
        """Copy the result. Close only when something outlives this
        process to serve the clipboard (wl-copy or our holder process);
        otherwise the copy lasts as long as the window, so it stays open."""
        try:
            how = save_mod.copy_pixbuf(self._export_cropped())
        except Exception as e:
            self.toast(tr("Copy failed: {error}", error=e))
            return
        if how in ("wl-copy", "holder process"):
            self.close()  # a holder keeps owning the clipboard after we exit
        else:
            self.toast(_("Copied — keep this window open while pasting "
                         "(install wl-clipboard to copy & close)"))

    def open_save_folder(self):
        try:
            path = save_mod.open_folder(self.settings.save_dir_path)
        except Exception as e:
            self.toast(tr("Open folder failed: {error}", error=e))
            return
        self.toast(tr("Opened save folder  {path}", path=path))

    def pin_to_screen(self):
        from ..editor.pin import PinWindow
        PinWindow(self.get_application(), self._export_cropped()).present()

    def _to_editor(self):
        """Hand the selection and its annotations to the editor window, in
        the selection's own coordinates, and close the overlay."""
        if not self.open_editor:
            return
        self._end_text(commit=True)
        x, y, _w, _h = self.sel or (0, 0, 0, 0)
        base = (self.pixbuf if self.sel is None
                else self.pixbuf.new_subpixbuf(*self.sel).copy())
        shapes = [s.translate(-x, -y) for s in self.shapes]
        cb, self.open_editor = self.open_editor, None
        cb(base, shapes)
        self.close()
