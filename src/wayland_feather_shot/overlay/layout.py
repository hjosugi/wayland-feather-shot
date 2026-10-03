"""Position the floating controls around a region selection."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


Position = Tuple[int, int]
Size = Tuple[int, int]
Bounds = Tuple[float, float, float, float]
EDGE_MARGIN = 8
BAR_GAP = 12


@dataclass(frozen=True)
class ControlLayout:
    toolbar: Position
    actions: Position
    stacked: bool


def _bars_fit(window: Size, first: Position, first_size: Size,
              second: Position, second_size: Size) -> bool:
    """Check viewport margins and separation for two control bars."""
    win_w, win_h = window

    def inside(pos: Position, size: Size) -> bool:
        return (EDGE_MARGIN <= pos[0]
                and pos[0] + size[0] <= win_w - EDGE_MARGIN
                and EDGE_MARGIN <= pos[1]
                and pos[1] + size[1] <= win_h - EDGE_MARGIN)

    return (inside(first, first_size) and inside(second, second_size)
            and (first[0] + first_size[0] + BAR_GAP <= second[0]
                 or second[0] + second_size[0] + BAR_GAP <= first[0]
                 or first[1] + first_size[1] + BAR_GAP <= second[1]
                 or second[1] + second_size[1] + BAR_GAP <= first[1]))


def layout_controls(window: Size, selection: Bounds, toolbar: Size,
                    vertical_actions: Size,
                    horizontal_actions: Size) -> ControlLayout:
    """Use the usual layout or two rows when it cannot fit or stay close."""
    tb, actions = position_bars(window, selection, toolbar, vertical_actions)
    ordinary = ControlLayout(tb, actions, False)
    x0, y0, x1, y1 = selection
    tb_w, tb_h = toolbar
    act_w, act_h = vertical_actions

    def gap(start: float, end: float, other_start: float,
            other_end: float) -> float:
        return max(0, start - other_end, other_start - end)

    ordinary_fits = _bars_fit(window, tb, toolbar, actions, vertical_actions)
    # A small clamp at a screen edge is fine. If either bar no longer faces
    # the selection, a different position for the same L cannot fix the
    # corner geometry without leaving the other bar detached.
    slack = 2 * BAR_GAP
    if (ordinary_fits and gap(tb[0], tb[0] + tb_w, x0, x1) <= slack
            and gap(tb[1], tb[1] + tb_h, y0, y1) <= BAR_GAP + slack
            and gap(actions[0], actions[0] + act_w, x0, x1)
            <= BAR_GAP + slack
            and gap(actions[1], actions[1] + act_h, y0, y1) <= slack):
        return ordinary

    row_w, row_h = horizontal_actions
    win_w, win_h = window
    if row_w > tb_w or tb_w + 2 * EDGE_MARGIN > win_w:
        return ordinary

    tx = max(EDGE_MARGIN, min(round((x0 + x1 - tb_w) / 2),
                              win_w - tb_w - EDGE_MARGIN))
    if tx == EDGE_MARGIN:
        ax = tx
    elif tx == win_w - tb_w - EDGE_MARGIN:
        ax = tx + tb_w - row_w
    else:
        ax = max(tx, min(round((x0 + x1 - row_w) / 2),
                         tx + tb_w - row_w))

    below_ty = math.ceil(y1 + BAR_GAP)
    below_ay = below_ty + tb_h + BAR_GAP
    if below_ay + row_h <= win_h - EDGE_MARGIN:
        return ControlLayout((tx, below_ty), (ax, below_ay), True)

    # No room below: both rows go inside the selection's bottom edge, as the
    # toolbar does on its own, never above the selection.
    group_h = tb_h + BAR_GAP + row_h
    inside_ty = max(EDGE_MARGIN, min(math.floor(y1), win_h - EDGE_MARGIN)
                    - BAR_GAP - group_h)
    inside_ay = inside_ty + tb_h + BAR_GAP
    if inside_ay + row_h <= win_h - EDGE_MARGIN:
        return ControlLayout((tx, inside_ty), (ax, inside_ay), True)

    # A short viewport may have no room outside the selection. Keep both
    # rows accessible at the opposite edge rather than returning an invalid
    # vertical arrangement.
    if not ordinary_fits:
        group_h = tb_h + BAR_GAP + row_h
        if group_h <= win_h - 2 * EDGE_MARGIN:
            if y0 + y1 <= win_h:
                ty = win_h - EDGE_MARGIN - group_h
                ay = ty + tb_h + BAR_GAP
            else:
                ay = EDGE_MARGIN
                ty = ay + row_h + BAR_GAP
            return ControlLayout((tx, ty), (ax, ay), True)
    return ordinary


def position_bars(window: Size, selection: Bounds, toolbar: Size,
                  actions: Size) -> Tuple[Position, Position]:
    """Find preferred positions for a toolbar and vertical action bar.

    The horizontal bar stays below the selection whenever it fits there.
    If no valid placement fits, the caller can switch to horizontal actions.
    """
    win_w, win_h = window
    x0, y0, x1, y1 = selection
    tb_w, tb_h = toolbar
    act_w, act_h = actions
    max_tx = win_w - tb_w - EDGE_MARGIN
    max_ty = win_h - tb_h - EDGE_MARGIN
    max_sy = win_h - act_h - EDGE_MARGIN

    def clamp(value: int, maximum: int) -> int:
        return max(EDGE_MARGIN, min(value, maximum))

    centered_tx = clamp(round((x0 + x1 - tb_w) / 2), max_tx)
    # The toolbar's end lines up with the selection's edge on the side the
    # actions hang from, so the two bars always meet at one corner of the
    # selection (Lightshot and Snipaste do the same). A toolbar wider than
    # the selection then sticks out on one side only, never both.
    right_aligned_tx = clamp(round(x1 - tb_w), max_tx)
    left_aligned_tx = clamp(round(x0), max_tx)
    placements = []
    below_ty = math.ceil(y1 + BAR_GAP)
    if below_ty <= max_ty:
        placements.append(("below", below_ty))
    else:
        # No room under the selection (it reaches the bottom of the screen,
        # or past it when zoomed in): the toolbar goes inside it, along the
        # bottom edge of what is visible. It never flips above the
        # selection; that read as the selection and its controls swapping
        # places.
        placements.append(("inside", clamp(
            math.floor(min(y1, win_h) - tb_h - BAR_GAP), max_ty)))

    sides = []
    right_sx = math.ceil(x1 + BAR_GAP)
    left_sx = math.floor(x0 - act_w - BAR_GAP)
    if right_sx + act_w <= win_w - EDGE_MARGIN:
        sides.append(("right", right_sx))
    if left_sx >= EDGE_MARGIN:
        sides.append(("left", left_sx))

    for direction, preferred_ty in placements:
        candidates: list[tuple[tuple[float, ...], Position, Position]] = []
        for side, sx in sides:
            # The actions hang from the selection's top edge and reach down,
            # whatever the selection's height, so the L looks the same
            # everywhere. A short selection may instead share its bottom edge
            # with them, or they drop under the toolbar, when that is the
            # only way to keep both bars attached.
            preferred_sy = clamp(math.ceil(y0), max_sy)
            if direction == "below":
                action_ys = (preferred_sy,
                             clamp(math.floor(y1 - act_h), max_sy),
                             preferred_ty + tb_h + BAR_GAP)
            else:
                action_ys = (preferred_sy,
                             clamp(math.floor(min(y1, win_h) - act_h),
                                   max_sy))

            for sy in action_ys:
                if direction == "below":
                    toolbar_ys = (preferred_ty,
                                  max(preferred_ty, sy + act_h + BAR_GAP))
                else:
                    toolbar_ys = (preferred_ty,)

                preferred_tx = (right_aligned_tx if side == "right"
                                else left_aligned_tx)
                for ty in toolbar_ys:
                    # Put the toolbar beside the actions rather than pushing
                    # the actions away from the selection's edge.
                    for tx in (preferred_tx, centered_tx,
                               sx - tb_w - BAR_GAP, sx + act_w + BAR_GAP):
                        tb, act = (tx, ty), (sx, sy)
                        if not _bars_fit(window, tb, toolbar, act, actions):
                            continue

                        vertical_gap = (ty - y1 if direction == "below"
                                        else 0)       # inside: attached
                        horizontal_gap = max(0, x0 - tx - tb_w, tx - x1)
                        action_gap = max(0, y0 - sy - act_h, sy - y1)
                        # The long toolbar should continue to face the
                        # selection at the screen corners. The narrow action
                        # bar can move beyond it when both cannot fit there.
                        detachment = (2 * (max(0, vertical_gap - BAR_GAP)
                                           + horizontal_gap) + action_gap)
                        # Keeping the actions at the selection's top edge
                        # matters more than keeping the toolbar centred.
                        rank = (detachment + (2 * BAR_GAP if side == "left"
                                              else 0),
                                0 if side == "right" else 1,
                                abs(sy - preferred_sy),
                                abs(tx - preferred_tx))
                        candidates.append((rank, tb, act))

        if candidates:
            _, tb, act = min(candidates, key=lambda item: item[0])
            return tb, act

    # If neither side of the selection fits, pack the bars in the viewport.
    # A full-screen selection may require controls over the captured image.
    tx = centered_tx
    ty = (placements[0][1] if placements else
          (max_ty if (y0 + y1) / 2 <= win_h / 2 else EDGE_MARGIN))
    sx = (sides[0][1] if sides else clamp(math.ceil(x1 + BAR_GAP),
                                         win_w - act_w - EDGE_MARGIN))
    sy = clamp(math.ceil(y0), max_sy)
    preferred_toolbar, preferred_actions = (tx, ty), (sx, sy)
    if _bars_fit(window, preferred_toolbar, toolbar, preferred_actions,
                 actions):
        return preferred_toolbar, preferred_actions

    packed: list[tuple[int, Position, Position]] = []

    def consider(tb: Position, act: Position) -> None:
        if _bars_fit(window, tb, toolbar, act, actions):
            distance = (abs(tb[0] - tx) + abs(tb[1] - ty)
                        + abs(act[0] - sx) + abs(act[1] - sy))
            packed.append((distance, tb, act))

    total_h = tb_h + act_h + BAR_GAP
    if total_h <= win_h - 2 * EDGE_MARGIN:
        for top in (clamp(ty, win_h - total_h - EDGE_MARGIN),
                    clamp(sy - tb_h - BAR_GAP,
                          win_h - total_h - EDGE_MARGIN)):
            consider((tx, top), (sx, top + tb_h + BAR_GAP))
        for top in (clamp(sy, win_h - total_h - EDGE_MARGIN),
                    clamp(ty - act_h - BAR_GAP,
                          win_h - total_h - EDGE_MARGIN)):
            consider((tx, top + act_h + BAR_GAP), (sx, top))

    total_w = tb_w + act_w + BAR_GAP
    if total_w <= win_w - 2 * EDGE_MARGIN:
        for left in (clamp(tx, win_w - total_w - EDGE_MARGIN),
                     clamp(sx - tb_w - BAR_GAP,
                           win_w - total_w - EDGE_MARGIN)):
            consider((left, ty), (left + tb_w + BAR_GAP, sy))
        for left in (clamp(sx, win_w - total_w - EDGE_MARGIN),
                     clamp(tx - act_w - BAR_GAP,
                           win_w - total_w - EDGE_MARGIN)):
            consider((left + act_w + BAR_GAP, ty), (left, sy))

    if packed:
        _, tb, act = min(packed, key=lambda item: item[0])
        return tb, act
    return preferred_toolbar, preferred_actions


def position_label(window: Size, selection: Bounds, label: Size,
                   occupied: Tuple[Bounds, ...]) -> Position:
    """Find space for the selection dimensions next to the controls."""
    win_w, win_h = window
    x0, y0, x1, y1 = selection
    width, height = label
    max_x, max_y = win_w - width, win_h - height
    if max_x < 0 or max_y < 0:
        return (0, 0)

    def clamp(value: int, maximum: int) -> int:
        return max(0, min(value, maximum))

    def overlaps(pos: Position, rect: Bounds) -> bool:
        rx0, ry0, rx1, ry1 = rect
        return (pos[0] < rx1 and pos[0] + width > rx0
                and pos[1] < ry1 and pos[1] + height > ry0)

    preferred_x = clamp(math.floor(x0 + 1), max_x)
    preferred_y = clamp(math.floor(y0 - height - 5), max_y)
    outside = (
        (preferred_x, preferred_y),
        (math.floor(x0 - width - BAR_GAP), math.ceil(y0)),
        (math.ceil(x1 + BAR_GAP), math.ceil(y0)),
        (preferred_x, math.ceil(y1 + BAR_GAP)),
    )
    for pos in outside:
        if (0 <= pos[0] <= max_x and 0 <= pos[1] <= max_y
                and not overlaps(pos, selection)
                and not any(overlaps(pos, rect) for rect in occupied)):
            return pos

    # The corner handle has a 14 px hit area; leave a little more space
    # when the label has to move into the selection.
    inside_inset = 18
    inside = (math.ceil(x0 + inside_inset),
              math.ceil(y0 + inside_inset))
    if (inside[0] + width <= x1 - inside_inset
            and inside[1] + height <= y1 - inside_inset
            and not any(overlaps(inside, rect) for rect in occupied)):
        return inside

    # Extremely small selections may leave no adjacent slot. Keep the label
    # visible and away from controls even if it must sit farther away.
    xs = (0, max_x, preferred_x)
    ys = (0, max_y, preferred_y)
    free = [(x, y) for x in xs for y in ys
            if not any(overlaps((x, y), rect) for rect in occupied)]
    if free:
        return min(free, key=lambda pos: (overlaps(pos, selection),
                                          abs(pos[0] - preferred_x)
                                          + abs(pos[1] - preferred_y)))
    return (preferred_x, preferred_y)
