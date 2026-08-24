"""Variable-width freehand strokes.

A Python port of the `perfect-freehand` algorithm (MIT, Steve Ruiz), the same
pipeline Screendrop's annotation engine uses.

Joining raw pointer samples with `line_to` at a constant width gives a stroke
that is visibly polygonal when drawn fast, lumpy when drawn slow, and uniformly
dead either way: circling a UI element looks like a rubber band rather than a
marker.  This runs the samples through four stages instead:

1. **Streamline** — pull each point towards its predecessor, which removes hand
   jitter before anything downstream can amplify it.
2. **Pressure** — with no pen to ask, pressure is simulated from speed: fast
   segments are thin, slow ones are thick, which is what gives a stroke its
   taper.
3. **Radius** — pressure, thinning and any end taper become a per-point radius.
4. **Outline** — walk the centreline emitting left and right offset points at
   that radius, round off the corners and cap the ends, and fill the resulting
   polygon rather than stroking a path.

Pure Python: no GTK, no cairo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]

# perfect-freehand's own constant: a plain pi leaves a seam in the round caps.
FIXED_PI = math.pi + 0.0001
MIN_PRESSURE = 0.025
RATE_OF_PRESSURE_CHANGE = 0.275
# Steps around a round cap or a sharp corner.  More is smoother and slower;
# 13 is what the reference uses and it is indistinguishable from a circle at
# annotation stroke widths.
CAP_STEPS = 13


def ease_out_sine(t: float) -> float:
    return math.sin((t * math.pi) / 2)


def ease_out_quad(t: float) -> float:
    return t * (2 - t)


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def linear(t: float) -> float:
    return t


@dataclass(frozen=True)
class StrokeOptions:
    """Tuning for one stroke.  The defaults are the reference's mouse preset."""

    size: float = 16.0
    #: How much speed thins the stroke.  0 gives a constant width.
    thinning: float = 0.5
    #: How far the outline is allowed to round off corners.
    smoothing: float = 0.62
    #: How hard the input points are pulled towards each other.
    streamline: float = 0.62
    #: Taper length at each end; 0 for none.
    taper_start: float = 0.0
    taper_end: float = 0.0
    #: Whether the stroke is finished (an unfinished one keeps its end open).
    last: bool = True

    def easing(self, t: float) -> float:
        return ease_out_sine(t)


def options_for(stroke_width: float, complete: bool = True) -> StrokeOptions:
    """Options for a stroke authored at *stroke_width* page units.

    Streamline rises with the stroke width the way the reference does: a fat
    marker should smooth more than a fine pen, because its own width already
    hides the detail that smoothing would remove.
    """
    streamline = _modulate(stroke_width, (9.0, 16.0), (0.64, 0.74), clamp=True)
    return StrokeOptions(size=stroke_width, thinning=0.5, smoothing=0.62,
                         streamline=streamline, last=complete)


def _modulate(value: float, source: Tuple[float, float],
              target: Tuple[float, float], clamp: bool = False) -> float:
    a, b = source
    c, d = target
    result = c + ((value - a) / (b - a)) * (d - c)
    if clamp:
        low, high = (c, d) if c < d else (d, c)
        return min(max(result, low), high)
    return result


# -- vector helpers ----------------------------------------------------------

def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Point, s: float) -> Point:
    return (a[0] * s, a[1] * s)


def _per(a: Point) -> Point:
    """The left-hand perpendicular."""
    return (a[1], -a[0])


def _neg(a: Point) -> Point:
    return (-a[0], -a[1])


def _dpr(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _dist2(a: Point, b: Point) -> float:
    dx, dy = a[0] - b[0], a[1] - b[1]
    return dx * dx + dy * dy


def _uni(a: Point) -> Point:
    length = math.hypot(a[0], a[1])
    return a if length == 0 else (a[0] / length, a[1] / length)


def _lerp_vec(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _rotate_around(point: Point, centre: Point, angle: float) -> Point:
    s, c = math.sin(angle), math.cos(angle)
    px, py = point[0] - centre[0], point[1] - centre[1]
    return (px * c - py * s + centre[0], px * s + py * c + centre[1])


# -- stage 1 & 2: streamlined points ----------------------------------------

@dataclass
class StrokePoint:
    point: Point
    pressure: float
    vector: Point
    distance: float
    running_length: float


def get_stroke_points(points: Sequence[Point],
                      options: StrokeOptions) -> List[StrokePoint]:
    """Streamline the raw samples and measure them.

    Each point ends up with the unit vector pointing *back* at its predecessor,
    the distance it travelled, and how far along the stroke it sits — which is
    everything the radius and outline stages need.
    """
    if not points:
        return []

    t = 0.15 + (1 - options.streamline) * 0.85
    pts: List[Point] = [(float(p[0]), float(p[1])) for p in points]

    # A stroke of one point is a dot; duplicate it so it still has a direction.
    if len(pts) == 1:
        pts = [pts[0], (pts[0][0] + 1.0, pts[0][1] + 1.0)]

    result = [StrokePoint(point=pts[0], pressure=0.5, vector=(1.0, 1.0),
                          distance=0.0, running_length=0.0)]
    previous = pts[0]
    running = 0.0

    for i in range(1, len(pts)):
        raw = pts[i]
        # The last point of a finished stroke lands exactly where the pointer
        # was, so the stroke ends where the user let go rather than short of it.
        if options.last and i == len(pts) - 1:
            point = raw
        else:
            point = _lerp_vec(previous, raw, t)

        if _dist2(previous, point) < 1e-8:
            continue

        distance = _dist(previous, point)
        running += distance
        result.append(StrokePoint(
            point=point,
            pressure=0.5,
            vector=_uni(_sub(previous, point)),
            distance=distance,
            running_length=running,
        ))
        previous = point

    # The first point has no predecessor to point at, so it borrows the second's
    # direction; otherwise the start cap would face an arbitrary way.
    if len(result) > 1:
        result[0].vector = result[1].vector
    return result


# -- stage 3: radii ----------------------------------------------------------

def _radii(stroke_points: Sequence[StrokePoint],
           options: StrokeOptions) -> List[float]:
    size = options.size
    thinning = options.thinning
    total_length = stroke_points[-1].running_length

    if thinning == 0:
        radii = [size / 2] * len(stroke_points)
    else:
        radii = []
        previous_pressure = stroke_points[0].pressure
        for sp in stroke_points:
            # Simulated pressure: the further this point travelled from the
            # last, the faster the pointer was moving, and the thinner the
            # stroke gets.  Eased so the width changes smoothly rather than
            # tracking every jitter in the sample rate.
            speed = min(1.0, sp.distance / size) if size else 0.0
            target = min(1.0, 1.0 - speed)
            pressure = min(1.0, previous_pressure
                           + (target - previous_pressure)
                           * (speed * RATE_OF_PRESSURE_CHANGE))
            previous_pressure = pressure
            radii.append(size * options.easing(0.5 - thinning * (0.5 - pressure)))

    taper_start = options.taper_start
    taper_end = options.taper_end
    if taper_start or taper_end:
        for i, sp in enumerate(stroke_points):
            start_scale = (ease_out_quad(sp.running_length / taper_start)
                           if taper_start and sp.running_length < taper_start
                           else 1.0)
            remaining = total_length - sp.running_length
            end_scale = (ease_out_cubic(remaining / taper_end)
                         if taper_end and remaining < taper_end else 1.0)
            radii[i] = max(0.01, radii[i] * min(start_scale, end_scale))

    # A stroke shorter than its own width is a dot: give every point the same
    # radius so it comes out round instead of wedge-shaped.
    if total_length < size:
        radius = max(radii) if radii else size / 2
        radii = [radius] * len(radii)
    return radii


# -- stage 4: the outline ----------------------------------------------------

def get_stroke_outline(stroke_points: Sequence[StrokePoint],
                       options: StrokeOptions) -> List[Point]:
    """The filled polygon for a set of stroke points."""
    if not stroke_points:
        return []

    size = options.size
    radii = _radii(stroke_points, options)
    total_length = stroke_points[-1].running_length

    # A dot: no direction worth following, so just draw the circle.
    if len(stroke_points) < 2 or total_length < size / 2:
        return _circle(stroke_points[0].point, max(radii[0], size / 3))

    left: List[Point] = []
    right: List[Point] = []
    min_distance = (size * options.smoothing) ** 2

    previous_vector = stroke_points[0].vector
    previous_left = stroke_points[0].point
    previous_right = stroke_points[0].point

    for i, sp in enumerate(stroke_points):
        radius = radii[i]
        point = sp.point
        vector = sp.vector

        next_vector = (stroke_points[i + 1].vector
                       if i < len(stroke_points) - 1 else vector)
        next_dpr = (_dpr(vector, next_vector)
                    if i < len(stroke_points) - 1 else 1.0)
        previous_dpr = _dpr(vector, previous_vector)

        # A hairpin: the stroke doubles back on itself, so the outline has to
        # travel all the way around the point instead of cutting the corner.
        is_sharp = previous_dpr < 0 and i > 0
        next_is_sharp = i < len(stroke_points) - 1 and next_dpr < 0

        if is_sharp or next_is_sharp:
            offset = _mul(_per(previous_vector), radius)
            for step in range(CAP_STEPS + 1):
                t = step / CAP_STEPS
                left.append(_rotate_around(_sub(point, offset), point,
                                           FIXED_PI * t))
                right.append(_rotate_around(_add(point, offset), point,
                                            FIXED_PI * -t))
            previous_left, previous_right = left[-1], right[-1]
            if next_is_sharp:
                previous_vector = vector
            continue

        # A normal point: offset perpendicular to the direction the stroke is
        # heading, blended with where it is about to head so corners round off.
        previous_vector = vector
        offset = _mul(_per(_lerp_vec(next_vector, vector, next_dpr)), radius)

        candidate_left = _sub(point, offset)
        candidate_right = _add(point, offset)
        # Skip points that barely moved: they add vertices without adding shape,
        # and they make the smoothed outline wobble.
        first_or_last = i <= 1 or i == len(stroke_points) - 1
        if first_or_last or _dist2(previous_left, candidate_left) > min_distance:
            left.append(candidate_left)
            previous_left = candidate_left
        if first_or_last or _dist2(previous_right, candidate_right) > min_distance:
            right.append(candidate_right)
            previous_right = candidate_right

    first_point = stroke_points[0].point
    last_point = stroke_points[-1].point
    start_cap = _semicircle(first_point, stroke_points[0].vector, radii[0])
    end_cap = _semicircle(last_point, _neg(stroke_points[-1].vector), radii[-1])

    # Right side reversed, so the polygon runs down one side and back up the
    # other with the caps joining them.
    return start_cap + left + end_cap + list(reversed(right))


def _semicircle(centre: Point, vector: Point, radius: float) -> List[Point]:
    """Half a circle around *centre*, starting perpendicular to *vector*."""
    start = _add(centre, _mul(_per(vector), radius))
    return [_rotate_around(start, centre, FIXED_PI * (step / CAP_STEPS))
            for step in range(CAP_STEPS + 1)]


def _circle(centre: Point, radius: float, steps: int = CAP_STEPS * 2) -> List[Point]:
    return [(centre[0] + radius * math.cos(2 * math.pi * i / steps),
             centre[1] + radius * math.sin(2 * math.pi * i / steps))
            for i in range(steps)]


def get_stroke(points: Sequence[Point],
               options: Optional[StrokeOptions] = None) -> List[Point]:
    """The filled outline for a run of raw pointer samples."""
    options = options or StrokeOptions()
    return get_stroke_outline(get_stroke_points(points, options), options)


def stroke_radii(points: Sequence[Point],
                 options: Optional[StrokeOptions] = None) -> List[float]:
    """The per-point radius the outline is built from.

    Exposed because it is the part worth asserting on: whether a stroke
    actually thins where it was drawn fast.
    """
    options = options or StrokeOptions()
    stroke_points = get_stroke_points(points, options)
    return _radii(stroke_points, options) if stroke_points else []


def centerline(points: Sequence[Point],
               options: Optional[StrokeOptions] = None) -> List[Point]:
    """Just the streamlined centreline.

    Hit-testing uses this rather than the outline: it is what the stroke looks
    like it follows, it costs a fraction as much, and it keeps what you grab in
    step with what you see.
    """
    options = options or StrokeOptions()
    return [sp.point for sp in get_stroke_points(points, options)]
