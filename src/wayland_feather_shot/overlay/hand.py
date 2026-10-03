"""The hand tool on the region overlay: picking placed shapes, moving
and reshaping them.

A press picks the shape under the pointer (Shift or Ctrl adds to the pick),
and a drag moves every picked shape. The picked shapes get the editor
window's frame: its handles resize them, the ones beyond the corners rotate
them, and a lone arrow has handles for its ends and its bend instead. The
editor's interaction engine (editor/interaction.py) does that geometry,
over a document of the picked shapes alone. Shapes on the move are lifted
out of the cached composite and drawn live (draw.py). A mixin of
overlay.window.OverlayWindow.
"""

from __future__ import annotations

from typing import Optional

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk  # noqa: E402

from ..editor import interaction
from ..editor.document import Document
from ..editor.geometry import point_in_polygon
from .canvas import rect

# Cursor names for the frame's handles.
HANDLE_CURSORS = {
    "nw": "nwse-resize", "se": "nwse-resize",
    "ne": "nesw-resize", "sw": "nesw-resize",
    "n": "ns-resize", "s": "ns-resize", "e": "ew-resize", "w": "ew-resize",
}
FRAME_RGB = (0.25, 0.6, 1.0)


class OverlayHandMixin:
    """``_picked`` holds the picked shapes' sids; ``_lifted`` the shapes on
    the move, with their places in the stacking order; ``_engine`` the
    interaction engine while a handle is dragged."""

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

    @staticmethod
    def _adds_to_pick(gesture) -> bool:
        """Shift or Ctrl held: the press adds to (or takes from) the picked
        shapes instead of starting over."""
        state = gesture.get_current_event_state()
        return bool(state & (Gdk.ModifierType.SHIFT_MASK
                             | Gdk.ModifierType.CONTROL_MASK))

    def _pick_engine(self, shapes=None):
        """The editor's interaction engine over the picked shapes (or
        *shapes*), all selected, seen through the current view. None with
        nothing picked or another tool."""
        if shapes is None:
            shapes = [s for s in self.shapes if s.sid in self._picked]
        if self.tool != "hand" or not shapes:
            return None
        engine = interaction.Editor(Document(shapes))
        engine.tool = "select"
        engine.doc.select(s.sid for s in shapes)
        scale, ox, oy = self._view_params()
        engine.viewport = interaction.Viewport(
            (float(self.pixbuf.get_width()), float(self.pixbuf.get_height())),
            scale, (ox, oy))
        return engine

    def _pick_handle_at(self, x, y) -> Optional[str]:
        """The picked shapes' handle under widget point (x, y), if any."""
        engine = self._pick_engine()
        return engine.handle_at((x, y)) if engine is not None else None

    def _hand_cursor(self, x, y, ix, iy) -> str:
        """What a press with the hand would do here, as a cursor name."""
        handle = self._pick_handle_at(x, y)
        if handle in HANDLE_CURSORS:
            return HANDLE_CURSORS[handle]
        if handle is not None:          # rotation or an arrow's handles
            return "grab"
        return "grab" if self._shape_at(ix, iy) is not None else "default"

    def _press_hand(self, gesture, x, y, ix, iy) -> Optional[str]:
        """A press with the hand; returns the kind of drag that follows.

        On a handle of the picked shapes it reshapes them, inside their
        frame (a hollow rectangle's middle) it moves them, and otherwise it
        picks (_pick).
        """
        adding = self._adds_to_pick(gesture)
        engine = self._pick_engine()
        if engine is not None and not adding:
            if engine.handle_at((x, y)) is not None:
                self._lift_picked()
                engine.pointer_down(interaction.PointerInfo((x, y), (ix, iy)))
                self._engine = engine
                return "reshape"
        index = self._shape_at(ix, iy)
        if index is None and engine is not None and not adding:
            frame = engine.selection_frame
            if (frame is not None and engine.lone_arrow is None
                    and point_in_polygon((ix, iy), frame.page_corners)):
                self._pick_on_click = None
                self._lift_picked()
                return "shape"
        return self._pick(index, adding)

    def _lift_picked(self):
        """Take the picked shapes out of the cached composite; they are
        drawn live while they move."""
        self._lifted = [(i, shape) for i, shape in enumerate(self.shapes)
                        if shape.sid in self._picked]
        for i, _shape in reversed(self._lifted):
            del self.shapes[i]
        self._lift_offset = (0.0, 0.0)
        self.area.set_cursor(Gdk.Cursor.new_from_name("grabbing"))

    def _reshape(self, ix, iy, shift):
        """Follow the pointer with the handle being dragged."""
        x, y = self._to_widget(ix, iy)
        self._engine.pointer_move(
            interaction.PointerInfo((x, y), (ix, iy), shift=shift))

    def _drop_reshaped(self):
        """Put the reshaped shapes back in their places (one undo step)."""
        engine, self._engine = self._engine, None
        reshaped = {shape.sid: shape for shape in engine.doc.shapes}
        lifted, self._lifted = self._lifted, []
        for i, shape in lifted:
            self.shapes.insert(i, shape)
        if any(reshaped.get(s.sid, s) != s for _i, s in lifted):
            self._push_history()
            for i, shape in lifted:
                self.shapes[i] = reshaped.get(shape.sid, shape)

    def _pick(self, index, adding) -> Optional[str]:
        """A press with the hand on shape *index* (None: on no shape).

        A press on a shape not yet picked picks it: alone, or with Shift or
        Ctrl as one more. Then every picked shape is lifted to move
        together. A click (a press without a move) on a shape that was
        already picked keeps just that one, or with Shift or Ctrl drops it;
        see _drop_lifted. A press on no shape clears the pick, unless Shift
        or Ctrl is held. Returns the kind of drag that follows.
        """
        self._pick_on_click = None
        if index is None:
            if not adding:
                self._picked.clear()
            return None
        sid = self.shapes[index].sid
        if sid not in self._picked:
            if not adding:
                self._picked.clear()
            self._picked.add(sid)
        else:
            self._pick_on_click = ("drop" if adding else "only", sid)
        self._lift_picked()
        return "shape"

    def _drop_lifted(self):
        """Put the lifted shapes back where they were in the stacking order,
        moved if the pointer moved (one undo step)."""
        lifted, self._lifted = self._lifted, []
        for i, shape in lifted:
            self.shapes.insert(i, shape)
        dx, dy = self._lift_offset
        if dx or dy:
            self._push_history()
            for i, shape in lifted:
                self.shapes[i] = shape.translate(dx, dy)
        elif self._pick_on_click is not None:
            action, sid = self._pick_on_click
            if action == "drop":
                self._picked.discard(sid)
            else:
                self._picked = {sid}
        self._pick_on_click = None
        self._lift_offset = (0.0, 0.0)
        self.area.set_cursor(Gdk.Cursor.new_from_name("grab"))

    def _live_shapes(self):
        """What is drawn live over the cached composite: the shape being
        drawn, or the picked shapes on the move or being reshaped."""
        if self._preview is not None:
            return [self._preview]
        if self._engine is not None:
            return list(self._engine.doc.shapes)
        dx, dy = self._lift_offset
        return [shape.translate(dx, dy) for _i, shape in self._lifted]

    def _picked_shapes(self):
        """The picked shapes as drawn now, for their frames."""
        if self.tool != "hand" or not self._picked:
            return []
        return [shape for shape in self.shapes
                if shape.sid in self._picked] + (
            self._live_shapes() if self._lifted else [])

    def _draw_pick_frame(self, snapshot):
        """The picked shapes' frame and handles, as the editor draws them:
        one frame around them all (a lone shape's own, rotated), or a lone
        arrow's three handles. Several picked shapes are outlined too."""
        shapes = self._picked_shapes()
        if not shapes:
            return
        engine = self._engine or self._pick_engine(shapes)
        to_widget = engine.viewport.to_widget
        outlines = []
        if len(shapes) > 1:
            for shape in shapes:
                box = shape.page_bounds
                outlines.append([to_widget(p) for p in (
                    (box.x, box.y), (box.x + box.w, box.y),
                    (box.x + box.w, box.y + box.h), (box.x, box.y + box.h))])
        frame = engine.selection_frame
        corners, squares, dots = [], [], []
        if engine.lone_arrow is not None:
            dots = [to_widget(p)
                    for p in engine.arrow_handle_points().values()]
        elif frame is not None:
            corners = [to_widget(p) for p in frame.page_corners]
            squares = [to_widget(frame.unit_point(u, v))
                       for u, v in interaction.HANDLE_UNIT.values()]
            dots = list(engine.rotate_handle_points().values())
        points = [p for outline in outlines for p in outline]
        points += corners + squares + dots
        if not points:
            return
        x0 = min(p[0] for p in points) - 8
        y0 = min(p[1] for p in points) - 8
        x1 = max(p[0] for p in points) + 8
        y1 = max(p[1] for p in points) + 8
        cr = snapshot.append_cairo(rect(x0, y0, x1 - x0, y1 - y0))
        r, g, b = FRAME_RGB
        cr.set_line_width(1.0)
        cr.set_source_rgba(r, g, b, 0.7)
        for outline in outlines:
            cr.move_to(*outline[0])
            for p in outline[1:]:
                cr.line_to(*p)
            cr.close_path()
            cr.stroke()
        if corners:
            cr.set_line_width(1.5)
            cr.set_source_rgba(r, g, b, 0.95)
            cr.move_to(*corners[0])
            for p in corners[1:]:
                cr.line_to(*p)
            cr.close_path()
            cr.stroke()
        for x, y in squares:
            cr.rectangle(x - 4.5, y - 4.5, 9, 9)
            cr.set_source_rgb(1, 1, 1)
            cr.fill_preserve()
            cr.set_source_rgb(r, g, b)
            cr.set_line_width(1.5)
            cr.stroke()
        for x, y in dots:
            cr.arc(x, y, 5, 0, 6.2832)
            cr.set_source_rgb(r, g, b)
            cr.fill_preserve()
            cr.set_source_rgb(1, 1, 1)
            cr.set_line_width(1.5)
            cr.stroke()
        del cr
