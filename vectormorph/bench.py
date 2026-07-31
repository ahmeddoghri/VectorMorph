"""A deterministic benchmark for morph quality.

"The morph looks better" is not a claim anyone can check. This module makes it
one, by scoring two strategies on the same shape pairs:

* **naive** pads the shorter point list, then interpolates by vertex index.
  This is what you get from a straightforward implementation, and it is the
  reason so many morphs turn inside out halfway through.
* **aligned** is the real pipeline: arc-length resampling, area-ordered subpath
  matching, and rotational alignment before interpolating.

Three metrics, all lower-is-better:

``travel``
    Mean distance each point moves, in viewBox units. Correspondence errors
    show up here first, because a mismatched pair drags points across the
    canvas instead of to the nearest sensible destination.

``crossings``
    Self-intersecting edge pairs, summed over intermediate frames. This is the
    direct measure of tangling. Endpoints are excluded, since a self-crossing
    source shape is the author's business, not the morph's.

``area_jerk``
    Standard deviation of the frame-to-frame change in area, normalized by mean
    area. A morph that stalls and then lurches scores badly even if it never
    tangles.

Everything is computed from fixed inputs with no randomness, so results
reproduce byte for byte on any machine.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from .document import load_svg, normalize_to_box, union_view_box
from .morph import DEFAULT_SAMPLES, interpolate, match_subpaths, resample
from .paths import Point, Subpath, polygon_area

#: Shape pairs exercised by the benchmark, as (name, source, target) stems.
#: Chosen to cover the cases that break naive implementations: a large vertex
#: count mismatch, a subpath count mismatch, and a shape with a hole.
BENCH_PAIRS: Tuple[Tuple[str, str, str], ...] = (
    ("circle_to_star", "circle", "star"),
    ("heart_to_squircle", "heart", "squircle"),
    ("star_to_squircle", "star", "squircle"),
    ("circle_to_heart", "circle", "heart"),
)

BENCH_STEPS = 16


@dataclass
class StrategyScore:
    travel: float
    crossings: int
    area_jerk: float


@dataclass
class PairResult:
    pair: str
    naive: StrategyScore
    aligned: StrategyScore


def _segments_cross(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    """True if segment a1-a2 properly crosses b1-b2.

    Uses strict orientation signs, so shared endpoints and collinear overlap do
    not count. Adjacent edges of a ring always touch, and counting that as a
    crossing would drown out the real signal.
    """
    def orient(p: Point, q: Point, r: Point) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1, d2 = orient(b1, b2, a1), orient(b1, b2, a2)
    d3, d4 = orient(a1, a2, b1), orient(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def count_self_intersections(ring: Sequence[Point]) -> int:
    """Count properly crossing edge pairs within one closed ring."""
    n = len(ring)
    if n < 4:
        return 0
    crossings = 0
    for i in range(n):
        a1, a2 = ring[i], ring[(i + 1) % n]
        # Start at i+2 to skip the shared-vertex neighbor, and stop before
        # wrapping onto edge i again.
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _segments_cross(a1, a2, ring[j], ring[(j + 1) % n]):
                crossings += 1
    return crossings


def _naive_match(
    source: Sequence[Subpath], target: Sequence[Subpath], samples: int
) -> Tuple[List[Subpath], List[Subpath]]:
    """The obvious implementation: equalize counts, interpolate by index.

    No arc-length resampling and no rotational alignment. Point i of the source
    goes to point i of the target, whatever those happen to be.
    """
    src = [list(s) for s in source if len(s) >= 2]
    dst = [list(s) for s in target if len(s) >= 2]
    src = src or [[(0.0, 0.0)]]
    dst = dst or [[(0.0, 0.0)]]

    while len(src) < len(dst):
        src.append([src[0][0]] * samples)
    while len(dst) < len(src):
        dst.append([dst[0][0]] * samples)

    out_src: List[Subpath] = []
    out_dst: List[Subpath] = []
    for s_ring, d_ring in zip(src, dst):
        # Stretch both to the sample count by repeating vertices, the cheap
        # equivalent of "just make the lists the same length".
        def stretch(ring: List[Point]) -> Subpath:
            return [ring[int(i * len(ring) / samples) % len(ring)] for i in range(samples)]

        out_src.append(stretch(s_ring))
        out_dst.append(stretch(d_ring))
    return out_src, out_dst


def _score(src: Sequence[Subpath], dst: Sequence[Subpath], steps: int) -> StrategyScore:
    point_count = sum(len(r) for r in src) or 1
    travel = sum(
        math.hypot(tx - sx, ty - sy)
        for s_ring, d_ring in zip(src, dst)
        for (sx, sy), (tx, ty) in zip(s_ring, d_ring)
    ) / point_count

    crossings = 0
    areas: List[float] = []
    for i in range(steps):
        t = i / (steps - 1)
        frame = interpolate(src, dst, t)
        areas.append(sum(abs(polygon_area(r)) for r in frame))
        if 0 < i < steps - 1:  # Endpoints are the author's shapes, not ours.
            crossings += sum(count_self_intersections(r) for r in frame)

    deltas = [areas[i + 1] - areas[i] for i in range(len(areas) - 1)]
    mean_area = sum(areas) / len(areas) if areas else 1.0
    if len(deltas) > 1 and mean_area > 0:
        mean_delta = sum(deltas) / len(deltas)
        variance = sum((d - mean_delta) ** 2 for d in deltas) / len(deltas)
        area_jerk = math.sqrt(variance) / mean_area
    else:
        area_jerk = 0.0

    return StrategyScore(
        travel=round(travel, 4), crossings=crossings, area_jerk=round(area_jerk, 5)
    )


def run_benchmark(
    examples_dir: str | Path = "examples",
    steps: int = BENCH_STEPS,
    samples: int = DEFAULT_SAMPLES,
) -> Dict:
    """Score both strategies on every benchmark pair."""
    examples = Path(examples_dir)
    results: List[PairResult] = []

    for name, source_stem, target_stem in BENCH_PAIRS:
        source_doc = load_svg(examples / f"{source_stem}.svg")
        target_doc = load_svg(examples / f"{target_stem}.svg")
        box = union_view_box(source_doc, target_doc)
        src_geometry = normalize_to_box(source_doc, box)
        dst_geometry = normalize_to_box(target_doc, box)

        naive_src, naive_dst = _naive_match(src_geometry, dst_geometry, samples)
        aligned_src, aligned_dst = match_subpaths(src_geometry, dst_geometry, samples)

        results.append(
            PairResult(
                pair=name,
                naive=_score(naive_src, naive_dst, steps),
                aligned=_score(aligned_src, aligned_dst, steps),
            )
        )

    def total(attr: str, strategy: str) -> float:
        return sum(getattr(getattr(r, strategy), attr) for r in results)

    naive_crossings = int(total("crossings", "naive"))
    aligned_crossings = int(total("crossings", "aligned"))
    naive_travel = total("travel", "naive")
    aligned_travel = total("travel", "aligned")

    return {
        "config": {"steps": steps, "samples": samples, "pairs": len(results)},
        "pairs": [asdict(r) for r in results],
        "totals": {
            "naive_crossings": naive_crossings,
            "aligned_crossings": aligned_crossings,
            "naive_travel": round(naive_travel, 4),
            "aligned_travel": round(aligned_travel, 4),
            "travel_reduction_pct": (
                round(100.0 * (naive_travel - aligned_travel) / naive_travel, 1)
                if naive_travel > 0 else 0.0
            ),
        },
    }


def format_report(report: Dict) -> str:
    """Render the benchmark as a Markdown table."""
    lines = [
        "| pair | travel (naive) | travel (aligned) | crossings (naive) | crossings (aligned) | area jerk (naive) | area jerk (aligned) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for pair in report["pairs"]:
        n, a = pair["naive"], pair["aligned"]
        lines.append(
            f"| {pair['pair']} | {n['travel']:.2f} | {a['travel']:.2f} | "
            f"{n['crossings']} | {a['crossings']} | "
            f"{n['area_jerk']:.4f} | {a['area_jerk']:.4f} |"
        )
    totals = report["totals"]
    lines.append("")
    lines.append(
        f"Total self-intersections: naive {totals['naive_crossings']}, "
        f"aligned {totals['aligned_crossings']}. "
        f"Mean point travel down {totals['travel_reduction_pct']}%."
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the VectorMorph quality benchmark.")
    parser.add_argument("--examples", default="examples", help="directory of example SVGs")
    parser.add_argument("--json", default="benchmark.json", help="where to write raw results")
    parser.add_argument("--steps", type=int, default=BENCH_STEPS)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    args = parser.parse_args(argv)

    report = run_benchmark(args.examples, steps=args.steps, samples=args.samples)
    Path(args.json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(format_report(report))
    print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
