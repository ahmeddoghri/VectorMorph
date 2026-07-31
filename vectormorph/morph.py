"""Shape correspondence and interpolation.

Interpolating between two polygons point-by-point only looks right if the two
point lists correspond: same count, same winding, and roughly the same starting
corner. Lerping raw parsed geometry instead produces the classic tangled-mess
morph, where the shape turns inside out on its way across.

This module fixes all three problems before interpolating:

1. :func:`resample` gives every subpath the same point count, spaced evenly by
   arc length rather than by original vertex index.
2. :func:`match_subpaths` pairs source and target subpaths by area and position,
   and collapses any unmatched subpath to a point so it grows out of, or
   shrinks into, the nearest real geometry.
3. :func:`align_rotation` rolls the starting index of each target ring to
   minimize total travel, and reverses winding when that helps.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from .paths import Point, Subpath, centroid, polygon_area

#: Points per ring after resampling. Higher is smoother and larger on disk;
#: 64 keeps a letterform readable while staying well under a kilobyte per frame.
DEFAULT_SAMPLES = 64


def _perimeter(points: Sequence[Point], closed: bool = True) -> List[float]:
    """Cumulative arc length at each vertex, starting at 0."""
    lengths = [0.0]
    n = len(points)
    limit = n if closed else n - 1
    for i in range(limit):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        lengths.append(lengths[-1] + math.hypot(x2 - x1, y2 - y1))
    return lengths


def resample(points: Sequence[Point], count: int = DEFAULT_SAMPLES) -> Subpath:
    """Resample a closed ring to exactly ``count`` evenly spaced points.

    Spacing is uniform in arc length, so a shape described with many vertices
    on one side and few on another still morphs at a constant rate.
    """
    if len(points) < 2:
        return [points[0] if points else (0.0, 0.0)] * count

    cumulative = _perimeter(points, closed=True)
    total = cumulative[-1]
    if total <= 1e-12:
        return [points[0]] * count

    result: List[Point] = []
    n = len(points)
    seg = 0
    for i in range(count):
        target = total * i / count
        while seg < len(cumulative) - 2 and cumulative[seg + 1] < target:
            seg += 1
        span = cumulative[seg + 1] - cumulative[seg]
        t = 0.0 if span <= 1e-12 else (target - cumulative[seg]) / span
        x1, y1 = points[seg % n]
        x2, y2 = points[(seg + 1) % n]
        result.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    return result


def align_rotation(source: Sequence[Point], target: Sequence[Point]) -> Subpath:
    """Roll and possibly reverse ``target`` so it lines up with ``source``.

    Tries every rotation of the target ring in both winding directions and
    keeps whichever minimizes the sum of squared point-to-point distances.
    That is O(n^2) in the ring size, which at 64 points is a few thousand
    operations, so it stays cheap enough to run per subpath per morph.
    """
    n = len(source)
    if n == 0 or len(target) != n:
        return list(target)

    best_cost = float("inf")
    best: Subpath = list(target)

    for candidate in (list(target), list(reversed(target))):
        for offset in range(n):
            cost = 0.0
            for i in range(n):
                sx, sy = source[i]
                tx, ty = candidate[(i + offset) % n]
                cost += (sx - tx) ** 2 + (sy - ty) ** 2
                if cost >= best_cost:
                    break  # Already worse than the incumbent; abandon early.
            if cost < best_cost:
                best_cost = cost
                best = candidate[offset:] + candidate[:offset]
    return best


def match_subpaths(
    source: Sequence[Subpath], target: Sequence[Subpath], samples: int = DEFAULT_SAMPLES
) -> Tuple[List[Subpath], List[Subpath]]:
    """Pair up subpaths and pad both sides to equal length.

    Subpaths are sorted by descending absolute area so the dominant shape maps
    to the dominant shape, rather than to whichever hole happened to be listed
    first. When one side has fewer subpaths, the missing entries become
    zero-area rings collapsed at the centroid of their partner, which reads as
    a clean grow-in or shrink-out.

    Winding direction is deliberately left as authored. Under the ``nonzero``
    fill rule a hole is exactly a ring wound against its parent, so forcing a
    uniform direction here would fill in every hole. :func:`align_rotation`
    still considers a reversed target, and picks it only when reversing
    genuinely shortens the path each point travels.
    """
    src = [resample(s, samples) for s in source if len(s) >= 2]
    dst = [resample(s, samples) for s in target if len(s) >= 2]

    if not src and not dst:
        return [], []
    src = src or [[(0.0, 0.0)] * samples]
    dst = dst or [[(0.0, 0.0)] * samples]

    src.sort(key=lambda r: abs(polygon_area(r)), reverse=True)
    dst.sort(key=lambda r: abs(polygon_area(r)), reverse=True)

    while len(src) < len(dst):
        # Collapse to the centroid of the partner ring it will grow out of.
        cx, cy = centroid(dst[len(src)])
        src.append([(cx, cy)] * samples)
    while len(dst) < len(src):
        cx, cy = centroid(src[len(dst)])
        dst.append([(cx, cy)] * samples)

    aligned_dst = [align_rotation(s, d) for s, d in zip(src, dst)]
    return src, aligned_dst


def interpolate(
    source: Sequence[Subpath], target: Sequence[Subpath], t: float
) -> List[Subpath]:
    """Linearly interpolate matched subpaths at progress ``t`` in [0, 1].

    Expects the output of :func:`match_subpaths`: equal subpath counts and
    equal point counts. ``t`` is already eased by the caller.
    """
    frames: List[Subpath] = []
    for s_ring, t_ring in zip(source, target):
        frames.append(
            [
                (sx + (tx - sx) * t, sy + (ty - sy) * t)
                for (sx, sy), (tx, ty) in zip(s_ring, t_ring)
            ]
        )
    return frames
