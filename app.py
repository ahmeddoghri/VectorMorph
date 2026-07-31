"""VectorMorph web application.

Two things live here:

* ``/`` and ``/morph`` are the shape morphing studio, built on the
  :mod:`vectormorph` engine. The live preview returns an animated SVG, so the
  browser gets a real vector animation rather than a rasterized approximation.
* ``/convert`` is the original frame-sequence converter, kept because it does a
  different job: stitching SVG frames you already have into one animation.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_socketio import SocketIO
from PIL import Image
from werkzeug.utils import secure_filename

from config import CONVERTED_DIR, Config, logger
from utils.file_utils import get_base64_data, get_unique_filename
from utils.image_processing import (
    blend_frames,
    convert_svg_to_png,
    fade_frames,
    save_animation,
)
from vectormorph import __version__, build_morph
from vectormorph.easing import EASINGS
from vectormorph.render import ALL_FORMATS, render, render_animated_svg

app = Flask(__name__)
app.config.from_object(Config)

# threading, not eventlet: eventlet is deprecated, and this workload is
# CPU-bound rasterization, which greenlets would not have helped anyway.
socketio = SocketIO(app, async_mode="threading")


@app.route("/")
def index():
    return render_template(
        "index.html", easings=sorted(EASINGS), formats=ALL_FORMATS, version=__version__
    )


@app.route("/health")
def health():
    """Liveness probe that also reports the engine version."""
    return jsonify({"status": "ok", "version": __version__})


def _save_upload(file_storage, directory: str) -> str:
    """Persist an upload under a sanitized name inside ``directory``."""
    name = secure_filename(file_storage.filename or "shape.svg")
    if not name.lower().endswith(".svg"):
        raise ValueError(f"{name!r} is not an SVG file")
    path = os.path.join(directory, name)
    # secure_filename collapses distinct names onto the same string often
    # enough that a two-file morph can collide with itself.
    counter = 1
    while os.path.exists(path):
        stem, ext = os.path.splitext(name)
        path = os.path.join(directory, f"{stem}_{counter}{ext}")
        counter += 1
    file_storage.save(path)
    return path


def _morph_options(form) -> dict:
    """Read and clamp morph settings out of a submitted form."""

    def integer(key: str, default: int, low: int, high: int) -> int:
        try:
            return max(low, min(high, int(form.get(key, default))))
        except (TypeError, ValueError):
            return default

    easing = form.get("easing", "ease-in-out")
    if easing not in EASINGS and not easing.startswith("cubic-bezier"):
        easing = "ease-in-out"

    background = form.get("background") or None
    if background in ("rgba(0,0,0,0)", "transparent", "none"):
        background = None

    return {
        "steps": integer("steps", 24, 2, 120),
        "samples": integer("samples", 64, 8, 256),
        "duration": integer("duration", 1200, 50, 20000),
        "size": integer("size", 512, 32, 2048),
        "easing": easing,
        "fill": form.get("fill") or None,
        "background": background,
        "ping_pong": form.get("ping_pong") in ("1", "true", "on", "yes"),
        "loop": form.get("loop", "1") in ("1", "true", "on", "yes"),
    }


def _read_pair(request_files):
    source = request_files.get("source")
    target = request_files.get("target")
    if not source or not target:
        raise ValueError("Upload both a source and a target SVG.")
    return source, target


@app.route("/preview", methods=["POST"])
def preview():
    """Morph two uploaded SVGs and return an animated SVG for live preview."""
    try:
        source, target = _read_pair(request.files)
        options = _morph_options(request.form)

        with tempfile.TemporaryDirectory() as work:
            result = build_morph(
                _save_upload(source, work),
                _save_upload(target, work),
                steps=options["steps"],
                easing=options["easing"],
                samples=options["samples"],
            )
            svg = render_animated_svg(
                result,
                duration_ms=options["duration"],
                fill=options["fill"],
                background=options["background"],
                loop=options["loop"],
                ping_pong=options["ping_pong"],
            )

        return jsonify(
            {
                "svg": svg,
                "frames": result.frame_count,
                "source_subpaths": result.source_subpaths,
                "target_subpaths": result.target_subpaths,
                "samples": result.samples,
                "bytes": len(svg.encode("utf-8")),
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - report something usable, log the trace
        logger.exception("Preview failed")
        return jsonify({"error": f"Preview failed: {exc}"}), 500


@app.route("/morph", methods=["POST"])
def morph():
    """Morph two uploaded SVGs and write a downloadable file."""
    try:
        source, target = _read_pair(request.files)

        fmt = request.form.get("format", "svg").lower()
        if fmt not in ALL_FORMATS:
            return jsonify({"error": f"Unsupported format {fmt!r}."}), 400

        options = _morph_options(request.form)
        with tempfile.TemporaryDirectory() as work:
            result = build_morph(
                _save_upload(source, work),
                _save_upload(target, work),
                steps=options["steps"],
                easing=options["easing"],
                samples=options["samples"],
            )

            output_path = get_unique_filename(CONVERTED_DIR, "morph", f".{fmt}")
            render_kwargs = {
                "duration_ms": options["duration"],
                "fill": options["fill"],
                "background": options["background"],
                "loop": options["loop"],
                "ping_pong": options["ping_pong"],
            }
            if fmt != "svg":
                render_kwargs["size"] = options["size"]
            render(result, output_path, fmt=fmt, **render_kwargs)

        filename = os.path.basename(output_path)
        return jsonify(
            {
                "filename": filename,
                "download_url": f"/download/{filename}",
                "frames": result.frame_count,
                "bytes": Path(output_path).stat().st_size,
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("Morph failed")
        return jsonify({"error": f"Morph failed: {exc}"}), 500


@app.route("/convert", methods=["POST"])
def convert():
    """Stitch a sequence of uploaded SVG frames into one animation."""
    try:
        files = request.files.getlist("files")
        if not files:
            return "No files uploaded.", 400

        duration = int(request.form.get("duration", 100))
        smart_animation = request.form.get("smart_animation", "none")
        background_color = request.form.get("background_color", "rgba(255,255,255,1)")
        blend_amount = float(request.form.get("blend_amount", 0.5))
        fade_steps = int(request.form.get("fade_steps", 4))
        output_format = request.form.get("output_format", "webp")

        if background_color == "rgba(0,0,0,0)":
            background_color = None

        with tempfile.TemporaryDirectory() as temp_dir:
            frames = process_svg_files(files, temp_dir, background_color)
            if not frames:
                return "Error processing SVG files.", 400

            frames = apply_animations(frames, smart_animation, blend_amount, fade_steps)
            output_path = save_output_file(frames, output_format, duration)
            if not output_path:
                return "Error saving output file.", 500

            return render_template(
                "result.html",
                filename=os.path.basename(output_path),
                media_type="image",
                base64_data=get_base64_data(output_path),
            )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Conversion error: {exc}")
        return "An error occurred during conversion.", 500


@app.route("/download/<filename>")
def download(filename):
    try:
        safe = secure_filename(filename)
        return send_from_directory(
            CONVERTED_DIR, safe, as_attachment=True, download_name=safe
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Download error: {exc}")
        return "File not found.", 404


def process_svg_files(files, temp_dir, background_color):
    """Rasterize uploaded SVG frames, preserving upload order."""
    frames = []
    for index, file in enumerate(files):
        if file.filename and file.filename.lower().endswith(".svg"):
            svg_path = os.path.join(temp_dir, secure_filename(file.filename))
            png_path = svg_path.replace(".svg", ".png")

            file.save(svg_path)
            if convert_svg_to_png(svg_path, png_path, background_color):
                frames.append(Image.open(png_path))

            socketio.emit("progress", {"progress": int((index + 1) / len(files) * 20)})
    return frames


def apply_animations(frames, smart_animation, blend_amount, fade_steps):
    """Apply the selected inter-frame effect."""
    if smart_animation == "blend":
        return blend_frames(frames, blend_amount)
    if smart_animation == "fade":
        return fade_frames(frames, fade_steps)
    return frames


def save_output_file(frames, output_format, duration):
    """Encode stitched frames to the requested animation format."""
    output_path = get_unique_filename(CONVERTED_DIR, "animate", f".{output_format}")
    if output_format in ("webp", "gif") and save_animation(
        frames, output_path, duration, output_format.upper()
    ):
        return output_path
    return None


if __name__ == "__main__":
    socketio.run(
        app, debug=False, host="127.0.0.1", port=5001, allow_unsafe_werkzeug=True
    )
