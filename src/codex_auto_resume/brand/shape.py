"""The corner every rounded thing is drawn with: Figma's corner smoothing (v0.6.24).

A circular corner meets its straight sides with a jump in curvature - from none to 1/R at once - and
the eye reads the jump as a slight bulge where the arc begins. Figma's construction ("Desperately
seeking squircles") runs a circular arc in the middle of the corner and joins it to
each side with one cubic Bezier whose curvature is zero at the side, so the corner eases in. How far
it eases is the smoothing: the corner then begins `(1 + smoothing) * radius` from its vertex instead
of `radius`, and 0.6 is the shape the owner approved (the Squircle board, 2026-11-15).

The formulas are the MIT-licensed figma-squircle's (`getPathParamsForCorner`). Where a side is too
short for the whole ease, the smoothing backs off until the corner fits ("back off the smoothing
until the budget is balanced"), so a radius of half the side - a pill - is a plain semicircle: chips,
switches, progress bars, badges and every ring stay round. Classic and Plain keep circular corners
(design_smoothing): Plain is Windows 11's look, Classic v0.6.2's.

This module is the geometry, and nothing else: the window draws it from `gui/SoftShape.cs` (the same
numbers, held to these by tests/test_squircle_parity.py), the popup and the notification card from
`ui/popup/gdiplus.py`, `ui/popup/elevation.py` and `notice_card.py`. Pure, and tested on any platform.

Coordinates are pixels, y down. A corner's "local" frame below has its vertex at the origin and the
shape in the quadrant u >= 0, v >= 0 (u across from the vertical side, v down from the horizontal one).
"""
from __future__ import annotations

import bisect
from collections import namedtuple
import math

from .scale import CORNER_SMOOTHING
from .tokens import design_name


# Which designs smooth their corners. A design changes paint and never layout (design.py), and a
# corner's smoothing is paint: the radius, and so every rectangle, is the same either way.
DESIGN_SMOOTHING = {"soft": CORNER_SMOOTHING, "classic": 0.0, "plain": 0.0}


def design_smoothing(design="soft") -> float:
    """How much a design smooths its corners: Soft brand.CORNER_SMOOTHING, Classic and Plain none."""
    return DESIGN_SMOOTHING[design_name(design)]


# The Codex panel's corner (owner, 2026-11-15, O11): CSS `corner-shape: superellipse(k)` where the panel's engine has
# it, and plain `border-radius` elsewhere. A superellipse is not Figma's curve and lives inside `border-radius`, so the
# panel takes the superellipse and the radius that come nearest Figma's 60 %: `reach` times the radius, at `k`. Fitted
# offline against `outline` for a corner of radius 1 (tests/test_squircle_panel.py fits it again): the two curves are
# within 0.03 of a radius of each other - half a pixel at the card's 16 px.
CSS_CORNER = {"reach": 1.57, "superellipse": 1.67}


# ------------------------------------------------------------------------------ one corner
# radius and smoothing as drawn (after the budget), p the corner's length along each side, a b c d
# the Bezier's spacings and `chord` the arc's run along each axis (figma-squircle's names).
Corner = namedtuple("Corner", "radius smoothing p a b c d chord")


def corner(radius, smoothing, budget) -> Corner:
    """One corner of `radius` smoothed by `smoothing`, in a box whose shorter side is `2 * budget`."""
    budget = max(0.0, float(budget))
    radius = max(0.0, min(float(radius), budget))
    if radius <= 0.0:
        return Corner(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    smoothing = max(0.0, min(float(smoothing), budget / radius - 1.0))
    p = min((1.0 + smoothing) * radius, budget)
    arc = 90.0 * (1.0 - smoothing)
    chord = math.sin(math.radians(arc / 2.0)) * radius * math.sqrt(2.0)
    alpha = (90.0 - arc) / 2.0
    p3_to_p4 = radius * math.tan(math.radians(alpha / 2.0))
    beta = 45.0 * smoothing
    c = p3_to_p4 * math.cos(math.radians(beta))
    d = c * math.tan(math.radians(beta))
    b = (p - chord - c - d) / 3.0
    return Corner(radius, smoothing, p, 2.0 * b, b, c, d, chord)


def smoothed(found: Corner) -> bool:
    """Whether a corner is drawn smoothed. One whose smoothing the budget took away is the circular
    corner exactly, and is drawn as one arc, as every corner was before v0.6.24."""
    return found.smoothing > 1e-9


# ------------------------------------------------------------------------------ the outline
# The four corners in the order they are drawn - top left, top right, bottom right, bottom left - each
# the top-right corner turned a quarter clockwise per step. `_TURNS[k]` maps the top-right corner's
# frame (vertex at the origin, the shape down and to the left) onto corner k's.
_TURNS = {
    "top_right": lambda x, y: (x, y),
    "bottom_right": lambda x, y: (-y, x),
    "bottom_left": lambda x, y: (-x, -y),
    "top_left": lambda x, y: (y, -x),
}
_ORDER = ("top_left", "top_right", "bottom_right", "bottom_left")
_QUADRANT = {"top_right": 270.0, "bottom_right": 0.0, "bottom_left": 90.0, "top_left": 180.0}


def _vertex(rect, name):
    left, top, right, bottom = rect
    return {"top_left": (left, top), "top_right": (right, top),
            "bottom_right": (right, bottom), "bottom_left": (left, bottom)}[name]


def corner_segments(found: Corner, vertex, name) -> list:
    """One corner's segments: ("bezier", p0, p1, p2, p3), ("arc", centre, radius, start, sweep) in
    GDI+'s degrees (clockwise from +x, y down), ("bezier", ...). A circular corner is its arc alone."""
    turn, (vx, vy) = _TURNS[name], vertex

    def at(x, y):
        tx, ty = turn(x, y)
        return (vx + tx, vy + ty)

    radius, p, a, b, c, d = found.radius, found.p, found.a, found.b, found.c, found.d
    start = _QUADRANT[name]
    centre = at(-radius, radius)
    if not smoothed(found):
        return [("arc", centre, radius, start, 90.0)]
    beta = 45.0 * found.smoothing
    return [("bezier", at(-p, 0.0), at(-p + a, 0.0), at(-p + a + b, 0.0), at(-p + a + b + c, d)),
            ("arc", centre, radius, start + beta, 90.0 - 2.0 * beta),
            ("bezier", at(-d, p - a - b - c), at(0.0, p - a - b), at(0.0, p - a), at(0.0, p))]


def outline(rect, radius, smoothing, corners=_ORDER) -> list:
    """The outline of `rect` (left, top, right, bottom) with `corners` rounded by `radius` and
    `smoothing`, as segments in drawing order; a corner not named is its vertex, ("point", vertex).
    The straight sides are what joins one segment to the next, as GDI+ joins a figure's parts. Empty
    for a box too small to round (under a pixel across), which is drawn as its rectangle."""
    left, top, right, bottom = (float(value) for value in rect)
    budget = min(right - left, bottom - top) / 2.0
    found = corner(radius, smoothing, budget)
    if found.radius * 2.0 <= 1.0:
        return []
    segments = []
    for name in _ORDER:
        vertex = _vertex((left, top, right, bottom), name)
        segments += corner_segments(found, vertex, name) if name in corners else [("point", vertex)]
    return segments


def _bezier_at(p0, p1, p2, p3, t):
    s = 1.0 - t
    return (s * s * s * p0[0] + 3 * s * s * t * p1[0] + 3 * s * t * t * p2[0] + t * t * t * p3[0],
            s * s * s * p0[1] + 3 * s * s * t * p1[1] + 3 * s * t * t * p2[1] + t * t * t * p3[1])


def flatten(segments, steps=32) -> list:
    """The outline's points: each Bezier and arc cut into `steps` straight pieces."""
    points = []
    for segment in segments:
        if segment[0] == "point":
            points.append(segment[1])
        elif segment[0] == "bezier":
            points += [_bezier_at(*segment[1:], k / float(steps)) for k in range(steps + 1)]
        else:
            (cx, cy), radius, start, sweep = segment[1:]
            for k in range(steps + 1):
                angle = math.radians(start + sweep * k / float(steps))
                points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


# ------------------------------------------------------------------------------ a corner's profile
# What a mask asks of a corner, worked out once per radius and smoothing and kept:
#
#   edge    the outline's half nearer the horizontal side, as v = f(u) for u from the corner's middle
#           (on the diagonal u = v) to p: the circle where the arc is, and the Bezier's points past it.
#           The outline is symmetric about the diagonal, so a point nearer the vertical side is asked as
#           its mirror; on this half f falls at most as steeply as the diagonal, so it is a function of u.
#   rho     the distance from the corner's centre (p, p) to the outline, by the direction t =
#           qy / (qx + qy) of a point (qx, qy) out from that centre, at RHO_STEPS steps of t. The outline
#           is convex and seen whole from the centre, so a point is inside exactly when it is nearer the
#           centre than the outline is that way, and |P - C| - rho is the distance along that ray.
#   lean    how far that ray leans off the outline's normal where it meets it, as the cosine that turns
#           a distance along the ray into one across the outline: exact next to the outline, a circle's
#           distance exactly, and the squircle's shadows within the levels tests/test_squircle_shadows.py
#           holds them to further out.
Profile = namedtuple("Profile", "corner p middle joint bezier_u bezier_v rho lean")

RHO_STEPS = 512                 # samples of rho and lean across t from 0 to 1
_HALF_STEPS = 64                # straight pieces per Bezier and per half arc
_PROFILES = {}
_UNITS = {}
_PROFILE_LIMIT = 64


def _arc_v(radius, u):
    rest = radius * radius - (radius - u) * (radius - u)
    return radius - math.sqrt(rest) if rest > 0.0 else radius


def _half_points(found: Corner, steps=_HALF_STEPS) -> list:
    """The outline's half nearer the horizontal side in the local frame, from (p, 0) to the middle."""
    radius, p, a, b, c, d = found.radius, found.p, found.a, found.b, found.c, found.d
    points = []
    if smoothed(found):
        points += [_bezier_at((p, 0.0), (p - a, 0.0), (p - a - b, 0.0), (p - a - b - c, d), k / float(steps))
                   for k in range(steps)]
        start = math.radians(270.0 - 45.0 * found.smoothing)
    else:
        start = math.radians(270.0)
    end = math.radians(225.0)
    for k in range(steps + 1):
        angle = start + (end - start) * k / float(steps)
        points.append((radius + radius * math.cos(angle), radius + radius * math.sin(angle)))
    return points


def _unit(smoothing) -> Profile:
    """A corner of radius 1 at `smoothing` (one the budget has already settled): every corner of that
    smoothing is this one made larger, since every number in `corner` is a length times the radius."""
    known = _UNITS.get(smoothing)
    if known is not None:
        return known
    found = corner(1.0, smoothing, 1e9)
    p, radius = found.p, found.radius
    half = _half_points(found)
    joint = p - found.a - found.b - found.c if smoothed(found) else radius
    bezier = sorted(point for point in half[:_HALF_STEPS + 1] if point[0] >= joint) if smoothed(found) else []
    # rho and lean by t: the half's points run from t = 1 (the side) to t = 1/2 (the diagonal).
    ts, rs, leans = [], [], []
    last = len(half) - 1
    for k in range(last, -1, -1):
        u, v = half[k]
        qx, qy = p - u, p - v
        if qx + qy <= 0.0:
            continue
        (u0, v0), (u1, v1) = half[max(0, k - 1)], half[min(last, k + 1)]
        tangent = math.hypot(u1 - u0, v1 - v0)
        r = math.hypot(qx, qy)
        ts.append(qy / (qx + qy))
        rs.append(r)
        leans.append(abs(qx * (v1 - v0) - qy * (u1 - u0)) / (r * tangent) if tangent > 0.0 and r > 0.0 else 1.0)
    rho = [0.0] * (RHO_STEPS + 1)
    lean = [1.0] * (RHO_STEPS + 1)
    found_at = bisect.bisect_left
    for k in range(RHO_STEPS // 2, RHO_STEPS + 1):
        t = k / float(RHO_STEPS)
        i = min(max(1, found_at(ts, t)), len(ts) - 1)
        t0, t1 = ts[i - 1], ts[i]
        share = min(1.0, max(0.0, (t - t0) / (t1 - t0))) if t1 > t0 else 0.0
        rho[k] = rho[RHO_STEPS - k] = rs[i - 1] + (rs[i] - rs[i - 1]) * share
        lean[k] = lean[RHO_STEPS - k] = leans[i - 1] + (leans[i] - leans[i - 1]) * share
    made = Profile(found, p, radius * (1.0 - math.sqrt(0.5)), joint, tuple(point[0] for point in bezier),
                   tuple(point[1] for point in bezier), tuple(rho), tuple(lean))
    if len(_UNITS) >= _PROFILE_LIMIT:
        _UNITS.clear()
    _UNITS[smoothing] = made
    return made


def profile(radius, smoothing, budget) -> Profile:
    """The corner's tables (see above), kept per corner as drawn: the unit corner's, made `radius` large."""
    found = corner(radius, smoothing, budget)
    key = (round(found.radius, 6), round(found.smoothing, 6))
    known = _PROFILES.get(key)
    if known is not None:
        return known
    unit, size = _unit(round(found.smoothing, 9)), found.radius
    made = Profile(found, found.p, unit.middle * size, unit.joint * size,
                   tuple(map(size.__mul__, unit.bezier_u)), tuple(map(size.__mul__, unit.bezier_v)),
                   tuple(map(size.__mul__, unit.rho)), unit.lean)
    if len(_PROFILES) >= _PROFILE_LIMIT:
        _PROFILES.clear()
    _PROFILES[key] = made
    return made


def edge_at(made: Profile, u) -> float:
    """f(u): the outline's v at u on its half nearer the horizontal side, for u from the middle to p."""
    if u >= made.p:
        return 0.0
    if u <= made.joint or len(made.bezier_u) < 2:
        return _arc_v(made.corner.radius, max(0.0, min(u, made.corner.radius)))
    us, vs = made.bezier_u, made.bezier_v
    i = min(max(1, bisect.bisect_left(us, u)), len(us) - 1)
    u0, u1 = us[i - 1], us[i]
    return vs[i - 1] + (vs[i] - vs[i - 1]) * ((u - u0) / (u1 - u0) if u1 > u0 else 0.0)


def inside_corner(made: Profile, u, v) -> bool:
    """Whether a point in a corner's local frame (vertex at the origin) is inside the outline."""
    if u < 0.0 or v < 0.0:
        return False
    if u >= made.p or v >= made.p:
        return True
    if v > u:
        u, v = v, u
    if u < made.middle:
        return False
    return v >= edge_at(made, u)


def inside(x, y, rect, radius, smoothing) -> bool:
    """Whether the point (x, y) is inside `rect` (left, top, right, bottom) rounded by `radius` and
    `smoothing`, as `outline` draws it."""
    left, top, right, bottom = (float(value) for value in rect)
    if not (left <= x <= right and top <= y <= bottom):
        return False
    made = profile(radius, smoothing, min(right - left, bottom - top) / 2.0)
    return inside_corner(made, min(x - left, right - x), min(y - top, bottom - y))


def distance(x, y, half_width, half_height, radius, smoothing) -> float:
    """Signed distance from (x, y) to the rounded box centred on the origin; inside is negative.

    Along the ray from the corner's centre, leant onto the outline's normal, in a corner (see Profile);
    across a side elsewhere. With no smoothing it is the circular corner's distance exactly, as
    ui/popup/elevation.py had it."""
    made = profile(radius, smoothing, min(half_width, half_height))
    p = made.p
    qx = abs(x) - (half_width - p)
    qy = abs(y) - (half_height - p)
    if qx > 0.0 and qy > 0.0:
        if not smoothed(made.corner):
            return math.hypot(qx, qy) - p
        k = int(qy / (qx + qy) * RHO_STEPS + 0.5)
        return (math.hypot(qx, qy) - made.rho[k]) * made.lean[k]
    return max(qx, qy) - p
