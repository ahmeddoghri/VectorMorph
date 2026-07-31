"""SVG path parsing and flattening.

Morphing between two vector shapes needs both shapes expressed in the same
terms. This module turns an SVG ``d`` attribute into a list of subpaths, each a
flat list of ``(x, y)`` points, by sampling every curve and arc at a fixed
resolution. Once both shapes are polylines, interpolation is well defined.

Only geometry is preserved. Fills, strokes, and gradients are handled at the
document level in :mod:`vectormorph.document`, not here.
"""

from __future__ import annotations

import math
import re
from typing import List, Sequence, Tuple

Point = Tuple[float, float]
Subpath = List[Point]

# One token is either a command letter or a number. SVG numbers are permissive:
# leading sign, optional decimal point, optional exponent.
_TOKEN = re.compile(r"[MmZzLlHhVvCcSsQqTtAa]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")

_ARG_COUNT = {
    "M": 2, "L": 2, "H": 1, "V": 1,
    "C": 6, "S": 4, "Q": 4, "T": 2,
    "A": 7, "Z": 0,
}

#: Samples used to flatten one curve segment. Fixed rather than adaptive so that
#: two different shapes always flatten to comparable point densities, and so
#: that output is byte-for-byte reproducible across machines.
CURVE_SAMPLES = 24


def tokenize(d: str) -> List[str]:
    """Split a path ``d`` attribute into command and number tokens."""
    return _TOKEN.findall(d)


def _cubic(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    mt = 1.0 - t
    a, b, c, dd = mt**3, 3 * mt * mt * t, 3 * mt * t * t, t**3
    return (
        a * p0[0] + b * p1[0] + c * p2[0] + dd * p3[0],
        a * p0[1] + b * p1[1] + c * p2[1] + dd * p3[1],
    )


def _quad(p0: Point, p1: Point, p2: Point, t: float) -> Point:
    mt = 1.0 - t
    a, b, c = mt * mt, 2 * mt * t, t * t
    return (
        a * p0[0] + b * p1[0] + c * p2[0],
        a * p0[1] + b * p1[1] + c * p2[1],
    )


def _sample_arc(
    start: Point, rx: float, ry: float, rotation: float,
    large_arc: bool, sweep: bool, end: Point,
) -> List[Point]:
    """Flatten an elliptical arc using endpoint-to-center parameterization.

    Follows the SVG 1.1 implementation notes (F.6.5), including the radius
    correction step for radii too small to span the two endpoints.
    """
    x1, y1 = start
    x2, y2 = end
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [end]

    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rotation)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)

    dx2, dy2 = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    # Scale up radii that are too small to reach between the endpoints.
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1.0:
        scale = math.sqrt(lam)
        rx, ry = rx * scale, ry * scale

    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    factor = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large_arc == sweep:
        factor = -factor

    cxp = factor * rx * y1p / ry
    cyp = -factor * ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2.0

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        norm = math.hypot(ux, uy) * math.hypot(vx, vy)
        if norm == 0:
            return 0.0
        a = math.acos(max(-1.0, min(1.0, dot / norm)))
        return -a if (ux * vy - uy * vx) < 0 else a

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle(
        (x1p - cxp) / rx, (y1p - cyp) / ry,
        (-x1p - cxp) / rx, (-y1p - cyp) / ry,
    )
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    points: List[Point] = []
    for i in range(1, CURVE_SAMPLES + 1):
        theta = theta1 + delta * (i / CURVE_SAMPLES)
        px = cos_phi * rx * math.cos(theta) - sin_phi * ry * math.sin(theta) + cx
        py = sin_phi * rx * math.cos(theta) + cos_phi * ry * math.sin(theta) + cy
        points.append((px, py))
    return points


def parse_path(d: str) -> List[Subpath]:
    """Flatten an SVG path ``d`` attribute into subpaths of sampled points.

    Returns one point list per subpath (each ``M`` starts a new one). Closed
    subpaths are not given a duplicate final point; closure is implied.
    """
    tokens = tokenize(d)
    subpaths: List[Subpath] = []
    current: Subpath = []

    i = 0
    cursor: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)
    command = ""
    # Reflected control points, for the shorthand S and T commands.
    last_cubic_ctrl: Point | None = None
    last_quad_ctrl: Point | None = None

    def flush() -> None:
        nonlocal current
        if len(current) >= 2:
            subpaths.append(current)
        current = []

    while i < len(tokens):
        token = tokens[i]
        if token.isalpha():
            command = token
            i += 1
        elif not command:
            raise ValueError(f"path data starts with a number, not a command: {d[:40]!r}")
        # An implicit repeat of M continues as L, per the SVG spec.
        elif command in "Mm":
            command = "L" if command == "M" else "l"

        upper = command.upper()
        relative = command.islower()
        n = _ARG_COUNT[upper]
        args = [float(a) for a in tokens[i : i + n]]
        if len(args) < n:
            break  # Truncated path data; keep whatever parsed cleanly.
        i += n

        if upper == "M":
            flush()
            cursor = (args[0] + cursor[0], args[1] + cursor[1]) if relative else (args[0], args[1])
            start = cursor
            current = [cursor]
            last_cubic_ctrl = last_quad_ctrl = None

        elif upper == "Z":
            if current:
                flush()
            cursor = start
            current = [cursor]
            last_cubic_ctrl = last_quad_ctrl = None

        elif upper == "L":
            cursor = (args[0] + cursor[0], args[1] + cursor[1]) if relative else (args[0], args[1])
            current.append(cursor)
            last_cubic_ctrl = last_quad_ctrl = None

        elif upper == "H":
            x = args[0] + cursor[0] if relative else args[0]
            cursor = (x, cursor[1])
            current.append(cursor)
            last_cubic_ctrl = last_quad_ctrl = None

        elif upper == "V":
            y = args[0] + cursor[1] if relative else args[0]
            cursor = (cursor[0], y)
            current.append(cursor)
            last_cubic_ctrl = last_quad_ctrl = None

        elif upper in ("C", "S"):
            if upper == "C":
                pts = [
                    (args[0], args[1]), (args[2], args[3]), (args[4], args[5])
                ]
                if relative:
                    pts = [(px + cursor[0], py + cursor[1]) for px, py in pts]
                c1, c2, end = pts
            else:
                pts = [(args[0], args[1]), (args[2], args[3])]
                if relative:
                    pts = [(px + cursor[0], py + cursor[1]) for px, py in pts]
                c2, end = pts
                # Reflect the previous control point about the current cursor.
                c1 = (
                    (2 * cursor[0] - last_cubic_ctrl[0], 2 * cursor[1] - last_cubic_ctrl[1])
                    if last_cubic_ctrl else cursor
                )
            for s in range(1, CURVE_SAMPLES + 1):
                current.append(_cubic(cursor, c1, c2, end, s / CURVE_SAMPLES))
            cursor, last_cubic_ctrl, last_quad_ctrl = end, c2, None

        elif upper in ("Q", "T"):
            if upper == "Q":
                pts = [(args[0], args[1]), (args[2], args[3])]
                if relative:
                    pts = [(px + cursor[0], py + cursor[1]) for px, py in pts]
                ctrl, end = pts
            else:
                end = (args[0] + cursor[0], args[1] + cursor[1]) if relative else (args[0], args[1])
                ctrl = (
                    (2 * cursor[0] - last_quad_ctrl[0], 2 * cursor[1] - last_quad_ctrl[1])
                    if last_quad_ctrl else cursor
                )
            for s in range(1, CURVE_SAMPLES + 1):
                current.append(_quad(cursor, ctrl, end, s / CURVE_SAMPLES))
            cursor, last_quad_ctrl, last_cubic_ctrl = end, ctrl, None

        elif upper == "A":
            end = (args[5] + cursor[0], args[6] + cursor[1]) if relative else (args[5], args[6])
            current.extend(
                _sample_arc(cursor, args[0], args[1], args[2], bool(args[3]), bool(args[4]), end)
            )
            cursor = end
            last_cubic_ctrl = last_quad_ctrl = None

    flush()
    return subpaths


def points_to_path(subpaths: Sequence[Subpath], precision: int = 2) -> str:
    """Serialize subpaths back into an SVG ``d`` attribute.

    Coordinates are rounded to ``precision`` decimals, which keeps generated
    files small and makes output stable across platforms with different
    float-to-string behavior.
    """
    parts: List[str] = []
    for sub in subpaths:
        if len(sub) < 2:
            continue
        fmt = f"{{:.{precision}f}}"
        parts.append("M" + fmt.format(sub[0][0]) + "," + fmt.format(sub[0][1]))
        for x, y in sub[1:]:
            parts.append("L" + fmt.format(x) + "," + fmt.format(y))
        parts.append("Z")
    return "".join(parts)


def polygon_area(points: Sequence[Point]) -> float:
    """Signed area via the shoelace formula. Sign encodes winding direction."""
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def centroid(points: Sequence[Point]) -> Point:
    """Area-weighted centroid, falling back to the mean for degenerate shapes."""
    area = polygon_area(points)
    if abs(area) < 1e-9:
        n = max(1, len(points))
        return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)
    cx = cy = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return (cx / (6.0 * area), cy / (6.0 * area))
