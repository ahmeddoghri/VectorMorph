# VectorMorph

Turn one SVG shape into another, and export the result as a real animated SVG.

Most "SVG morph" tools hand you a video of a morph. This one keeps the output a
vector: a single `<path>` with one `<animate>` element carrying every keyframe.
No JavaScript, no CSS, no runtime library. It scales to any size, and a
24-frame morph lands around 19 KB.

```bash
vectormorph morph circle.svg star.svg -o morph.svg
```

## The part that is actually hard

Interpolating between two shapes is easy to do and easy to do badly. Lerp point
`i` of one shape onto point `i` of the other and you get the classic tangled
morph: the shape folds through itself, turns inside out, and snaps back at the
end. That happens because the two point lists do not correspond. They have
different lengths, different winding directions, and different starting corners.

VectorMorph fixes all three before interpolating anything:

1. **Arc-length resampling.** Every ring is resampled to the same number of
   points, spaced evenly by distance rather than by original vertex index. A
   shape with 200 vertices bunched on one side morphs at a constant rate.
2. **Area-ordered subpath matching.** Subpaths are paired largest-to-largest, so
   the body maps to the body rather than to whichever hole was listed first.
   When one shape has fewer subpaths, the extras collapse to a point at their
   partner's centroid and grow in or shrink out cleanly.
3. **Rotational alignment.** Each target ring is rolled through every possible
   starting offset, in both winding directions, and the offset that minimizes
   total point travel wins.

Holes keep working because winding direction is left as authored. Under the
`nonzero` fill rule a hole is precisely a ring wound against its parent, so
normalizing every ring to the same direction would quietly fill in every hole.

### Measured, not asserted

`vectormorph.bench` scores the naive approach against the real pipeline on four
shape pairs, counting self-intersecting edge pairs in the intermediate frames.
Run `python -m vectormorph.bench` to reproduce this table exactly:

| pair | travel (naive) | travel (aligned) | crossings (naive) | crossings (aligned) |
| --- | ---: | ---: | ---: | ---: |
| circle_to_star | 53.55 | 14.77 | 50 | 0 |
| heart_to_squircle | 87.67 | 14.06 | 21 | 0 |
| star_to_squircle | 26.53 | 18.05 | 0 | 0 |
| circle_to_heart | 56.01 | 11.93 | 12 | 0 |

**83 self-intersections down to 0, mean point travel down 73.7%.**

One honest caveat: on `star_to_squircle`, area jerk is marginally worse aligned
than naive (0.0024 vs 0.0014). Those two shapes already correspond well, so
alignment has nothing to fix and the resampling shifts things slightly. The
committed `benchmark.json` is regenerated and diffed in CI, so these numbers
cannot silently drift.

## Install

The morph engine and the animated-SVG export are pure Python:

```bash
pip install defusedxml
```

For WebP, GIF, and APNG output, or the web studio:

```bash
pip install -r requirements.txt   # needs libcairo installed system-wide
```

On macOS: `brew install cairo`. On Debian/Ubuntu: `apt-get install libcairo2`.

## CLI

```bash
# Morph one shape into another
vectormorph morph circle.svg star.svg -o morph.svg

# Chain several shapes together
vectormorph sequence a.svg b.svg c.svg -o chain.svg --ping-pong

# Find out why a morph looks wrong
vectormorph inspect logo.svg
```

Useful flags:

| Flag | Does |
| --- | --- |
| `-s, --steps` | Frames per morph, endpoints included (default 24) |
| `-e, --easing` | `linear`, `ease-in`, `ease-out`, `ease-in-out`, `bounce`, `elastic`, `css-ease`, or `cubic-bezier(x1,y1,x2,y2)` |
| `-d, --duration` | Total animation length in ms |
| `--samples` | Points per ring (default 64); raise it for intricate shapes |
| `--size` | Raster output size in pixels |
| `--ping-pong` | Morph back to the source instead of snapping |
| `--no-normalize` | Keep original scale and position instead of fitting both shapes to a shared box |

`inspect` is the debugging tool. If a morph looks wrong, it is almost always
because one file has more subpaths than you expected, or none at all:

```
$ vectormorph inspect logo.svg
logo.svg
  viewBox      (0.0, 0.0, 100.0, 100.0)
  fill         #e0245e
  subpaths     2
  points       97
  largest area 3812.4
```

## Library

```python
from vectormorph import build_morph, render, render_animated_svg

result = build_morph("circle.svg", "star.svg", steps=48, easing="bounce")
print(result.frame_count, result.source_subpaths, result.target_subpaths)

render(result, "out.svg")                      # animated SVG
render(result, "out.webp", size=512)           # animated WebP
svg_markup = render_animated_svg(result, duration_ms=900, ping_pong=True)
```

Output is deterministic: the same inputs produce byte-identical files, which is
what lets the benchmark artifact be diffed in CI.

## Web studio

```bash
python app.py
```

Open `http://localhost:5001`. Upload two SVGs, tune the easing and frame count,
and the preview pane shows the actual animated SVG the exporter would write, not
a rasterized stand-in. Export to SVG, WebP, GIF, APNG, or a still PNG.

The original frame-sequence converter is still there at `/convert`, because
stitching SVG frames you already have is a genuinely different job from
interpolating between two shapes.

### What it understands

`<path>`, `<rect>` (including corner radii), `<circle>`, `<ellipse>`, `<line>`,
`<polygon>`, and `<polyline>`, nested at any depth under `<g>` elements, with
`matrix`, `translate`, `scale`, `rotate`, `skewX`, and `skewY` transforms
composed and baked into the output coordinates. All path commands are supported,
including arcs and the `S`/`T` shorthand curves.

Uploaded SVGs are parsed with `defusedxml`, so a file carrying an external
entity declaration is rejected rather than read off your filesystem.

## Limits

Worth knowing before you file a bug:

- **Geometry only.** Fills, strokes, gradients, and opacity are not interpolated;
  the morph takes the source's fill and keeps it. Stroked outlines morph as
  their fill region.
- **Curves are flattened to polylines** at 24 samples per segment. Output is
  dense line segments, not curves. It looks identical at normal sizes and keeps
  correspondence tractable, but it is not a curve-preserving morph.
- **Text is ignored.** Convert text to outlines first.
- **Rotational alignment is O(n²)** in the ring size. The 64-point default is
  instant; 256 points across many subpaths is noticeably slower.
- **`nonzero` fill rule** is assumed. A shape drawn to rely on `evenodd` with
  same-winding rings will fill differently.

## Tests

```bash
pytest -q          # 65 tests
```

CI runs the suite on Python 3.10 through 3.13, separately verifies the engine
works with no raster dependencies installed, and diffs the regenerated benchmark
against the committed one.

## License

MIT. See LICENSE.
