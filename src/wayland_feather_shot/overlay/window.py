"""Flameshot-style capture overlay.

Wayland does not let arbitrary apps draw over other clients reliably across
compositors, so we do it the robust way: the portal hands us a frozen
full-screen image, we display it fullscreen, and everything happens on that
frozen image — drag-select with resize handles, then annotate in place with
a floating toolbar attached to the selection, then Ctrl+S / Ctrl+C.

This module holds the window, its pointer and key input, the undo history
and the outputs (save, copy, pin, editor). The rest is split by concern into
mixins: view (coordinates, zoom, handles), controls (the bars), text (typing
in place), draw (each frame), extract (OCR, QR, smart redaction), frame
(the background frame) and hand (picking and moving placed shapes).
"""

from __future__ import annotations

import os
import shutil
from typing import Callable, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

import cairo  # noqa: E402

from .. import save as save_mod
from ..editor import background as bg
from ..editor import preset as preset_mod
from ..editor import render
from ..editor import shapes as shape_model
from ..editor.shapes import (EMOJI_CHOICES, Arrow, EllipseShape, EmojiSticker,
                            Highlight, Line, Marker, Obscure, Pen, RectShape,
                            Spotlight, StepArrow, Style)
from ..i18n import _, tr
from ..theme import install_custom_css
from .canvas import OverlayCanvas, OverlayScene
from .controls import OVERLAY_TOOLS, OverlayControlsMixin, menu_popover
from .draw import OverlayDrawMixin
from .extract import OverlayExtractMixin
from .frame import OverlayFrameMixin
from .hand import OverlayHandMixin
from .text import OverlayTextMixin, TextLayer
from .view import ZOOM_MAX, ZOOM_STEP, MonitorView, OverlayViewMixin, Rect

# What other modules and the tests take from here.
__all__ = ["OverlayWindow", "OVERLAY_TOOLS", "ZOOM_MAX"]

TOOL_KEYS = {
    Gdk.KEY_v: "move", Gdk.KEY_p: "pen", Gdk.KEY_l: "line",
    Gdk.KEY_a: "arrow", Gdk.KEY_r: "rect", Gdk.KEY_e: "ellipse",
    Gdk.KEY_h: "highlight", Gdk.KEY_t: "text", Gdk.KEY_b: "blur",
    Gdk.KEY_x: "pixelate", Gdk.KEY_m: "marker", Gdk.KEY_s: "hand",
    Gdk.KEY_g: "steparrow", Gdk.KEY_u: "bubble", Gdk.KEY_o: "spotlight",
    Gdk.KEY_j: "emoji",
}

# Tools that drag out a box, tools that drag from one point to another, and
# tools that act on a click.
RECT_TOOLS = {"rect", "ellipse", "highlight", "blur", "pixelate", "spotlight"}
LINE_TOOLS = {"pen", "line", "arrow", "steparrow"}
CLICK_TOOLS = {"text", "bubble", "marker", "emoji"}


class OverlayWindow(OverlayViewMixin, OverlayControlsMixin, OverlayTextMixin,
                    OverlayDrawMixin, OverlayExtractMixin, OverlayFrameMixin,
                    OverlayHandMixin, Gtk.ApplicationWindow):
    """Fullscreen frozen-image capture UI.

    Everything follows from ``sel``: with no selection the overlay waits for
    one to be dragged out (a click takes the whole screen); with one, the
    toolbar and action bar appear and the tools draw on the screenshot.
    With select_all (the `full` mode, Ctrl+PrtSc) it starts with the whole
    screen selected, so the handles can still cut a part out of it, and
    shows the whole screenshot in one window on the active monitor instead
    of one window per monitor.

    open_editor(pixbuf, shapes) is an optional callback for the "open in
    editor window" button; it receives the cropped base image and the
    annotation shapes translated into its coordinates.

    With remember_style the overlay starts from the style the last session
    (overlay or editor) ended with, and saves its own on closing
    (editor/preset.py). The tests leave it off.

    With copy_on_select (the `copy` mode, Ctrl+Shift+PrtSc) the first
    selection is copied to the clipboard and the overlay closes: selecting
    a region is the whole job.
    """

    def __init__(self, app, pixbuf: GdkPixbuf.Pixbuf, settings,
                 open_editor: Optional[Callable] = None,
                 copy_on_select: bool = False, select_all: bool = False,
                 monitor_layout=None, remember_style: bool = False):
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
        rgba = (rgba.red, rgba.green, rgba.blue, rgba.alpha)
        self._preset = (preset_mod.starting_point(settings, rgba)
                        if remember_style else None)
        if self._preset is not None:
            preset = self._preset
            self._pen_width = float(preset.width)
            self.style = Style(rgba=tuple(preset.rgba),
                               width=self._page_width(self._pen_width),
                               font_size=float(preset.font_size),
                               font_family=preset.font_family)
            self.redaction_density = preset.redaction_density
            self.spotlight_scrim = preset.spotlight_scrim
            self.text_style = preset.text_style
            self.text_align = preset.text_align
            self.arrow_heads = {"head_start": preset.head_start,
                                "head_end": preset.head_end}
        else:
            self._pen_width = float(settings.pen_width)
            self.style = Style(rgba=rgba,
                               width=self._page_width(self._pen_width),
                               font_size=float(settings.font_size))
            self.redaction_density = shape_model.density_from_factor(
                settings.blur_factor)
            self.spotlight_scrim = 0.55  # how dark a spotlight's outside goes
            self.text_style = "plain"    # one of shape_model.TEXT_STYLES
            self.text_align = "left"     # left, center or right
            self.arrow_heads = {"head_start": "none", "head_end": "arrow"}
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
        self._pen_points: List[Tuple[float, float]] = []
        self._preview = None             # the shape being drawn

        # The hand's picked shapes (by sid; Shift/Ctrl+click adds and
        # removes), and while they move: (index, original) for each, lifted
        # out of self.shapes, and how far they have gone.
        self._picked = set()
        self._lifted: List[tuple] = []
        self._lift_offset = (0.0, 0.0)
        self._pick_on_click = None       # what a click without a move does

        # Double-click inside the selection copies it (see _on_click).
        self._copy_first_click = False
        self._copy_press_inside = False

        # Where things are: each MonitorView (view.py) has its own zoom,
        # pan and pointer; these are the monitors' rects for edge snapping.
        self._mon_rects = self._monitor_rects_image()

        self._bars_visible = False
        self._text_edit = None           # {"view", "pos"} while typing
        self._recognizing = False        # an OCR or QR run is going
        self.background = bg.BackgroundSettings()     # no frame
        self._frame_base = None          # (key, shrunk selection) for it
        self._toast_timer = None

        if select_all and monitor_layout is None:
            # The whole picture at a glance: one window, on the monitor the
            # compositor puts it on, fitting every monitor's part.
            monitor_layout = [(None, (0, 0, pixbuf.get_width(),
                                      pixbuf.get_height()))]
        self._build_ui(monitor_layout)
        if self._preset is not None:
            self.connect("close-request",
                         lambda *_: (self._remember_style(), False)[1])
        self.set_decorated(False)
        monitor = self._views[0].monitor
        if monitor is not None:
            self.fullscreen_on_monitor(monitor)
        else:
            self.fullscreen()
        if select_all:
            # Not in the undo history: there is no empty overlay to go back
            # to. The bars are placed again once the window has its size.
            self.sel = (0, 0, pixbuf.get_width(), pixbuf.get_height())
            self._selection_made()

    def _remember_style(self):
        """Save the style for the next session, when it changed; best
        effort (preset.save never raises)."""
        preset = self._preset
        before = preset.to_dict()
        preset.rgba = tuple(self.style.rgba)
        preset.width = self._pen_width
        preset.font_size = self.style.font_size
        preset.font_family = self.style.font_family
        preset.redaction_density = self.redaction_density
        preset.spotlight_scrim = self.spotlight_scrim
        preset.text_style = self.text_style
        preset.text_align = self.text_align
        preset.head_start = self.arrow_heads["head_start"]
        preset.head_end = self.arrow_heads["head_end"]
        if preset.to_dict() != before:
            preset_mod.save(preset)

    # ---------------------------------------------------------------- UI --

    def _build_ui(self, monitor_layout=None):
        """One view per monitor, their input controllers, and the widgets
        laid over the canvases.

        Each view's canvas draws its part of the screenshot, the selection
        and the annotations (see draw.py). Two gestures share its button 1:
        the drag gesture selects, moves, resizes and draws; the click
        gesture places text, bubbles, markers and stickers and turns a
        double-click inside the selection into a copy. The widgets over the
        canvases (the in-place text layer, the toolbar and action bar, the
        toast) exist once and move to the view they are needed in (_place).
        """
        self._bar_rects = ()
        self._action_sizes = None

        self._views = []
        layout = monitor_layout or self._monitor_layout()
        for index, (monitor, rect) in enumerate(layout):
            window = self if index == 0 else self._monitor_window()
            root = Gtk.Overlay()
            window.set_child(root)
            area = OverlayCanvas(self._draw_view,
                                 on_resize=self._on_canvas_resized)
            area.set_cursor(Gdk.Cursor.new_from_name("crosshair"))
            root.set_child(area)
            view = MonitorView(window, root, area, rect, monitor)
            self._views.append(view)
            self._listen(view)
        self._view = self._bars_view = self._text_host = self._views[0]
        self._root = self._views[0].root

        self._install_css()
        self._toolbar = self._build_toolbar()
        self._action_bar = self._build_action_bar()
        for bar in (self._toolbar, self._action_bar):
            self._keep_keys_on_the_overlay(bar)
        self._toast = Gtk.Label()
        self._toast.add_css_class("wfs-toast")
        self._toast.set_halign(Gtk.Align.CENTER)
        self._toast.set_valign(Gtk.Align.END)
        self._toast.set_margin_bottom(48)
        self._toast.set_can_target(False)
        self._toast.set_visible(False)
        self._text_layer = TextLayer()
        self._text_layer.set_visible(False)
        for w in (self._text_layer, self._toolbar, self._action_bar,
                  self._toast):
            self._root.add_overlay(w)
        if len(self._views) > 1:
            # The other monitors' windows come and go with this one: close()
            # (and the window manager) goes through close-request, destroy()
            # through destroy.
            self.connect("map", lambda *_: self._show_monitor_windows())
            self.connect("close-request",
                         lambda *_: (self._close_monitor_windows(), False)[1])
            self.connect("destroy", lambda *_: self._close_monitor_windows())

    def _listen(self, view):
        """Attach the input controllers to *view*'s canvas and window. Each
        handler first makes *view* the current one, so coordinates, cursor
        and zoom are that monitor's."""
        def on(handler):
            def run(*args):
                self._view = view
                return handler(*args)
            return run

        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", on(self._on_drag_begin))
        drag.connect("drag-update", on(self._on_drag_update))
        drag.connect("drag-end", on(self._on_drag_end))
        view.area.add_controller(drag)

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", on(self._on_click_pressed))
        click.connect("released", on(self._on_click))
        view.area.add_controller(click)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", on(self._on_motion))
        view.area.add_controller(motion)

        scroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", on(self._on_scroll))
        view.area.add_controller(scroll)

        pinch = Gtk.GestureZoom()
        pinch.connect("begin", on(self._on_pinch_begin))
        pinch.connect("scale-changed", on(self._on_pinch_scale))
        view.area.add_controller(pinch)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", on(self._on_key))
        view.window.add_controller(keys)

        # GTK gives a new window's focus to its first focusable widget; with
        # the bars already showing (full mode) that is a toolbar button,
        # which would swallow Enter. The overlay takes the keys itself.
        view.window.connect(
            "map", lambda win: GLib.idle_add(self._drop_initial_focus, win))

    def _monitor_window(self):
        """A plain fullscreen window for another monitor's view."""
        window = Gtk.Window(title="Feather Shot")
        window.set_decorated(False)
        # Closing any of the windows closes the capture.
        window.connect("close-request", lambda *_: (self.close(), True)[1])
        return window

    def _show_monitor_windows(self):
        for view in self._views[1:]:
            if view.monitor is not None:
                view.window.fullscreen_on_monitor(view.monitor)
            else:
                view.window.fullscreen()
            view.window.present()

    def _close_monitor_windows(self):
        for view in self._views[1:]:
            view.window.destroy()

    def _draw_view(self, area, snapshot, width, height):
        with self._looking_through(self._view_of(area)):
            self._snapshot(area, snapshot, width, height)

    def _place(self, widget, view):
        """Move one of the widgets laid over the canvases (a bar, the text
        layer, the toast) into *view*'s window."""
        parent = widget.get_parent()
        if parent is view.root:
            return
        if parent is not None:
            parent.remove_overlay(widget)
        view.root.add_overlay(widget)

    def _drop_initial_focus(self, window):
        if self._text_edit is None:
            window.set_focus(None)
        return False

    def _on_canvas_resized(self, _width, _height):
        # The bars sit around the selection in widget pixels; a selection
        # made before the window had its size (full mode) is placed now.
        if self.sel is not None and self._bars_visible:
            self._update_control_layout()

    def _install_css(self):
        install_custom_css()      # once per display; a no-op after that

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
        self._redraw()

    # ------------------------------------------------------------- input --

    def _on_drag_begin(self, gesture, x, y):
        """Decide what this drag does, from where it starts and the tool.

        With nothing selected it starts the selection. With a selection: a
        handle resizes it, the hand picks up the shape under the pointer
        (with the other picked shapes), the move tool moves the selection
        (or starts a new one outside it), and the drawing tools draw. The
        press also finishes any text being typed.
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
                self._drag_kind = self._pick(self._shape_at(ix, iy),
                                             self._adds_to_pick(gesture))
            elif self.tool == "move":
                if self._inside_sel(ix, iy):
                    self._drag_kind = "move"
                    self._drag_sel0 = self.sel
                else:
                    self._drag_kind = "select"   # start a fresh selection
                    self._prev_sel = self.sel
                    self._set_bars_visible(False)
            elif self.tool in RECT_TOOLS or self.tool in LINE_TOOLS:
                self._drag_kind = "draw"
                if self.tool == "pen":
                    self._pen_points = [(ix, iy)]
            else:
                self._drag_kind = None
        self._redraw()

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
        self._redraw()

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
        elif kind == "shape":
            self._drop_lifted()
        elif kind in ("move", "resize"):
            if self.sel != self._drag_sel0:
                self._push_history(prev_sel=self._drag_sel0)
            self._update_control_layout()
        self._redraw()

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
        elif kind == "shape":
            self._lift_offset = (ix - sx, iy - sy)

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
            self._preview = Arrow(start, cur, self.style, **self.arrow_heads)
        elif tool == "steparrow":
            self._preview = StepArrow(start, cur,
                                      shape_model.next_number(self.shapes),
                                      self.style, **self.arrow_heads)
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
            elif tool == "spotlight":
                self._preview = Spotlight(rect, scrim=self.spotlight_scrim)

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

        Two clicks inside the selection copy it and close. Otherwise the
        click tools act: text and bubble start typing there, the marker
        places the next number, and emoji offers stickers to place.
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
        if self.sel is None or self.tool not in CLICK_TOOLS:
            return
        ix, iy = self._to_image(x, y)
        if self.tool == "marker":
            self._add_shape(
                Marker((ix, iy), shape_model.next_number(self.shapes),
                       self.style))
        elif self.tool == "emoji":
            self._pick_emoji(x, y, ix, iy)
        else:
            self._begin_text(ix, iy, kind=self.tool)

    def _add_shape(self, shape):
        """Add one finished annotation, as an undo step."""
        self._push_history()
        self.shapes.append(shape)
        self._redraw()

    def _pick_emoji(self, x, y, ix, iy):
        """Offer the stickers at the click; the one picked goes there."""
        grid = Gtk.FlowBox()
        grid.set_max_children_per_line(6)
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        popover = menu_popover(grid)
        popover.set_parent(self.area)
        point = Gdk.Rectangle()
        point.x, point.y, point.width, point.height = int(x), int(y), 1, 1
        popover.set_pointing_to(point)
        popover.connect("closed", lambda p: GLib.idle_add(p.unparent))

        def pick(_button, char):
            popover.popdown()
            self._add_shape(EmojiSticker((ix, iy), char, self.style))

        for char in EMOJI_CHOICES:
            button = Gtk.Button(label=char)
            button.add_css_class("flat")
            button.add_css_class("wfs-emoji")
            button.connect("clicked", pick, char)
            grid.append(button)
        popover.popup()

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
        render.draw_scene(cr, self.pixbuf, self.shapes)
        surface.flush()
        return Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)

    def _hide_for_good(self):
        """Take the overlay off the screen now, ahead of the slow work that
        ends in closing it: the desktop comes back at once instead of after
        the export and the encoding."""
        self._end_text(commit=True)     # the text being typed is kept
        for view in self._views:
            view.window.set_visible(False)
        Gdk.Display.get_default().flush()

    def _show_again(self):
        """Back on screen after _hide_for_good, to say what went wrong."""
        for view in self._views:
            view.window.present()

    def save_and_close(self):
        path = save_mod.timestamp_path(self.settings)
        self._hide_for_good()
        try:
            path = save_mod.save_pixbuf(self._export_result(), path)
        except Exception as e:
            self._show_again()
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
            self._hide_for_good()
            try:
                path = save_mod.save_pixbuf(self._export_result(),
                                            gfile.get_path())
            except Exception as e:
                self._show_again()
                self.toast(tr("Save failed: {error}", error=e))
                return
            print(path)
            self.close()

        dialog.save(self, None, done)

    def copy_and_close(self):
        """Copy the result to the clipboard and close.

        On GNOME the overlay sets the clipboard itself, while it still has
        the keyboard focus, and closes at once (_copy_in_process). With
        wl-copy it goes off the screen first and hands the PNG over. With
        our holder process, or nothing that outlives this one, the copy
        lasts as long as the window, so it stays open.
        """
        if save_mod.compositor_keeps_clipboard():
            self._copy_in_process()
            return
        handing_over = shutil.which("wl-copy") is not None
        if handing_over:
            self._hide_for_good()
        try:
            how = save_mod.copy_pixbuf(self._export_result())
        except Exception as e:
            if handing_over:
                self._show_again()
            self.toast(tr("Copy failed: {error}", error=e))
            return
        if how in ("wl-copy", "holder process"):
            self.close()  # a holder keeps owning the clipboard after we exit
        else:
            self._show_again()
            self.toast(_("Copied — keep this window open while pasting "
                         "(install wl-clipboard to copy & close)"))

    def _copy_in_process(self):
        """Own the clipboard from here and close; see
        save.compositor_keeps_clipboard.

        The picture is made and encoded only when it is first asked for:
        mutter asks at once to keep its copy, by then without a window on
        the screen. The app is held until that has been written, or until
        another client takes the clipboard over.
        """
        self._end_text(commit=True)
        app = self.get_application()
        clipboard = self.get_clipboard()
        app.hold()
        state = {"held": True, "handler": None}

        def let_go():
            if state["held"]:
                state["held"] = False
                if state["handler"] is not None:
                    clipboard.disconnect(state["handler"])
                app.release()

        clipboard.set_content(
            save_mod.lazy_png_content(self._export_result, on_served=let_go))
        state["handler"] = clipboard.connect(
            "notify::local",
            lambda cb, _pspec: None if cb.get_property("local") else let_go())
        self.close()

    def open_save_folder(self):
        try:
            path = save_mod.open_folder(self.settings.save_dir_path)
        except Exception as e:
            self.toast(tr("Open folder failed: {error}", error=e))
            return
        self.toast(tr("Opened save folder  {path}", path=path))

    def pin_to_screen(self):
        from ..editor.pin import PinWindow
        PinWindow(self.get_application(), self._export_result()).present()

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
