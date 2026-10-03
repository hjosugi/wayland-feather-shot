"""The hand tool on the region overlay: picking placed shapes and moving
them.

A press picks the shape under the pointer (Shift or Ctrl adds to the pick),
and a drag moves every picked shape; they are lifted out of the cached
composite while they move and drawn live (draw.py). A mixin of
overlay.window.OverlayWindow.
"""

from __future__ import annotations

from typing import Optional

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk  # noqa: E402


class OverlayHandMixin:
    """``_picked`` holds the picked shapes' sids; ``_lifted`` the shapes on
    the move, with their places in the stacking order."""

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
        # Lift the picked shapes out of the cached composite; they are drawn
        # live while they move.
        self._lifted = [(i, shape) for i, shape in enumerate(self.shapes)
                        if shape.sid in self._picked]
        for i, _shape in reversed(self._lifted):
            del self.shapes[i]
        self._lift_offset = (0.0, 0.0)
        self.area.set_cursor(Gdk.Cursor.new_from_name("grabbing"))
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
        drawn, or the picked shapes on the move."""
        if self._preview is not None:
            return [self._preview]
        dx, dy = self._lift_offset
        return [shape.translate(dx, dy) for _i, shape in self._lifted]

    def _picked_shapes(self):
        """The picked shapes as drawn now, for their frames."""
        if self.tool != "hand" or not self._picked:
            return []
        return [shape for shape in self.shapes
                if shape.sid in self._picked] + (
            self._live_shapes() if self._lifted else [])
