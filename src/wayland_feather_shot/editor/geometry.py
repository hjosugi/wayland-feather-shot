"""Pure geometry for the annotation editor.

No GTK, no cairo, no ``gi``: everything here is plain Python so it can run in
CI, which installs no GObject stack.

Coordinates are **page space** — the captured image's own pixel space, y-down,
origin at the image's top-left, one unit per image pixel.  A shape places its
geometry with a transform (translation plus rotation); the geometry itself is
always expressed in the shape's own *local* space.  Queries transform the point
into the shape rather than transforming the geometry out, which is what lets
every shape kind share one hit-testing and selection implementation.
"""

from __future__ import annotations

import math
from typing import Iterable, List, NamedTuple, Sequence, Tuple

Point = Tuple[float, float]

# Number of segments used when an analytic curve has to be flattened into a
# polygon (selection outlines, marquee overlap tests).
ELLIPSE_SEGMENTS = 48


# -- point helpers -----------------------------------------------------------

def rotate(p: Point, angle: float, origin: Point = (0.0, 0.0)) -> Point:
    """Rotate *p* around *origin* by *angle* radians (y-down, so positive is
    clockwise on screen)."""
    if angle == 0.0:
        return (p[0], p[1])
    c, s = math.cos(angle), math.sin(angle)
    dx, dy = p[0] - origin[0], p[1] - origin[1]
    return (origin[0] + dx * c - dy * s, origin[1] + dx * s + dy * c)


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def dist_to_segment(p: Point, a: Point, b: Point) -> float:
    """Shortest distance from *p* to the segment a-b."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0.0:
        return dist(p, a)
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def dist_to_polyline(p: Point, points: Sequence[Point], closed: bool = False) -> float:
    if not points:
        return float("inf")
    if len(points) == 1:
        return dist(p, points[0])
    best = float("inf")
    for i in range(len(points) - 1):
        best = min(best, dist_to_segment(p, points[i], points[i + 1]))
    if closed:
        best = min(best, dist_to_segment(p, points[-1], points[0]))
    return best


def point_in_polygon(p: Point, poly: Sequence[Point]) -> bool:
    """Even-odd ray cast.  Points exactly on an edge are not guaranteed either
    way; callers that care test the outline distance separately."""
    if len(poly) < 3:
        return False
    x, y = p
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


def _orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Proper or touching intersection of segments a-b and c-d."""
    d1, d2 = _orient(c, d, a), _orient(c, d, b)
    d3, d4 = _orient(a, b, c), _orient(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    # Collinear touching cases.
    for pa, pb, pc, dd in ((c, d, a, d1), (c, d, b, d2), (a, b, c, d3), (a, b, d, d4)):
        if dd == 0.0 and dist_to_segment(pc, pa, pb) == 0.0:
            return True
    return False


def polylines_cross(a: Sequence[Point], b: Sequence[Point]) -> bool:
    for i in range(len(a) - 1):
        for j in range(len(b) - 1):
            if segments_intersect(a[i], a[i + 1], b[j], b[j + 1]):
                return True
    return False


def ellipse_points(w: float, h: float, segments: int = ELLIPSE_SEGMENTS) -> List[Point]:
    """An axis-aligned ellipse inscribed in (0, 0, w, h), flattened."""
    rx, ry = w / 2.0, h / 2.0
    cx, cy = rx, ry
    step = 2.0 * math.pi / segments
    return [(cx + rx * math.cos(i * step), cy + ry * math.sin(i * step))
            for i in range(segments)]


# -- boxes -------------------------------------------------------------------

class Box(NamedTuple):
    x: float
    y: float
    w: float
    h: float

    @property
    def corners(self) -> List[Point]:
        """Clockwise from the top-left."""
        return [(self.x, self.y), (self.x + self.w, self.y),
                (self.x + self.w, self.y + self.h), (self.x, self.y + self.h)]

    @property
    def center(self) -> Point:
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def point(self, u: float, v: float) -> Point:
        """The point at normalized position (u, v) inside the box."""
        return (self.x + self.w * u, self.y + self.h * v)

    def contains(self, p: Point) -> bool:
        return (self.x <= p[0] <= self.x + self.w
                and self.y <= p[1] <= self.y + self.h)

    def expand(self, margin: float) -> "Box":
        return Box(self.x - margin, self.y - margin,
                   self.w + 2 * margin, self.h + 2 * margin)

    def intersects(self, other: "Box") -> bool:
        return not (other.x > self.x + self.w or other.x + other.w < self.x
                    or other.y > self.y + self.h or other.y + other.h < self.y)

    @staticmethod
    def from_points(points: Iterable[Point]) -> "Box":
        xs: List[float] = []
        ys: List[float] = []
        for x, y in points:
            xs.append(x)
            ys.append(y)
        if not xs:
            return Box(0.0, 0.0, 0.0, 0.0)
        return Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    @staticmethod
    def union(boxes: Sequence["Box"]) -> "Box":
        points: List[Point] = []
        for b in boxes:
            points.append((b.x, b.y))
            points.append((b.x + b.w, b.y + b.h))
        return Box.from_points(points)


def norm_rect(x0: float, y0: float, x1: float, y1: float) -> Tuple[float, float, float, float]:
    """Two dragged corners as (x, y, w, h)."""
    return (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))


# -- geometry primitives -----------------------------------------------------

class Geometry:
    """A shape's outline in its own local space.

    ``hit_test`` answers "did the pointer grab this?": within *margin* of the
    outline always counts, and the interior counts only for shapes that are
    actually filled — clicking through the middle of a hollow rectangle should
    reach whatever is behind it.
    """

    filled = False

    @property
    def vertices(self) -> List[Point]:
        raise NotImplementedError

    @property
    def closed(self) -> bool:
        return True

    @property
    def bounds(self) -> Box:
        return Box.from_points(self.vertices)

    def hit_test(self, p: Point, margin: float = 0.0, hit_inside: bool = False) -> bool:
        verts = self.vertices
        if not self.bounds.expand(margin).contains(p):
            return False
        if dist_to_polyline(p, verts, closed=self.closed) <= margin:
            return True
        return bool(hit_inside and self.closed and point_in_polygon(p, verts))

    def overlaps_polygon(self, poly: Sequence[Point]) -> bool:
        """Whether a marquee polygon touches this geometry at all."""
        verts = self.vertices
        if not verts:
            return False
        if not self.bounds.intersects(Box.from_points(poly)):
            return False
        if any(point_in_polygon(v, poly) for v in verts):
            return True
        if self.closed and any(point_in_polygon(p, verts) for p in poly):
            return True
        ring = list(verts) + ([verts[0]] if self.closed and len(verts) > 2 else [])
        closed_poly = list(poly) + [poly[0]]
        return polylines_cross(ring, closed_poly)


class Rect2d(Geometry):
    def __init__(self, w: float, h: float, filled: bool = False):
        self.w, self.h, self.filled = w, h, filled

    @property
    def vertices(self) -> List[Point]:
        return Box(0.0, 0.0, self.w, self.h).corners

    @property
    def bounds(self) -> Box:
        return Box(0.0, 0.0, self.w, self.h)


class Ellipse2d(Geometry):
    def __init__(self, w: float, h: float, filled: bool = False):
        self.w, self.h, self.filled = w, h, filled

    @property
    def vertices(self) -> List[Point]:
        return ellipse_points(self.w, self.h)

    @property
    def bounds(self) -> Box:
        return Box(0.0, 0.0, self.w, self.h)

    def hit_test(self, p, margin=0.0, hit_inside=False):
        rx, ry = self.w / 2.0, self.h / 2.0
        if rx <= 0 or ry <= 0:
            return dist(p, (rx, ry)) <= margin
        dx, dy = (p[0] - rx) / rx, (p[1] - ry) / ry
        radial = math.hypot(dx, dy)
        if hit_inside and radial <= 1.0:
            return True
        # Approximate the outline band by scaling the margin into unit space.
        band = margin / max(min(rx, ry), 1e-6)
        return abs(radial - 1.0) <= band


class Circle2d(Ellipse2d):
    def __init__(self, diameter: float, filled: bool = True):
        super().__init__(diameter, diameter, filled)


class Polyline2d(Geometry):
    """An open path — a pen stroke, a straight line, an arrow shaft."""

    def __init__(self, points: Sequence[Point]):
        self.points = list(points)

    @property
    def vertices(self) -> List[Point]:
        return self.points

    @property
    def closed(self) -> bool:
        return False


class Polygon2d(Geometry):
    def __init__(self, points: Sequence[Point], filled: bool = False):
        self.points = list(points)
        self.filled = filled

    @property
    def vertices(self) -> List[Point]:
        return self.points


class Group2d(Geometry):
    """Several primitives acting as one shape (a step arrow's shaft plus its
    badge, say).  A hit on any part is a hit on the group."""

    def __init__(self, parts: Sequence[Geometry]):
        self.parts = list(parts)

    @property
    def vertices(self) -> List[Point]:
        out: List[Point] = []
        for part in self.parts:
            out.extend(part.vertices)
        return out

    @property
    def bounds(self) -> Box:
        return Box.union([p.bounds for p in self.parts]) if self.parts else Box(0, 0, 0, 0)

    def hit_test(self, p, margin=0.0, hit_inside=False):
        return any(part.hit_test(p, margin, hit_inside or part.filled)
                   for part in self.parts)

    def overlaps_polygon(self, poly):
        return any(part.overlaps_polygon(poly) for part in self.parts)
