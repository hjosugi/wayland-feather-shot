"""Arrow geometry: heads, curvature, and the shaft between them.

Pure Python — no GTK — so the maths is unit-testable.

An arrow is a start point, an end point and a **bend**: the signed
perpendicular distance from the straight chord between the terminals to where
the arrow's middle has been pulled.  Zero bend is a straight line; anything
else is the unique circular arc through the two terminals and that middle
point.  Curvature matters on a dense screenshot, where a straight arrow to the
thing you mean often has to cross the thing you don't.

Heads know their own length along the shaft, so the shaft can stop exactly
where the head begins instead of at a fixed fudge factor that leaves heavy
strokes poking through the tip.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]

#: Head styles, in the order they appear in the picker.
HEADS: Tuple[str, ...] = ("none", "arrow", "triangle", "chevron", "square",
                          "dot", "diamond", "bar", "inverted")

HEAD_TITLES = {
    "none": "None",
    "arrow": "Arrow",
    "triangle": "Outlined triangle",
    "chevron": "Chevron",
    "square": "Square",
    "dot": "Dot",
    "diamond": "Diamond",
    "bar": "Bar",
    "inverted": "Inverted",
}

#: Bounds on how many segments a rendered arc is flattened into.  The count
#: adapts to the arc's length so the flattening error stays under a pixel on a
#: big arrow without paying for 160 segments on a small one.
MIN_ARC_SEGMENTS = 12
MAX_ARC_SEGMENTS = 160
#: Target length of one flattened segment, in page units.
ARC_SEGMENT_LENGTH = 4.0
#: Bend smaller than this fraction of the stroke width snaps back to straight.
BEND_SNAP_RATIO = 1.5


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Point, s: float) -> Point:
    return (a[0] * s, a[1] * s)


def _mid(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _per(a: Point) -> Point:
    """The left-hand perpendicular."""
    return (a[1], -a[0])


def _uni(a: Point) -> Point:
    length = math.hypot(a[0], a[1])
    return (0.0, 0.0) if length == 0 else (a[0] / length, a[1] / length)


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


# -- heads -------------------------------------------------------------------

def head_size(style: str, stroke_width: float) -> float:
    """How wide a head is, across the shaft."""
    if style == "none":
        return 0.0
    base = max(10.0, stroke_width * 4.0)
    if style in ("dot", "square"):
        return base * 0.62
    if style == "bar":
        return base * 0.9
    return base


def head_length(style: str, stroke_width: float) -> float:
    """How far a head reaches back along the shaft.

    The shaft is trimmed by exactly this, which is what stops a heavy stroke
    poking out through the tip — the old code shortened by a flat 0.6 of the
    head size whatever the head actually was.
    """
    size = head_size(style, stroke_width)
    if style == "none":
        return 0.0
    if style == "bar":
        return max(stroke_width * 0.5, 1.0)
    if style in ("dot", "square"):
        return size * 0.5
    if style == "chevron":
        return size * 0.72
    if style == "inverted":
        return size * 0.55
    return size * 0.86


def head_path(style: str, tip: Point, angle: float,
              stroke_width: float) -> Tuple[str, List[Point]]:
    """The head's outline and how to paint it.

    Returns ``(kind, points)`` where kind is ``"fill"``, ``"outline"`` (a closed
    path that is stroked) or ``"stroke"`` (an open one); *angle* points the way
    the arrow is travelling, so the head sits behind the tip.
    """
    if style == "none":
        return ("fill", [])

    size = head_size(style, stroke_width)
    cos_a, sin_a = math.cos(angle), math.sin(angle)

    def back(distance: float, offset: float) -> Point:
        """A point *distance* back along the shaft and *offset* across it."""
        return (tip[0] - distance * cos_a - offset * sin_a,
                tip[1] - distance * sin_a + offset * cos_a)

    if style in ("arrow", "triangle"):
        spread = size * 0.45
        points = [tip, back(size * 0.86, -spread), back(size * 0.86, spread)]
        return ("fill" if style == "arrow" else "outline", points)

    if style == "chevron":
        spread = size * 0.5
        # An open V: back out to one side, in to the tip, back out to the other.
        return ("stroke", [back(size * 0.72, -spread), tip,
                           back(size * 0.72, spread)])

    if style == "square":
        half = size / 2
        centre_back = half
        return ("fill", [back(centre_back - half, -half), back(centre_back + half, -half),
                         back(centre_back + half, half), back(centre_back - half, half)])

    if style == "dot":
        radius = size / 2
        centre = back(radius, 0.0)
        steps = 20
        return ("fill", [(centre[0] + radius * math.cos(2 * math.pi * i / steps),
                          centre[1] + radius * math.sin(2 * math.pi * i / steps))
                         for i in range(steps)])

    if style == "diamond":
        half = size * 0.45
        return ("fill", [tip, back(half, -half), back(half * 2, 0.0),
                         back(half, half)])

    if style == "bar":
        half = size / 2
        return ("stroke", [back(0.0, -half), back(0.0, half)])

    if style == "inverted":
        # A triangle pointing back down the shaft: the tip is the notch.
        spread = size * 0.45
        return ("fill", [back(size * 0.55, 0.0), back(0.0, -spread),
                         back(0.0, spread)])

    return ("fill", [])


# -- curvature ---------------------------------------------------------------

def snap_bend(bend: float, stroke_width: float) -> float:
    """Collapse a nearly-straight arrow back to straight."""
    return 0.0 if abs(bend) < max(2.0, stroke_width * BEND_SNAP_RATIO) else bend


def middle_point(start: Point, end: Point, bend: float) -> Point:
    """Where the arrow's middle sits — the arc's apex, and its drag handle."""
    chord = _sub(end, start)
    if chord == (0.0, 0.0):
        return start
    return _add(_mid(start, end), _mul(_per(_uni(chord)), bend))


def bend_from_point(start: Point, end: Point, point: Point) -> float:
    """The bend that would put the arrow's middle under *point*."""
    chord = _sub(end, start)
    if chord == (0.0, 0.0):
        return 0.0
    return _dot(_sub(point, _mid(start, end)), _per(_uni(chord)))


def arc(start: Point, end: Point,
        bend: float) -> Optional[Tuple[Point, float, float, float]]:
    """The circle through start, end and the bent middle.

    Returns ``(centre, radius, start_angle, sweep)``, or None when the arrow is
    straight enough that a circle is the wrong description of it.
    """
    if bend == 0:
        return None
    chord = _sub(end, start)
    length = math.hypot(*chord)
    if length == 0:
        return None

    half = length / 2
    perpendicular = _per(_uni(chord))
    centre_offset = (bend * bend - half * half) / (2 * bend)
    centre = _add(_mid(start, end), _mul(perpendicular, centre_offset))
    radius = (bend * bend + half * half) / (2 * abs(bend))

    start_angle = math.atan2(start[1] - centre[1], start[0] - centre[0])
    end_angle = math.atan2(end[1] - centre[1], end[0] - centre[0])
    apex = middle_point(start, end, bend)
    apex_angle = math.atan2(apex[1] - centre[1], apex[0] - centre[0])
    return (centre, radius, start_angle,
            _sweep(start_angle, end_angle, apex_angle))


def _sweep(start_angle: float, end_angle: float, through: float) -> float:
    """The signed sweep from start to end that passes through *through*."""
    def normalize(angle: float) -> float:
        return (angle + math.pi) % (2 * math.pi) - math.pi

    direct = normalize(end_angle - start_angle)
    towards = normalize(through - start_angle)
    if direct >= 0:
        inside = 0 <= towards <= direct
    else:
        inside = direct <= towards <= 0
    if inside:
        return direct
    return direct - 2 * math.pi if direct > 0 else direct + 2 * math.pi


def arc_segments(radius: float, sweep: float) -> int:
    """How finely to flatten an arc of this size."""
    length = abs(radius * sweep)
    return int(min(max(length / ARC_SEGMENT_LENGTH, MIN_ARC_SEGMENTS),
                   MAX_ARC_SEGMENTS))


def path_points(start: Point, end: Point, bend: float,
                segments: Optional[int] = None) -> List[Point]:
    """The shaft as a polyline: two points when straight, an arc when bent."""
    resolved = arc(start, end, bend)
    if resolved is None:
        return [start, end]
    centre, radius, start_angle, sweep = resolved
    if segments is None:
        segments = arc_segments(radius, sweep)
    return [(centre[0] + radius * math.cos(start_angle + sweep * i / segments),
             centre[1] + radius * math.sin(start_angle + sweep * i / segments))
            for i in range(segments + 1)]


def direction_at(start: Point, end: Point, bend: float,
                 at_end: bool = True) -> float:
    """The angle the arrow is travelling at one of its terminals.

    On a bent arrow the head has to follow the tangent, or it points off into
    space instead of along the curve it belongs to.
    """
    resolved = arc(start, end, bend)
    if resolved is None:
        chord = _sub(end, start) if at_end else _sub(start, end)
        return math.atan2(chord[1], chord[0])

    centre, _radius, start_angle, sweep = resolved
    angle = start_angle + (sweep if at_end else 0.0)
    # The tangent is perpendicular to the radius, turned the way the arc sweeps.
    tangent = angle + (math.pi / 2 if sweep > 0 else -math.pi / 2)
    return tangent if at_end else tangent + math.pi


def trimmed(start: Point, end: Point, bend: float,
            start_trim: float = 0.0, end_trim: float = 0.0,
            segments: Optional[int] = None) -> List[Point]:
    """The shaft with each end pulled back by a head's length."""
    points = path_points(start, end, bend, segments)
    if start_trim > 0:
        points = _trim_from_start(points, start_trim)
    if end_trim > 0:
        points = list(reversed(_trim_from_start(list(reversed(points)), end_trim)))
    return points


def _trim_from_start(points: Sequence[Point], distance: float) -> List[Point]:
    """Drop *distance* of path from the front, keeping the rest."""
    if len(points) < 2 or distance <= 0:
        return list(points)
    remaining = distance
    for i in range(len(points) - 1):
        segment = math.dist(points[i], points[i + 1])
        if segment >= remaining:
            if segment == 0:
                continue
            t = remaining / segment
            cut = (points[i][0] + (points[i + 1][0] - points[i][0]) * t,
                   points[i][1] + (points[i + 1][1] - points[i][1]) * t)
            return [cut] + list(points[i + 1:])
        remaining -= segment
    # The whole path is shorter than the trim: keep the last sliver so the
    # arrow never vanishes entirely.
    return [points[-2], points[-1]]
