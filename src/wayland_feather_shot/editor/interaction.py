"""The editor's pointer state machine.

Pure Python: no GTK, no cairo.  The canvas turns GTK events into
:class:`PointerInfo` values and asks this module what happens; everything about
*what* a drag means lives here, which is what makes it testable.

A press decides which interaction starts, based on the current tool.  After
that, motion and release dispatch on the **interaction**, not on the tool — so
adding a tool is one branch in :meth:`Editor.pointer_down` plus a renderer,
instead of another arm in five different handlers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

from .document import Document
from .geometry import Box, Point, norm_rect, rotate
from . import shapes as S

DRAG_TOOLS = {"pen", "line", "arrow", "steparrow", "rect", "ellipse",
              "highlight", "blur", "pixelate"}
CLICK_TOOLS = {"text", "marker", "bubble", "emoji"}
BOX_TOOLS = {"rect", "ellipse", "highlight", "blur", "pixelate"}

CORNER_HANDLES = ("nw", "ne", "se", "sw")
EDGE_HANDLES = ("n", "e", "s", "w")
ROTATE_HANDLES = ("rot-nw", "rot-ne", "rot-se", "rot-sw")

# Normalized position of each handle inside the selection frame.
HANDLE_UNIT: Dict[str, Point] = {
    "nw": (0.0, 0.0), "n": (0.5, 0.0), "ne": (1.0, 0.0),
    "e": (1.0, 0.5), "se": (1.0, 1.0), "s": (0.5, 1.0),
    "sw": (0.0, 1.0), "w": (0.0, 0.5),
}
# The point that stays put while a handle is dragged.
HANDLE_ANCHOR: Dict[str, Point] = {
    "nw": (1.0, 1.0), "n": (0.5, 1.0), "ne": (0.0, 1.0),
    "e": (0.0, 0.5), "se": (0.0, 0.0), "s": (0.5, 0.0),
    "sw": (1.0, 0.0), "w": (1.0, 0.5),
}

HANDLE_HIT_RADIUS = 9.0     # widget px
MIN_MARQUEE = 2.0            # page units below which a drag is really a click
ROTATE_HANDLE_OFFSET = 16.0  # widget px outside the corner
ANGLE_SNAP = math.pi / 12    # 15°


def scales_x(handle: str) -> bool:
    return handle not in ("n", "s")


def scales_y(handle: str) -> bool:
    return handle not in ("e", "w")


@dataclass
class Viewport:
    """Where the page sits in the widget."""

    image_size: Tuple[float, float] = (1.0, 1.0)
    scale: float = 1.0
    offset: Point = (0.0, 0.0)

    def to_page(self, wx: float, wy: float) -> Point:
        s = self.scale or 1.0
        return ((wx - self.offset[0]) / s, (wy - self.offset[1]) / s)

    def to_widget(self, p: Point) -> Point:
        s = self.scale or 1.0
        return (p[0] * s + self.offset[0], p[1] * s + self.offset[1])

    def page_distance(self, widget_distance: float) -> float:
        """A widget-space distance in page units, so hit margins and handles
        stay the same size to grab at any zoom level."""
        s = self.scale or 1.0
        return widget_distance / s

    @property
    def image_edge(self) -> float:
        return max(self.image_size)


@dataclass
class PointerInfo:
    widget: Point
    page: Point
    shift: bool = False
    ctrl: bool = False
    alt: bool = False


@dataclass
class SelectionFrame:
    """The box drawn around the selection.

    A lone shape keeps its own rotated frame, so it resizes along its own axes;
    several shapes share an axis-aligned page-space frame.
    """

    box: Box
    origin: Point = (0.0, 0.0)
    rotation: float = 0.0

    def to_page(self, p: Point) -> Point:
        rx, ry = rotate(p, self.rotation)
        return (rx + self.origin[0], ry + self.origin[1])

    def to_frame(self, p: Point) -> Point:
        return rotate((p[0] - self.origin[0], p[1] - self.origin[1]), -self.rotation)

    def unit_point(self, u: float, v: float) -> Point:
        return self.to_page(self.box.point(u, v))

    @property
    def page_corners(self) -> List[Point]:
        return [self.to_page(c) for c in self.box.corners]

    @property
    def page_center(self) -> Point:
        return self.to_page(self.box.center)


# -- interaction states ------------------------------------------------------

@dataclass
class Idle:
    pass


@dataclass
class Drawing:
    sid: str
    origin: Point


@dataclass
class CreatingBox:
    sid: str
    origin: Point


@dataclass
class CreatingArrow:
    sid: str
    origin: Point


@dataclass
class Brushing:
    origin: Point
    additive: bool = False


@dataclass
class Translating:
    origin: Point
    initial: Dict[str, Point]


@dataclass
class Resizing:
    handle: str
    frame: SelectionFrame
    initial: Tuple[S.Shape, ...]


@dataclass
class Rotating:
    center: Point
    start_angle: float
    initial: Tuple[S.Shape, ...]


class Editor:
    """Document + viewport + tool + the in-flight interaction."""

    def __init__(self, document: Optional[Document] = None,
                 style: Optional[S.Style] = None):
        self.doc = document or Document()
        self.viewport = Viewport()
        self.tool = "pen"
        self.style = style or S.Style()
        self.redaction_density = 0.55
        self.state = Idle()
        self.brush: Optional[Box] = None
        self.on_change = None
        # The canvas owns the base image; a snapshot has to carry it, because
        # a composite redaction and a crop change the pixels as well as the
        # shapes and the two have to undo together.
        self.base_provider = None

    # -- style -------------------------------------------------------------

    @property
    def page_style(self) -> S.Style:
        """The active style with its width converted into page units, so the
        same setting looks the same on a 1080p and a 4K capture."""
        return replace(self.style, width=S.page_stroke_width(
            self.style.width, self.viewport.image_edge))

    def _mark_undo(self) -> None:
        self.doc.mark_undo(self.base_provider() if self.base_provider else None)

    def _notify(self):
        if self.on_change:
            self.on_change()

    # -- selection frame ---------------------------------------------------

    @property
    def selection_frame(self) -> Optional[SelectionFrame]:
        selected = self.doc.selected_shapes
        if not selected:
            return None
        if len(selected) == 1:
            shape = selected[0]
            return SelectionFrame(shape.local_bounds, shape.origin, shape.rotation)
        box = S.selection_bounds(selected)
        return SelectionFrame(box) if box else None

    def handle_at(self, widget_point: Point) -> Optional[str]:
        """Which selection handle is under a widget point.

        Tested in widget space so handles stay the same size to grab however
        far the canvas is zoomed.
        """
        frame = self.selection_frame
        if frame is None:
            return None
        for handle, (u, v) in HANDLE_UNIT.items():
            screen = self.viewport.to_widget(frame.unit_point(u, v))
            if math.dist(screen, widget_point) <= HANDLE_HIT_RADIUS:
                return handle
        center = self.viewport.to_widget(frame.page_center)
        for handle, corner in zip(ROTATE_HANDLES, CORNER_HANDLES):
            u, v = HANDLE_UNIT[corner]
            screen = self.viewport.to_widget(frame.unit_point(u, v))
            dx, dy = screen[0] - center[0], screen[1] - center[1]
            length = math.hypot(dx, dy) or 1.0
            out = (screen[0] + dx / length * ROTATE_HANDLE_OFFSET,
                   screen[1] + dy / length * ROTATE_HANDLE_OFFSET)
            if math.dist(out, widget_point) <= HANDLE_HIT_RADIUS:
                return handle
        return None

    def hit_margin(self) -> float:
        return max(3.0, self.viewport.page_distance(8.0))

    # -- press -------------------------------------------------------------

    def pointer_down(self, p: PointerInfo) -> None:
        if self.tool == "select":
            self._begin_select(p)
        elif self.tool == "pen":
            self._begin_pen(p)
        elif self.tool in BOX_TOOLS:
            self._begin_box(p)
        elif self.tool in ("line", "arrow", "steparrow"):
            self._begin_arrow(p)
        self._notify()

    def _begin_select(self, p: PointerInfo) -> None:
        handle = self.handle_at(p.widget)
        frame = self.selection_frame
        if handle and frame:
            self._mark_undo()
            if handle in ROTATE_HANDLES:
                center = frame.page_center
                self.state = Rotating(center, _angle(center, p.page),
                                      tuple(self.doc.shapes))
            else:
                self.state = Resizing(handle, frame, tuple(self.doc.shapes))
            return

        index = S.hit_shape(self.doc.shapes, p.page, self.hit_margin())
        if index is not None:
            sid = self.doc.shapes[index].sid
            if p.shift:
                self.doc.toggle(sid)
            elif sid not in self.doc.selected:
                self.doc.select([sid])
            if self.doc.selected:
                self._mark_undo()
                self.state = Translating(p.page, self._initial_origins())
            return

        # Nothing under the pointer — but the selection's own frame acts as a
        # drag handle, so a hollow shape can be moved from its empty middle.
        if frame and _point_in_polygon(p.page, frame.page_corners):
            self._mark_undo()
            self.state = Translating(p.page, self._initial_origins())
            return

        if not p.shift:
            self.doc.clear_selection()
        self.state = Brushing(p.page, additive=p.shift)
        self.brush = Box(p.page[0], p.page[1], 0.0, 0.0)

    def _initial_origins(self) -> Dict[str, Point]:
        return {s.sid: s.origin for s in self.doc.selected_shapes}

    def _begin_pen(self, p: PointerInfo) -> None:
        self._mark_undo()
        shape = self.doc.add(S.Pen([p.page], self.page_style))
        self.state = Drawing(shape.sid, p.page)

    def _begin_box(self, p: PointerInfo) -> None:
        self._mark_undo()
        rect = (p.page[0], p.page[1], 1.0, 1.0)
        if self.tool == "rect":
            shape = S.RectShape(rect, self.page_style)
        elif self.tool == "ellipse":
            shape = S.EllipseShape(rect, self.page_style)
        elif self.tool == "highlight":
            shape = S.Highlight(rect, self.page_style)
        else:
            shape = S.Obscure(rect, density=self.redaction_density,
                              pixelate=self.tool == "pixelate")
        self.doc.add(shape)
        self.state = CreatingBox(shape.sid, p.page)

    def _begin_arrow(self, p: PointerInfo) -> None:
        self._mark_undo()
        if self.tool == "line":
            shape = S.Line(p.page, p.page, self.page_style)
        elif self.tool == "steparrow":
            shape = S.StepArrow(p.page, p.page,
                                S.next_number(self.doc.shapes), self.page_style)
        else:
            shape = S.Arrow(p.page, p.page, self.page_style)
        self.doc.add(shape)
        self.state = CreatingArrow(shape.sid, p.page)

    # -- move --------------------------------------------------------------

    def pointer_move(self, p: PointerInfo) -> None:
        state = self.state
        if isinstance(state, Idle):
            return
        if isinstance(state, Drawing):
            self._append_pen_point(state, p)
        elif isinstance(state, CreatingBox):
            self._resize_while_creating(state, p)
        elif isinstance(state, CreatingArrow):
            self._update_arrow_end(state, p)
        elif isinstance(state, Brushing):
            self.brush = Box(*norm_rect(state.origin[0], state.origin[1],
                                        p.page[0], p.page[1]))
        elif isinstance(state, Translating):
            self._translate(state, p)
        elif isinstance(state, Resizing):
            self._resize(state, p)
        elif isinstance(state, Rotating):
            self._rotate(state, p)
        self._notify()

    def _append_pen_point(self, state: Drawing, p: PointerInfo) -> None:
        shape = self.doc.shape(state.sid)
        if shape is None:
            return
        local = shape.to_local(p.page)
        points = shape.props.points
        # Skip points on top of the previous one: they add nothing and cost a
        # full redraw.
        if points and math.dist(points[-1], local) < 0.75:
            return
        self.doc.update(replace(shape, props=replace(
            shape.props, points=points + (local,))))

    def _resize_while_creating(self, state: CreatingBox, p: PointerInfo) -> None:
        shape = self.doc.shape(state.sid)
        if shape is None:
            return
        ox, oy = state.origin
        x, y, w, h = norm_rect(ox, oy, p.page[0], p.page[1])
        if p.shift:
            side = max(w, h)
            x = ox - side if p.page[0] < ox else ox
            y = oy - side if p.page[1] < oy else oy
            w = h = side
        self.doc.update(replace(shape, x=x, y=y, props=replace(
            shape.props, w=max(1.0, w), h=max(1.0, h))))

    def _update_arrow_end(self, state: CreatingArrow, p: PointerInfo) -> None:
        shape = self.doc.shape(state.sid)
        if shape is None:
            return
        end = shape.to_local(p.page)
        if p.shift:
            end = _snap_angle((0.0, 0.0), end)
        self.doc.update(replace(shape, props=replace(shape.props, end=end)))

    def _translate(self, state: Translating, p: PointerInfo) -> None:
        dx = p.page[0] - state.origin[0]
        dy = p.page[1] - state.origin[1]
        if p.shift:
            # Lock to whichever axis has moved further.
            if abs(dx) > abs(dy):
                dy = 0.0
            else:
                dx = 0.0
        moved = []
        for sid, (x0, y0) in state.initial.items():
            shape = self.doc.shape(sid)
            if shape is not None:
                moved.append(shape.moved_to(x0 + dx, y0 + dy))
        self.doc.update_many(moved)

    def _resize(self, state: Resizing, p: PointerInfo) -> None:
        # Re-apply from the snapshot every time rather than accumulating
        # deltas: accumulating drifts and makes the drag unreversible.
        self.doc.shapes = list(state.initial)
        frame = state.frame
        handle = state.handle
        anchor_u, anchor_v = HANDLE_ANCHOR[handle]
        anchor = frame.box.point(anchor_u, anchor_v)
        pointer = frame.to_frame(p.page)

        sx = sy = 1.0
        if scales_x(handle) and frame.box.w:
            moving = frame.box.point(0.0 if anchor_u > 0.5 else 1.0, 0.0)[0]
            if moving != anchor[0]:
                sx = (pointer[0] - anchor[0]) / (moving - anchor[0])
        if scales_y(handle) and frame.box.h:
            moving = frame.box.point(0.0, 0.0 if anchor_v > 0.5 else 1.0)[1]
            if moving != anchor[1]:
                sy = (pointer[1] - anchor[1]) / (moving - anchor[1])

        if p.shift and handle in CORNER_HANDLES:
            uniform = max(abs(sx), abs(sy))
            sx = math.copysign(uniform, sx)
            sy = math.copysign(uniform, sy)

        # Let a shape flip, never let it collapse to nothing.
        sx = math.copysign(max(abs(sx), 0.01), sx or 1.0)
        sy = math.copysign(max(abs(sy), 0.01), sy or 1.0)

        out = []
        for shape in state.initial:
            if shape.sid not in self.doc.selected:
                continue
            out.append(_scaled_about(shape, frame, anchor, sx, sy))
        self.doc.update_many(out)

    def _rotate(self, state: Rotating, p: PointerInfo) -> None:
        self.doc.shapes = list(state.initial)
        delta = _angle(state.center, p.page) - state.start_angle
        if p.shift:
            delta = round(delta / ANGLE_SNAP) * ANGLE_SNAP
        out = [s.rotated(delta, state.center) for s in state.initial
               if s.sid in self.doc.selected]
        self.doc.update_many(out)

    # -- release -----------------------------------------------------------

    def pointer_up(self, p: PointerInfo) -> None:
        state = self.state
        if isinstance(state, Drawing):
            self._finish_pen(state)
        elif isinstance(state, CreatingBox):
            self._finish_box(state)
        elif isinstance(state, CreatingArrow):
            self._finish_arrow(state)
        elif isinstance(state, Brushing):
            self._finish_brush(state, p)
        self.state = Idle()
        self.brush = None
        self._notify()

    def _finish_pen(self, state: Drawing) -> None:
        shape = self.doc.shape(state.sid)
        if shape is None:
            return
        points = shape.props.points
        if len(points) < 2:
            self.doc.cancel_undo()
            return
        # A stroke that comes back near its own start closes, so it reads as a
        # ring rather than a near-miss.
        closed = math.dist(points[0], points[-1]) <= shape.props.style.width * 2
        if closed:
            self.doc.update(replace(shape, props=replace(shape.props, closed=True)))

    def _degenerate(self, shape: S.Shape) -> bool:
        props = shape.props
        return getattr(props, "w", 2) <= 2 and getattr(props, "h", 2) <= 2

    def _finish_box(self, state: CreatingBox) -> None:
        shape = self.doc.shape(state.sid)
        if shape is None:
            return
        if self._degenerate(shape):
            # A click without a drag: drop it rather than leaving a speck.
            self.doc.cancel_undo()
            return
        self.doc.select([state.sid])

    def _finish_arrow(self, state: CreatingArrow) -> None:
        shape = self.doc.shape(state.sid)
        if shape is None:
            return
        if math.dist((0.0, 0.0), shape.props.end) < 4.0:
            self.doc.cancel_undo()
            return
        self.doc.select([state.sid])

    def _finish_brush(self, state: Brushing, p: PointerInfo) -> None:
        box = Box(*norm_rect(state.origin[0], state.origin[1],
                             p.page[0], p.page[1]))
        if box.w < MIN_MARQUEE and box.h < MIN_MARQUEE:
            # A click, not a drag.  Without this a click in the hollow middle
            # of a big rectangle would select it, because a zero-size marquee
            # sits "inside" its outline — and that contradicts the click
            # behaviour, where a hollow shape lets the click through.
            return
        hits = [self.doc.shapes[i].sid for i in S.shapes_in(self.doc.shapes, box)]
        self.doc.select(hits, additive=state.additive)

    # -- click tools -------------------------------------------------------

    def click(self, p: PointerInfo) -> Optional[str]:
        """Handle a click for the click-to-place tools.

        Returns the name of a tool whose content the window has to ask the user
        for (text, bubble, emoji), or None when the click was handled here.
        """
        if self.tool not in CLICK_TOOLS:
            return None
        if self.tool == "marker":
            self._mark_undo()
            diameter = max(26.0, self.viewport.image_edge * 0.028)
            self.doc.add(S.Marker(p.page, S.next_number(self.doc.shapes),
                                  self.page_style, diameter=diameter))
            self.doc.clear_selection()
            self._notify()
            return None
        return self.tool

    def add_shape(self, shape: S.Shape) -> None:
        self._mark_undo()
        self.doc.add(shape)
        self.doc.clear_selection()
        self._notify()


# -- helpers -----------------------------------------------------------------

def _angle(origin: Point, p: Point) -> float:
    return math.atan2(p[1] - origin[1], p[0] - origin[0])


def _snap_angle(anchor: Point, p: Point) -> Point:
    dx, dy = p[0] - anchor[0], p[1] - anchor[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return p
    angle = round(math.atan2(dy, dx) / ANGLE_SNAP) * ANGLE_SNAP
    return (anchor[0] + math.cos(angle) * length,
            anchor[1] + math.sin(angle) * length)


def _point_in_polygon(p: Point, poly: Sequence[Point]) -> bool:
    from .geometry import point_in_polygon
    return point_in_polygon(p, poly)


def _scaled_about(shape: S.Shape, frame: SelectionFrame, anchor: Point,
                  sx: float, sy: float) -> S.Shape:
    """Scale one shape about *anchor*, expressed in the frame's space."""
    origin = frame.to_frame(shape.origin)
    scaled_origin = (anchor[0] + (origin[0] - anchor[0]) * sx,
                     anchor[1] + (origin[1] - anchor[1]) * sy)
    page_origin = frame.to_page(scaled_origin)

    # How much of each scale factor lands on the shape's own width and height
    # depends on how far it is rotated relative to the frame.
    relative = shape.rotation - frame.rotation
    cos_r, sin_r = abs(math.cos(relative)), abs(math.sin(relative))
    local_sx = sx * cos_r + sy * sin_r
    local_sy = sy * cos_r + sx * sin_r
    return shape.moved_to(*page_origin).scaled(local_sx, local_sy)
