"""The frame around picked shapes: its handles, and resizing, rotating and
bending the shapes from them.

Pure Python: no GTK, no cairo. The overlay's hand tool (overlay/hand.py)
gives a :class:`Reshaper` the picked shapes and the view, asks it which
handle is under the pointer, and hands it the drag; all of the geometry
lives here, which is what makes it testable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

from . import arrows
from . import shapes as S
from .geometry import Box, Point, rotate

CORNER_HANDLES = ("nw", "ne", "se", "sw")
ROTATE_HANDLES = ("rot-nw", "rot-ne", "rot-se", "rot-sw")
# A lone arrow gets these three instead of a resize frame: its bounding box is
# mostly empty space, so a frame is the wrong affordance for it.
ARROW_HANDLES = ("arrow-start", "arrow-middle", "arrow-end")

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
ROTATE_HANDLE_OFFSET = 16.0  # widget px outside the corner
ANGLE_SNAP = math.pi / 12    # 15°


def scales_x(handle: str) -> bool:
    return handle not in ("n", "s")


def scales_y(handle: str) -> bool:
    return handle not in ("e", "w")


@dataclass
class Viewport:
    """Where the page sits in the widget."""

    scale: float = 1.0
    offset: Point = (0.0, 0.0)

    def to_widget(self, p: Point) -> Point:
        s = self.scale or 1.0
        return (p[0] * s + self.offset[0], p[1] * s + self.offset[1])


@dataclass
class PointerInfo:
    widget: Point
    page: Point
    shift: bool = False


@dataclass
class SelectionFrame:
    """The box drawn around the picked shapes.

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
        return rotate((p[0] - self.origin[0], p[1] - self.origin[1]),
                      -self.rotation)

    def unit_point(self, u: float, v: float) -> Point:
        return self.to_page(self.box.point(u, v))

    @property
    def page_corners(self) -> List[Point]:
        return [self.to_page(c) for c in self.box.corners]

    @property
    def page_center(self) -> Point:
        return self.to_page(self.box.center)


# -- what a drag from a handle does ------------------------------------------

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


@dataclass
class DraggingArrow:
    handle: str


class Reshaper:
    """Reshapes *shapes*, picked together, from their frame's handles.

    ``shapes`` follows the drag; a press away from the handles changes
    nothing.
    """

    def __init__(self, shapes: Sequence[S.Shape], viewport: Viewport):
        self.shapes: List[S.Shape] = list(shapes)
        self.viewport = viewport
        self.state = None

    # -- the frame and its handles --

    @property
    def lone_arrow(self) -> Optional[S.Shape]:
        """The one picked shape, when it is an arrow."""
        if len(self.shapes) == 1 and self.shapes[0].kind == "arrow":
            return self.shapes[0]
        return None

    def arrow_handle_points(self) -> Dict[str, Point]:
        """The three handles of a lone arrow, in page space."""
        shape = self.lone_arrow
        if shape is None:
            return {}
        props = shape.props
        return {
            "arrow-start": shape.to_page(props.start),
            "arrow-middle": shape.to_page(props.middle()),
            "arrow-end": shape.to_page(props.end),
        }

    @property
    def selection_frame(self) -> Optional[SelectionFrame]:
        if not self.shapes:
            return None
        if len(self.shapes) == 1:
            shape = self.shapes[0]
            return SelectionFrame(shape.local_bounds, shape.origin,
                                  shape.rotation)
        box = S.selection_bounds(self.shapes)
        return SelectionFrame(box) if box else None

    def handle_at(self, widget_point: Point) -> Optional[str]:
        """Which handle is under a widget point.

        Tested in widget space so handles stay the same size to grab however
        far the view is zoomed.
        """
        # An arrow's own three handles take the place of the resize frame.
        for handle, page_point in self.arrow_handle_points().items():
            if math.dist(self.viewport.to_widget(page_point),
                         widget_point) <= HANDLE_HIT_RADIUS:
                return handle
        if self.lone_arrow is not None:
            return None

        frame = self.selection_frame
        if frame is None:
            return None
        for handle, (u, v) in HANDLE_UNIT.items():
            screen = self.viewport.to_widget(frame.unit_point(u, v))
            if math.dist(screen, widget_point) <= HANDLE_HIT_RADIUS:
                return handle
        for handle, out in self.rotate_handle_points().items():
            if math.dist(out, widget_point) <= HANDLE_HIT_RADIUS:
                return handle
        return None

    def rotate_handle_points(self) -> Dict[str, Point]:
        """The rotation handles, in widget space: just outside each corner
        of the frame, away from its centre."""
        frame = self.selection_frame
        if frame is None or self.lone_arrow is not None:
            return {}
        center = self.viewport.to_widget(frame.page_center)
        points = {}
        for handle, corner in zip(ROTATE_HANDLES, CORNER_HANDLES):
            u, v = HANDLE_UNIT[corner]
            screen = self.viewport.to_widget(frame.unit_point(u, v))
            dx, dy = screen[0] - center[0], screen[1] - center[1]
            length = math.hypot(dx, dy) or 1.0
            points[handle] = (screen[0] + dx / length * ROTATE_HANDLE_OFFSET,
                              screen[1] + dy / length * ROTATE_HANDLE_OFFSET)
        return points

    # -- the drag --

    def press(self, p: PointerInfo) -> bool:
        """Start a drag from the handle under *p*; False when there is
        none."""
        handle = self.handle_at(p.widget)
        if handle is None:
            return False
        if handle in ARROW_HANDLES:
            self.state = DraggingArrow(handle)
        elif handle in ROTATE_HANDLES:
            center = self.selection_frame.page_center
            self.state = Rotating(center, _angle(center, p.page),
                                  tuple(self.shapes))
        else:
            self.state = Resizing(handle, self.selection_frame,
                                  tuple(self.shapes))
        return True

    def drag(self, p: PointerInfo) -> None:
        """Follow the pointer with the handle being dragged."""
        if isinstance(self.state, Resizing):
            self._resize(self.state, p)
        elif isinstance(self.state, Rotating):
            self._rotate(self.state, p)
        elif isinstance(self.state, DraggingArrow):
            self._drag_arrow(self.state, p)

    def _resize(self, state: Resizing, p: PointerInfo) -> None:
        # Re-apply from the snapshot every time rather than accumulating
        # deltas: accumulating drifts and makes the drag unreversible.
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

        width_only = not scales_y(handle)
        self.shapes = [_scaled_about(shape, frame, anchor, sx, sy, width_only)
                       for shape in state.initial]

    def _rotate(self, state: Rotating, p: PointerInfo) -> None:
        delta = _angle(state.center, p.page) - state.start_angle
        if p.shift:
            delta = round(delta / ANGLE_SNAP) * ANGLE_SNAP
        self.shapes = [s.rotated(delta, state.center) for s in state.initial]

    def _drag_arrow(self, state: DraggingArrow, p: PointerInfo) -> None:
        shape = self.shapes[0]
        props = shape.props
        local = shape.to_local(p.page)

        if state.handle == "arrow-end":
            end = _snap_angle(props.start, local) if p.shift else local
            self.shapes = [replace(shape, props=replace(props, end=end))]
            return

        if state.handle == "arrow-middle":
            bend = arrows.bend_from_point(props.start, props.end, local)
            self.shapes = [replace(shape, props=replace(
                props, bend=arrows.snap_bend(bend, props.style.width)))]
            return

        # Dragging the start moves the shape's origin, so the end has to be
        # re-expressed against it or the arrow would drag its tip along too.
        page_end = shape.to_page(props.end)
        moved = shape.moved_to(p.page[0], p.page[1])
        end = moved.to_local(page_end)
        if p.shift:
            end = _snap_angle(props.start, end)
        self.shapes = [replace(moved, props=replace(props, end=end))]


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


def _scaled_about(shape: S.Shape, frame: SelectionFrame, anchor: Point,
                  sx: float, sy: float, width_only: bool = False) -> S.Shape:
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
    return shape.moved_to(*page_origin).scaled(local_sx, local_sy, width_only)
