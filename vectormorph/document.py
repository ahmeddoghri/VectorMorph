"""Reading geometry and presentation out of an SVG file.

Real-world SVGs do not consist purely of ``<path>`` elements. Icon sets are full
of ``<rect>``, ``<circle>``, and ``<polygon>``, and exporters bury everything
under nested ``<g>`` transforms. This module normalizes all of that into a flat
list of subpaths in user space, plus the handful of presentation attributes a
morph needs to carry across.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# SVGs arrive from file upload, so the parser sees untrusted XML. defusedxml
# refuses external entities and entity-expansion bombs, which the stdlib parser
# happily processes. Only parsing is swapped; ET is still used for its types.
from defusedxml.ElementTree import parse as safe_parse
from pathlib import Path
from typing import List, Sequence, Tuple

from .paths import Point, Subpath, parse_path

SVG_NS = "http://www.w3.org/2000/svg"

# 4x2 affine matrix as (a, b, c, d, e, f), matching the SVG transform spec.
Matrix = Tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

_TRANSFORM = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")
_NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


@dataclass
class ShapeDocument:
    """Flattened geometry plus the presentation needed to redraw it."""

    subpaths: List[Subpath] = field(default_factory=list)
    width: float = 100.0
    height: float = 100.0
    view_box: Tuple[float, float, float, float] = (0.0, 0.0, 100.0, 100.0)
    fill: str = "#000000"

    @property
    def is_empty(self) -> bool:
        return not self.subpaths


def _numbers(text: str) -> List[float]:
    return [float(n) for n in _NUMBER.findall(text or "")]


def multiply(m1: Matrix, m2: Matrix) -> Matrix:
    """Compose two affine transforms (``m1`` applied after ``m2``)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def parse_transform(text: str) -> Matrix:
    """Parse an SVG ``transform`` attribute into a single matrix."""
    result = IDENTITY
    for name, raw in _TRANSFORM.findall(text or ""):
        args = _numbers(raw)
        if name == "matrix" and len(args) == 6:
            m: Matrix = tuple(args)  # type: ignore[assignment]
        elif name == "translate":
            tx = args[0] if args else 0.0
            ty = args[1] if len(args) > 1 else 0.0
            m = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif name == "scale":
            sx = args[0] if args else 1.0
            sy = args[1] if len(args) > 1 else sx
            m = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif name == "rotate" and args:
            angle = math.radians(args[0])
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            rot: Matrix = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            if len(args) >= 3:
                # rotate(a, cx, cy) is translate(c) * rotate(a) * translate(-c).
                cx, cy = args[1], args[2]
                rot = multiply((1.0, 0.0, 0.0, 1.0, cx, cy), rot)
                rot = multiply(rot, (1.0, 0.0, 0.0, 1.0, -cx, -cy))
            m = rot
        elif name == "skewX" and args:
            m = (1.0, 0.0, math.tan(math.radians(args[0])), 1.0, 0.0, 0.0)
        elif name == "skewY" and args:
            m = (1.0, math.tan(math.radians(args[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            continue
        result = multiply(result, m)
    return result


def apply_matrix(m: Matrix, points: Sequence[Point]) -> Subpath:
    a, b, c, d, e, f = m
    return [(a * x + c * y + e, b * x + d * y + f) for x, y in points]


def _rounded_rect(x: float, y: float, w: float, h: float, rx: float, ry: float) -> str:
    """Build path data for a rect, honoring corner radii like the spec does."""
    rx = min(rx, w / 2.0)
    ry = min(ry, h / 2.0)
    if rx <= 0 or ry <= 0:
        return f"M{x},{y}H{x + w}V{y + h}H{x}Z"
    return (
        f"M{x + rx},{y}"
        f"H{x + w - rx}A{rx},{ry} 0 0 1 {x + w},{y + ry}"
        f"V{y + h - ry}A{rx},{ry} 0 0 1 {x + w - rx},{y + h}"
        f"H{x + rx}A{rx},{ry} 0 0 1 {x},{y + h - ry}"
        f"V{y + ry}A{rx},{ry} 0 0 1 {x + rx},{y}Z"
    )


def _shape_to_path(tag: str, attrib: dict) -> str | None:
    """Convert an SVG basic shape element into equivalent path data."""
    def num(key: str, default: float = 0.0) -> float:
        try:
            return float(attrib.get(key, default))
        except (TypeError, ValueError):
            return default

    if tag == "path":
        return attrib.get("d")

    if tag == "rect":
        w, h = num("width"), num("height")
        if w <= 0 or h <= 0:
            return None
        # A single specified radius applies to both axes.
        rx = num("rx", -1.0)
        ry = num("ry", -1.0)
        if rx < 0:
            rx = max(ry, 0.0)
        if ry < 0:
            ry = max(rx, 0.0)
        return _rounded_rect(num("x"), num("y"), w, h, rx, ry)

    if tag in ("circle", "ellipse"):
        cx, cy = num("cx"), num("cy")
        if tag == "circle":
            rx = ry = num("r")
        else:
            rx, ry = num("rx"), num("ry")
        if rx <= 0 or ry <= 0:
            return None
        # Two half-arcs, because a single arc of 360 degrees is degenerate.
        return (
            f"M{cx - rx},{cy}"
            f"A{rx},{ry} 0 1 0 {cx + rx},{cy}"
            f"A{rx},{ry} 0 1 0 {cx - rx},{cy}Z"
        )

    if tag == "line":
        return f"M{num('x1')},{num('y1')}L{num('x2')},{num('y2')}"

    if tag in ("polygon", "polyline"):
        coords = _numbers(attrib.get("points", ""))
        if len(coords) < 4:
            return None
        pairs = [f"{coords[i]},{coords[i + 1]}" for i in range(0, len(coords) - 1, 2)]
        data = "M" + "L".join(pairs)
        return data + "Z" if tag == "polygon" else data

    return None


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def load_svg(path: str | Path) -> ShapeDocument:
    """Load an SVG file and flatten every drawable shape into subpaths.

    Nested ``<g>`` transforms are composed and baked into the point
    coordinates, so the returned geometry is directly comparable across files
    that organize their groups differently.
    """
    tree = safe_parse(str(path))
    root = tree.getroot()

    view_box = (0.0, 0.0, 100.0, 100.0)
    if root.get("viewBox"):
        vb = _numbers(root.get("viewBox", ""))
        if len(vb) == 4 and vb[2] > 0 and vb[3] > 0:
            view_box = (vb[0], vb[1], vb[2], vb[3])

    def dimension(key: str, fallback: float) -> float:
        raw = _numbers(root.get(key, ""))
        return raw[0] if raw and raw[0] > 0 else fallback

    width = dimension("width", view_box[2])
    height = dimension("height", view_box[3])
    if not root.get("viewBox"):
        view_box = (0.0, 0.0, width, height)

    subpaths: List[Subpath] = []
    fill = root.get("fill") or "#000000"

    def walk(node: ET.Element, matrix: Matrix) -> None:
        nonlocal fill
        current = multiply(matrix, parse_transform(node.get("transform", "")))
        for child in node:
            tag = _local(child.tag)
            child_matrix = multiply(current, parse_transform(child.get("transform", "")))
            if tag in ("g", "svg", "a"):
                walk(child, current)
                continue
            if child.get("fill") and child.get("fill") != "none" and fill == "#000000":
                fill = child.get("fill", fill)
            data = _shape_to_path(tag, child.attrib)
            if not data:
                continue
            for sub in parse_path(data):
                subpaths.append(apply_matrix(child_matrix, sub))

    walk(root, IDENTITY)
    if fill in ("none", ""):
        fill = "#000000"

    return ShapeDocument(
        subpaths=subpaths, width=width, height=height, view_box=view_box, fill=fill
    )


def union_view_box(
    a: ShapeDocument, b: ShapeDocument
) -> Tuple[float, float, float, float]:
    """Smallest viewBox containing both documents' viewBoxes.

    A morph between a 24x24 icon and an 800x800 illustration has to be drawn in
    one coordinate system, or the intermediate frames get cropped.
    """
    ax, ay, aw, ah = a.view_box
    bx, by, bw, bh = b.view_box
    min_x, min_y = min(ax, bx), min(ay, by)
    max_x, max_y = max(ax + aw, bx + bw), max(ay + ah, by + bh)
    return (min_x, min_y, max_x - min_x, max_y - min_y)


def normalize_to_box(
    doc: ShapeDocument, box: Tuple[float, float, float, float], padding: float = 0.05
) -> List[Subpath]:
    """Scale and center a document's geometry to fit ``box``.

    Without this, morphing a small icon into a large one is dominated by the
    size difference instead of the shape difference. ``padding`` is the fraction
    of the box left as a margin.
    """
    points = [p for sub in doc.subpaths for p in sub]
    if not points:
        return []

    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_y = max(p[1] for p in points)
    src_w = max(max_x - min_x, 1e-9)
    src_h = max(max_y - min_y, 1e-9)

    bx, by, bw, bh = box
    avail_w = bw * (1.0 - 2.0 * padding)
    avail_h = bh * (1.0 - 2.0 * padding)
    scale = min(avail_w / src_w, avail_h / src_h)

    # Center the scaled bounding box inside the target box.
    offset_x = bx + (bw - src_w * scale) / 2.0
    offset_y = by + (bh - src_h * scale) / 2.0

    return [
        [((x - min_x) * scale + offset_x, (y - min_y) * scale + offset_y) for x, y in sub]
        for sub in doc.subpaths
    ]
