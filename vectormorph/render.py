"""Turning a morph into files.

Two very different outputs come out of the same interpolated geometry:

* **Animated SVG** (:func:`render_animated_svg`) keeps the result a vector. One
  ``<animate>`` element carries every keyframe's path data, so the file scales
  to any size and typically lands in tens of kilobytes.
* **Raster animations** (:func:`render_raster`) rasterize each frame through
  CairoSVG and hand them to Pillow for WebP, GIF, or APNG encoding.

Both take the same frame list, so what you preview is what you export.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

from .document import ShapeDocument, load_svg, normalize_to_box, union_view_box
from .easing import get_easing
from .morph import DEFAULT_SAMPLES, interpolate, match_subpaths
from .paths import Subpath, points_to_path

#: Formats that can be written. Animated SVG is vector; the rest are raster.
RASTER_FORMATS = ("webp", "gif", "apng", "png")
ALL_FORMATS = RASTER_FORMATS + ("svg",)


@dataclass
class MorphResult:
    """A completed morph, plus the numbers worth reporting on."""

    frames: List[List[Subpath]]
    view_box: Tuple[float, float, float, float]
    fill: str
    source_subpaths: int
    target_subpaths: int
    samples: int

    @property
    def frame_count(self) -> int:
        return len(self.frames)


def build_morph(
    source_path: str | Path,
    target_path: str | Path,
    steps: int = 24,
    easing: str = "ease-in-out",
    samples: int = DEFAULT_SAMPLES,
    normalize: bool = True,
    padding: float = 0.05,
) -> MorphResult:
    """Morph one SVG into another and return every interpolated frame.

    ``steps`` is the number of frames including both endpoints, so ``steps=2``
    yields just the source and the target. Frames are generated in a single
    pass with the correspondence solved once up front, which is what keeps a
    long morph from drifting.
    """
    if steps < 2:
        raise ValueError("steps must be at least 2 (source and target)")

    source_doc = load_svg(source_path)
    target_doc = load_svg(target_path)
    if source_doc.is_empty:
        raise ValueError(f"no drawable geometry found in {source_path}")
    if target_doc.is_empty:
        raise ValueError(f"no drawable geometry found in {target_path}")

    box = union_view_box(source_doc, target_doc)
    if normalize:
        src_geometry = normalize_to_box(source_doc, box, padding)
        dst_geometry = normalize_to_box(target_doc, box, padding)
    else:
        src_geometry, dst_geometry = source_doc.subpaths, target_doc.subpaths

    matched_src, matched_dst = match_subpaths(src_geometry, dst_geometry, samples)

    ease = get_easing(easing)
    frames = [
        interpolate(matched_src, matched_dst, ease(i / (steps - 1)))
        for i in range(steps)
    ]

    return MorphResult(
        frames=frames,
        view_box=box,
        fill=source_doc.fill,
        source_subpaths=len(source_doc.subpaths),
        target_subpaths=len(target_doc.subpaths),
        samples=samples,
    )


def frame_to_svg(
    subpaths: Sequence[Subpath],
    view_box: Tuple[float, float, float, float],
    fill: str = "#000000",
    background: str | None = None,
    size: int | None = None,
) -> str:
    """Render one frame as a standalone SVG document."""
    x, y, w, h = view_box
    dimensions = f'width="{size}" height="{size}" ' if size else ""
    background_rect = (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{background}"/>'
        if background else ""
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" {dimensions}'
        f'viewBox="{x} {y} {w} {h}">'
        f"{background_rect}"
        f'<path d="{points_to_path(subpaths)}" fill="{fill}" fill-rule="nonzero"/>'
        f"</svg>"
    )


def render_animated_svg(
    result: MorphResult,
    duration_ms: int = 1200,
    fill: str | None = None,
    background: str | None = None,
    loop: bool = True,
    ping_pong: bool = False,
) -> str:
    """Render the morph as a single self-animating SVG using SMIL.

    All keyframes live in one ``values`` list on one ``<animate>`` element. The
    result needs no JavaScript and no CSS, renders in any modern browser, and
    stays sharp at any size.

    ``ping_pong`` appends the reversed frame list so the shape morphs back
    instead of snapping to the start.
    """
    x, y, w, h = result.view_box
    frames = list(result.frames)
    if ping_pong and len(frames) > 2:
        frames = frames + frames[-2:0:-1]

    values = ";".join(points_to_path(frame) for frame in frames)
    seconds = max(duration_ms, 1) / 1000.0
    repeat = "indefinite" if loop else "1"
    background_rect = (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{background}"/>'
        if background else ""
    )
    paint = fill or result.fill

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {w} {h}">'
        f"{background_rect}"
        f'<path fill="{paint}" fill-rule="nonzero" d="{points_to_path(frames[0])}">'
        f'<animate attributeName="d" dur="{seconds}s" '
        f'repeatCount="{repeat}" calcMode="linear" values="{values}"/>'
        f"</path></svg>"
    )


def rasterize_frames(
    result: MorphResult,
    size: int = 512,
    fill: str | None = None,
    background: str | None = None,
):
    """Rasterize every morph frame to a Pillow image.

    Imported lazily so that the pure-geometry parts of the library, and the
    animated-SVG export, work on machines without libcairo installed.
    """
    try:
        import cairosvg  # noqa: PLC0415 - optional heavy dependency
        from PIL import Image  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "Raster output needs the optional dependencies: "
            "pip install 'vectormorph[raster]' (CairoSVG also needs libcairo "
            "installed system-wide). Exporting to .svg has no such requirement."
        ) from exc

    images = []
    paint = fill or result.fill
    for frame in result.frames:
        svg = frame_to_svg(frame, result.view_box, paint, background, size)
        png_bytes = cairosvg.svg2png(
            bytestring=svg.encode("utf-8"), output_width=size, output_height=size
        )
        images.append(Image.open(io.BytesIO(png_bytes)).convert("RGBA"))
    return images


def render_raster(
    result: MorphResult,
    output_path: str | Path,
    fmt: str = "webp",
    size: int = 512,
    duration_ms: int = 1200,
    fill: str | None = None,
    background: str | None = None,
    loop: bool = True,
    ping_pong: bool = False,
) -> Path:
    """Encode the morph as an animated WebP, GIF, or APNG."""
    fmt = fmt.lower()
    if fmt not in RASTER_FORMATS:
        raise ValueError(f"{fmt!r} is not a raster format; try one of {RASTER_FORMATS}")

    images = rasterize_frames(result, size=size, fill=fill, background=background)
    if ping_pong and len(images) > 2:
        images = images + images[-2:0:-1]

    per_frame = max(1, int(duration_ms / max(1, len(images))))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "png":
        images[0].save(output)
        return output

    save_format = {"webp": "WEBP", "gif": "GIF", "apng": "PNG"}[fmt]
    options = {
        "format": save_format,
        "save_all": True,
        "append_images": images[1:],
        "duration": per_frame,
        "loop": 0 if loop else 1,
    }
    if fmt == "gif":
        # GIF has no alpha channel, so flatten onto the background first.
        from PIL import Image  # noqa: PLC0415

        flat = []
        for img in images:
            canvas = Image.new("RGBA", img.size, background or "#FFFFFF")
            canvas.alpha_composite(img)
            flat.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE))
        options["append_images"] = flat[1:]
        flat[0].save(output, **options)
        return output

    if fmt == "webp":
        options["lossless"] = True

    images[0].save(output, **options)
    return output


def render(
    result: MorphResult,
    output_path: str | Path,
    fmt: str | None = None,
    **kwargs,
) -> Path:
    """Render to whichever format ``output_path``'s extension implies."""
    output = Path(output_path)
    fmt = (fmt or output.suffix.lstrip(".") or "webp").lower()

    if fmt == "svg":
        svg = render_animated_svg(
            result,
            duration_ms=kwargs.get("duration_ms", 1200),
            fill=kwargs.get("fill"),
            background=kwargs.get("background"),
            loop=kwargs.get("loop", True),
            ping_pong=kwargs.get("ping_pong", False),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(svg, encoding="utf-8")
        return output

    return render_raster(result, output, fmt=fmt, **kwargs)
