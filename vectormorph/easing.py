"""Easing curves for morph interpolation.

Every easing function maps a normalized time ``t`` in [0, 1] onto an eased
progress in [0, 1]. Endpoints are exact: ``f(0) == 0`` and ``f(1) == 1`` for
every curve here, so a morph always starts on the source shape and lands on
the target shape regardless of which curve you pick.
"""

from __future__ import annotations

import math
from typing import Callable, Dict

Easing = Callable[[float], float]


def linear(t: float) -> float:
    return t


def ease_in(t: float) -> float:
    return t * t * t


def ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t: float) -> float:
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - ((-2.0 * t + 2.0) ** 3) / 2.0


def bounce(t: float) -> float:
    """Bounce-out: overshoot decays into the target."""
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


def elastic(t: float) -> float:
    """Elastic-out: springs past the target and settles."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    c4 = (2.0 * math.pi) / 3.0
    return 2.0 ** (-10.0 * t) * math.sin((t * 10.0 - 0.75) * c4) + 1.0


def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> Easing:
    """Build a CSS-style ``cubic-bezier(x1, y1, x2, y2)`` easing function.

    Control points P0=(0,0) and P3=(1,1) are fixed, matching the CSS timing
    function definition. The curve is solved for y at a given x with bisection,
    which is slower than Newton but cannot diverge on the near-vertical curves
    people actually write.
    """

    def _bez(a: float, b: float, t: float) -> float:
        mt = 1.0 - t
        return 3.0 * mt * mt * t * a + 3.0 * mt * t * t * b + t * t * t

    def curve(t: float) -> float:
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2.0
            if _bez(x1, x2, mid) < t:
                lo = mid
            else:
                hi = mid
        return _bez(y1, y2, (lo + hi) / 2.0)

    return curve


#: Named easing curves available to the CLI and the web UI.
EASINGS: Dict[str, Easing] = {
    "linear": linear,
    "ease-in": ease_in,
    "ease-out": ease_out,
    "ease-in-out": ease_in_out,
    "bounce": bounce,
    "elastic": elastic,
    # CSS keyword equivalents, so a designer can paste what they already know.
    "css-ease": cubic_bezier(0.25, 0.1, 0.25, 1.0),
    "css-ease-in-out": cubic_bezier(0.42, 0.0, 0.58, 1.0),
}


def get_easing(name: str) -> Easing:
    """Look up an easing by name, or parse a ``cubic-bezier(...)`` literal."""
    key = name.strip().lower()
    if key in EASINGS:
        return EASINGS[key]
    if key.startswith("cubic-bezier"):
        inner = key[key.index("(") + 1 : key.rindex(")")]
        parts = [float(p) for p in inner.split(",")]
        if len(parts) != 4:
            raise ValueError(f"cubic-bezier needs 4 numbers, got {len(parts)}")
        return cubic_bezier(*parts)
    raise ValueError(
        f"unknown easing {name!r}; try one of {', '.join(sorted(EASINGS))} "
        "or cubic-bezier(x1,y1,x2,y2)"
    )
