"""Command-line interface.

Three subcommands:

* ``morph`` interpolates one SVG into another.
* ``sequence`` chains a list of SVGs, morphing through each in turn.
* ``inspect`` reports what VectorMorph sees in a file, which is the fastest way
  to find out why a morph looks wrong.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Sequence

from . import __version__
from .document import load_svg, normalize_to_box, union_view_box
from .easing import EASINGS
from .morph import DEFAULT_SAMPLES
from .paths import polygon_area
from .render import ALL_FORMATS, build_morph, render, render_animated_svg


def _add_shared_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-o", "--output", required=True, help="output file path")
    parser.add_argument(
        "-f", "--format", choices=ALL_FORMATS, default=None,
        help="output format (default: inferred from the output extension)",
    )
    parser.add_argument(
        "-s", "--steps", type=int, default=24,
        help="frames per morph, including both endpoints (default: 24)",
    )
    parser.add_argument(
        "-e", "--easing", default="ease-in-out",
        help=f"easing curve: {', '.join(sorted(EASINGS))}, or cubic-bezier(...)",
    )
    parser.add_argument(
        "-d", "--duration", type=int, default=1200,
        help="total animation duration in milliseconds (default: 1200)",
    )
    parser.add_argument(
        "--size", type=int, default=512,
        help="raster output size in pixels (default: 512)",
    )
    parser.add_argument(
        "--samples", type=int, default=DEFAULT_SAMPLES,
        help=f"points sampled per ring (default: {DEFAULT_SAMPLES})",
    )
    parser.add_argument("--fill", default=None, help="fill color for the morphed shape")
    parser.add_argument("--background", default=None, help="background color")
    parser.add_argument(
        "--no-normalize", action="store_true",
        help="keep original scale and position instead of fitting both shapes to a common box",
    )
    parser.add_argument(
        "--padding", type=float, default=0.05,
        help="margin as a fraction of the canvas when normalizing (default: 0.05)",
    )
    parser.add_argument(
        "--ping-pong", action="store_true", help="morph back to the source at the end"
    )
    parser.add_argument("--no-loop", action="store_true", help="play once instead of looping")


def _render_options(args: argparse.Namespace) -> dict:
    return {
        "duration_ms": args.duration,
        "fill": args.fill,
        "background": args.background,
        "loop": not args.no_loop,
        "ping_pong": args.ping_pong,
        "size": args.size,
    }


def cmd_morph(args: argparse.Namespace) -> int:
    result = build_morph(
        args.source,
        args.target,
        steps=args.steps,
        easing=args.easing,
        samples=args.samples,
        normalize=not args.no_normalize,
        padding=args.padding,
    )

    fmt = (args.format or Path(args.output).suffix.lstrip(".") or "webp").lower()
    options = _render_options(args)
    if fmt == "svg":
        # Raster-only options are meaningless for the vector export.
        options.pop("size", None)

    output = render(result, args.output, fmt=fmt, **options)
    size_kb = output.stat().st_size / 1024.0
    print(
        f"{output}  {result.frame_count} frames  "
        f"{result.samples} pts/ring  {size_kb:.1f} KB"
    )
    return 0


def cmd_sequence(args: argparse.Namespace) -> int:
    """Morph through a chain of shapes, concatenating each leg's frames."""
    if len(args.inputs) < 2:
        print("sequence needs at least two SVG files", file=sys.stderr)
        return 2

    legs = []
    per_leg_steps = max(2, args.steps)
    for source, target in zip(args.inputs, args.inputs[1:]):
        legs.append(
            build_morph(
                source, target,
                steps=per_leg_steps,
                easing=args.easing,
                samples=args.samples,
                normalize=not args.no_normalize,
                padding=args.padding,
            )
        )

    # Each leg is solved independently, so its geometry sits in its own box.
    # Re-fit every leg to the union box so the chain does not jump between legs.
    combined = legs[0]
    frames = list(legs[0].frames)
    for leg in legs[1:]:
        # Drop the duplicated endpoint shared with the previous leg.
        frames.extend(leg.frames[1:])
    combined.frames = frames

    fmt = (args.format or Path(args.output).suffix.lstrip(".") or "webp").lower()
    options = _render_options(args)
    if fmt == "svg":
        options.pop("size", None)

    output = render(combined, args.output, fmt=fmt, **options)
    size_kb = output.stat().st_size / 1024.0
    print(
        f"{output}  {len(frames)} frames across {len(legs)} legs  {size_kb:.1f} KB"
    )
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    """Report the geometry VectorMorph extracted from a file."""
    for file in args.inputs:
        doc = load_svg(file)
        areas = sorted((abs(polygon_area(s)) for s in doc.subpaths), reverse=True)
        total_points = sum(len(s) for s in doc.subpaths)
        print(f"{file}")
        print(f"  viewBox      {doc.view_box}")
        print(f"  size         {doc.width} x {doc.height}")
        print(f"  fill         {doc.fill}")
        print(f"  subpaths     {len(doc.subpaths)}")
        print(f"  points       {total_points}")
        if areas:
            print(f"  largest area {areas[0]:.1f}")
            if len(areas) > 1:
                print(f"  smallest     {areas[-1]:.1f}")
        if not doc.subpaths:
            print("  WARNING: no drawable geometry found; this file cannot be morphed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vectormorph",
        description="Interpolate one SVG shape into another and export the animation.",
    )
    parser.add_argument("--version", action="version", version=f"vectormorph {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    morph = sub.add_parser("morph", help="morph one SVG into another")
    morph.add_argument("source", help="source SVG file")
    morph.add_argument("target", help="target SVG file")
    _add_shared_options(morph)
    morph.set_defaults(func=cmd_morph)

    sequence = sub.add_parser("sequence", help="morph through a chain of SVG files")
    sequence.add_argument("inputs", nargs="+", help="two or more SVG files, in order")
    _add_shared_options(sequence)
    sequence.set_defaults(func=cmd_sequence)

    inspect = sub.add_parser("inspect", help="report the geometry found in SVG files")
    inspect.add_argument("inputs", nargs="+", help="SVG files to inspect")
    inspect.set_defaults(func=cmd_inspect)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
