"""The shape store: z-ordered shapes, the selection, and undo/redo.

Pure Python, so it is unit-testable without a GTK stack.  The base image is
opaque to the document — the canvas hands it in when it snapshots, because a
crop changes the pixels as well as the shapes and the two have to undo
together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .geometry import Box
from .shapes import Shape, Style, selection_bounds

HISTORY_LIMIT = 100


@dataclass(frozen=True)
class Snapshot:
    shapes: Tuple[Shape, ...]
    base: Any = None


class Document:
    def __init__(self, shapes: Optional[Sequence[Shape]] = None):
        self.shapes: List[Shape] = list(shapes or [])
        self.selected: Set[str] = set()
        self._undo: List[Snapshot] = []
        self._redo: List[Snapshot] = []

    # -- reading --

    def index_of(self, sid: str) -> Optional[int]:
        for i, s in enumerate(self.shapes):
            if s.sid == sid:
                return i
        return None

    def shape(self, sid: str) -> Optional[Shape]:
        i = self.index_of(sid)
        return self.shapes[i] if i is not None else None

    @property
    def selected_shapes(self) -> List[Shape]:
        return [s for s in self.shapes if s.sid in self.selected]

    @property
    def has_selection(self) -> bool:
        return bool(self.selected)

    def selection_page_bounds(self) -> Optional[Box]:
        return selection_bounds(self.selected_shapes)

    # -- history --

    def mark_undo(self, base: Any = None) -> None:
        """Snapshot the current state before an edit."""
        self._undo.append(Snapshot(tuple(self.shapes), base))
        if len(self._undo) > HISTORY_LIMIT:
            self._undo.pop(0)
        self._redo.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self, base: Any = None) -> Any:
        """Restore the previous state; returns the base image to restore."""
        if not self._undo:
            return base
        self._redo.append(Snapshot(tuple(self.shapes), base))
        snapshot = self._undo.pop()
        self._restore(snapshot)
        return snapshot.base

    def redo(self, base: Any = None) -> Any:
        if not self._redo:
            return base
        self._undo.append(Snapshot(tuple(self.shapes), base))
        snapshot = self._redo.pop()
        self._restore(snapshot)
        return snapshot.base

    def cancel_undo(self) -> Any:
        """Roll back an edit that turned out to be a no-op.

        A click that starts a shape and releases without dragging leaves a
        speck behind; dropping the snapshot rather than calling :meth:`undo`
        keeps that non-edit out of the redo stack too.
        """
        if not self._undo:
            return None
        snapshot = self._undo.pop()
        self._restore(snapshot)
        return snapshot.base

    def _restore(self, snapshot: Snapshot) -> None:
        self.shapes = list(snapshot.shapes)
        alive = {s.sid for s in self.shapes}
        # Keep whatever survived, so undoing a style change does not also drop
        # the selection the user is still working with.
        self.selected &= alive

    # -- writing --

    def add(self, shape: Shape) -> Shape:
        self.shapes.append(shape)
        return shape

    def update(self, shape: Shape) -> None:
        i = self.index_of(shape.sid)
        if i is not None:
            self.shapes[i] = shape

    def update_many(self, shapes: Iterable[Shape]) -> None:
        by_id: Dict[str, Shape] = {s.sid: s for s in shapes}
        self.shapes = [by_id.get(s.sid, s) for s in self.shapes]

    def remove(self, sids: Iterable[str]) -> None:
        doomed = set(sids)
        self.shapes = [s for s in self.shapes if s.sid not in doomed]
        self.selected -= doomed

    def replace_all(self, shapes: Sequence[Shape]) -> None:
        self.shapes = list(shapes)
        self.selected.clear()

    def translate_all(self, dx: float, dy: float) -> None:
        self.shapes = [s.translate(dx, dy) for s in self.shapes]

    # -- selection --

    def select(self, sids: Iterable[str], additive: bool = False) -> None:
        if additive:
            self.selected |= set(sids)
        else:
            self.selected = set(sids)

    def toggle(self, sid: str) -> None:
        self.selected ^= {sid}

    def clear_selection(self) -> None:
        self.selected.clear()

    def select_all(self) -> None:
        self.selected = {s.sid for s in self.shapes}

    def delete_selected(self) -> bool:
        if not self.selected:
            return False
        self.remove(set(self.selected))
        return True

    def restyle_selected(self, style: Style) -> bool:
        if not self.selected:
            return False
        changed = False
        out: List[Shape] = []
        for s in self.shapes:
            if s.sid in self.selected and s.style is not None:
                out.append(s.restyled(style))
                changed = True
            else:
                out.append(s)
        self.shapes = out
        return changed

    def nudge_selected(self, dx: float, dy: float) -> bool:
        if not self.selected:
            return False
        self.shapes = [s.translate(dx, dy) if s.sid in self.selected else s
                       for s in self.shapes]
        return True

    def bring_to_front(self) -> bool:
        if not self.selected:
            return False
        moved = [s for s in self.shapes if s.sid in self.selected]
        rest = [s for s in self.shapes if s.sid not in self.selected]
        self.shapes = rest + moved
        return True

    def send_to_back(self) -> bool:
        if not self.selected:
            return False
        moved = [s for s in self.shapes if s.sid in self.selected]
        rest = [s for s in self.shapes if s.sid not in self.selected]
        self.shapes = moved + rest
        return True
