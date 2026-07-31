"""VectorMorph: interpolate one SVG shape into another, and export the result.

The library entry point is :func:`build_morph`, which solves the correspondence
between two shapes and returns every interpolated frame, and :func:`render`,
which writes those frames as an animated SVG, WebP, GIF, or APNG.

    >>> from vectormorph import build_morph, render
    >>> result = build_morph("circle.svg", "star.svg", steps=48)
    >>> render(result, "morph.svg")
"""

from .document import ShapeDocument, load_svg
from .easing import EASINGS, get_easing
from .morph import interpolate, match_subpaths, resample
from .paths import parse_path, points_to_path
from .render import (
    ALL_FORMATS,
    MorphResult,
    build_morph,
    render,
    render_animated_svg,
    render_raster,
)

__version__ = "0.2.0"

__all__ = [
    "ALL_FORMATS",
    "EASINGS",
    "MorphResult",
    "ShapeDocument",
    "build_morph",
    "get_easing",
    "interpolate",
    "load_svg",
    "match_subpaths",
    "parse_path",
    "points_to_path",
    "render",
    "render_animated_svg",
    "render_raster",
    "resample",
]
