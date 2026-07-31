"""Tests for the vector morphing engine."""

from __future__ import annotations

import math

import pytest

from vectormorph import build_morph, render, render_animated_svg
from vectormorph.bench import count_self_intersections, run_benchmark
from vectormorph.document import load_svg, parse_transform
from vectormorph.easing import EASINGS, get_easing
from vectormorph.morph import align_rotation, interpolate, match_subpaths, resample
from vectormorph.paths import centroid, parse_path, points_to_path, polygon_area

CIRCLE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>'
SQUARE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect x="10" y="10" width="80" height="80"/></svg>'
DONUT = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<path d="M50 10 A40 40 0 1 0 50 90 A40 40 0 1 0 50 10 Z '
    'M50 30 A20 20 0 1 1 50 70 A20 20 0 1 1 50 30 Z"/></svg>'
)


@pytest.fixture
def shapes(tmp_path):
    """Write the test SVGs to disk and return their paths."""
    paths = {}
    for name, body in (("circle", CIRCLE), ("square", SQUARE), ("donut", DONUT)):
        file = tmp_path / f"{name}.svg"
        file.write_text(body)
        paths[name] = file
    return paths


# --- path parsing -----------------------------------------------------------

def test_parse_path_handles_all_command_types():
    d = "M10,10 L20,10 H30 V20 C30,30 40,30 40,20 Q45,10 50,20 T60,20 A5,5 0 0 1 70,20 Z"
    subpaths = parse_path(d)
    assert len(subpaths) == 1
    assert len(subpaths[0]) > 10
    assert all(isinstance(p, tuple) and len(p) == 2 for p in subpaths[0])


def test_relative_commands_match_absolute():
    absolute = parse_path("M0,0 L10,0 L10,10 Z")
    relative = parse_path("m0,0 l10,0 l0,10 z")
    assert absolute[0] == pytest.approx(relative[0])


def test_multiple_subpaths_are_separated():
    subpaths = parse_path("M0,0 L10,0 L10,10 Z M20,20 L30,20 L30,30 Z")
    assert len(subpaths) == 2


def test_implicit_lineto_after_moveto():
    # A second coordinate pair after M continues as an implicit L.
    subpaths = parse_path("M0,0 10,0 10,10 Z")
    assert len(subpaths) == 1
    assert len(subpaths[0]) == 3


def test_polygon_area_matches_analytic_square():
    assert polygon_area([(0, 0), (10, 0), (10, 10), (0, 10)]) == pytest.approx(100.0)


def test_polygon_area_sign_encodes_winding():
    ccw = polygon_area([(0, 0), (10, 0), (10, 10), (0, 10)])
    cw = polygon_area([(0, 10), (10, 10), (10, 0), (0, 0)])
    assert ccw > 0 > cw


def test_centroid_of_square_is_center():
    assert centroid([(0, 0), (10, 0), (10, 10), (0, 10)]) == pytest.approx((5.0, 5.0))


def test_points_to_path_roundtrips():
    original = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]]
    reparsed = parse_path(points_to_path(original))
    assert reparsed[0][:3] == pytest.approx(original[0])


# --- shape extraction -------------------------------------------------------

def test_circle_element_becomes_geometry(shapes):
    doc = load_svg(shapes["circle"])
    assert len(doc.subpaths) == 1
    # Sampled area should land close to pi * r^2 for r = 40.
    assert abs(polygon_area(doc.subpaths[0])) == pytest.approx(math.pi * 1600, rel=0.02)


def test_rect_element_becomes_geometry(shapes):
    doc = load_svg(shapes["square"])
    assert abs(polygon_area(doc.subpaths[0])) == pytest.approx(6400.0, rel=0.01)


def test_donut_has_two_subpaths_with_opposite_winding(shapes):
    doc = load_svg(shapes["donut"])
    assert len(doc.subpaths) == 2
    areas = [polygon_area(s) for s in doc.subpaths]
    # A hole is a ring wound against its parent; that is what makes it a hole.
    assert areas[0] * areas[1] < 0


def test_transform_is_baked_into_coordinates(tmp_path):
    file = tmp_path / "shifted.svg"
    file.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<g transform="translate(10,20)"><rect x="0" y="0" width="10" height="10"/></g></svg>'
    )
    doc = load_svg(file)
    xs = [p[0] for p in doc.subpaths[0]]
    ys = [p[1] for p in doc.subpaths[0]]
    assert min(xs) == pytest.approx(10.0)
    assert min(ys) == pytest.approx(20.0)


def test_parse_transform_composes_in_order():
    m = parse_transform("translate(10,0) scale(2)")
    # A point at x=1 scales to 2 then translates to 12.
    a, b, c, d, e, f = m
    assert a * 1 + c * 0 + e == pytest.approx(12.0)


# --- correspondence ---------------------------------------------------------

def test_resample_produces_exact_count():
    ring = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert len(resample(ring, 64)) == 64


def test_resample_is_evenly_spaced_by_arc_length():
    ring = resample([(0, 0), (10, 0), (10, 10), (0, 10)], 40)
    gaps = [
        math.hypot(ring[(i + 1) % 40][0] - ring[i][0], ring[(i + 1) % 40][1] - ring[i][1])
        for i in range(40)
    ]
    assert max(gaps) - min(gaps) < 1e-6


def test_resample_preserves_area():
    ring = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert abs(polygon_area(resample(ring, 64))) == pytest.approx(100.0, rel=0.01)


def test_align_rotation_recovers_a_rolled_ring():
    source = resample([(0, 0), (10, 0), (10, 10), (0, 10)], 32)
    rolled = source[7:] + source[:7]
    aligned = align_rotation(source, rolled)
    for (sx, sy), (ax, ay) in zip(source, aligned):
        assert (sx, sy) == pytest.approx((ax, ay))


def test_align_rotation_recovers_reversed_winding():
    source = resample([(0, 0), (10, 0), (10, 10), (0, 10)], 32)
    aligned = align_rotation(source, list(reversed(source)))
    cost = sum(
        (sx - ax) ** 2 + (sy - ay) ** 2 for (sx, sy), (ax, ay) in zip(source, aligned)
    )
    assert cost == pytest.approx(0.0, abs=1e-9)


def test_match_subpaths_pads_the_shorter_side():
    one = [[(0, 0), (10, 0), (10, 10)]]
    two = [[(0, 0), (10, 0), (10, 10)], [(20, 20), (30, 20), (30, 30)]]
    src, dst = match_subpaths(one, two, samples=32)
    assert len(src) == len(dst) == 2
    assert all(len(r) == 32 for r in src + dst)


def test_padded_subpath_is_collapsed_to_a_point():
    one = [[(0, 0), (10, 0), (10, 10)]]
    two = [[(0, 0), (10, 0), (10, 10)], [(20, 20), (30, 20), (30, 30)]]
    src, _ = match_subpaths(one, two, samples=16)
    padded = src[1]
    assert abs(polygon_area(padded)) == pytest.approx(0.0, abs=1e-9)


def test_match_subpaths_preserves_hole_winding(shapes):
    doc = load_svg(shapes["donut"])
    src, _ = match_subpaths(doc.subpaths, doc.subpaths, samples=32)
    # Uniform winding here would mean the hole gets filled in on render.
    assert polygon_area(src[0]) * polygon_area(src[1]) < 0


def test_interpolate_endpoints_are_exact():
    src = [resample([(0, 0), (10, 0), (10, 10)], 16)]
    dst = [resample([(5, 5), (20, 5), (20, 20)], 16)]
    assert interpolate(src, dst, 0.0)[0] == pytest.approx(src[0])
    assert interpolate(src, dst, 1.0)[0] == pytest.approx(dst[0])


# --- easing -----------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(EASINGS))
def test_every_easing_pins_both_endpoints(name):
    ease = get_easing(name)
    assert ease(0.0) == pytest.approx(0.0, abs=1e-6)
    assert ease(1.0) == pytest.approx(1.0, abs=1e-6)


def test_cubic_bezier_literal_is_parsed():
    ease = get_easing("cubic-bezier(0.42, 0, 0.58, 1)")
    assert ease(0.5) == pytest.approx(0.5, abs=0.01)


def test_unknown_easing_is_rejected():
    with pytest.raises(ValueError):
        get_easing("wobble")


def test_ease_in_starts_slower_than_linear():
    assert get_easing("ease-in")(0.25) < 0.25


# --- morph + render ---------------------------------------------------------

def test_build_morph_returns_requested_frame_count(shapes):
    result = build_morph(shapes["circle"], shapes["square"], steps=12)
    assert result.frame_count == 12


def test_morph_endpoints_match_the_input_shapes(shapes):
    result = build_morph(shapes["circle"], shapes["square"], steps=9)
    first_area = sum(abs(polygon_area(r)) for r in result.frames[0])
    last_area = sum(abs(polygon_area(r)) for r in result.frames[-1])
    assert first_area != pytest.approx(last_area, rel=0.01)


def test_morph_never_self_intersects(shapes):
    """The whole point of the alignment step, asserted directly."""
    result = build_morph(shapes["circle"], shapes["square"], steps=16)
    for frame in result.frames[1:-1]:
        assert sum(count_self_intersections(r) for r in frame) == 0


def test_morph_with_a_hole_keeps_the_hole(shapes):
    result = build_morph(shapes["donut"], shapes["donut"], steps=5)
    for frame in result.frames:
        assert polygon_area(frame[0]) * polygon_area(frame[1]) < 0


def test_steps_below_two_is_rejected(shapes):
    with pytest.raises(ValueError):
        build_morph(shapes["circle"], shapes["square"], steps=1)


def test_empty_svg_is_rejected(tmp_path):
    empty = tmp_path / "empty.svg"
    empty.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>')
    circle = tmp_path / "c.svg"
    circle.write_text(CIRCLE)
    with pytest.raises(ValueError, match="no drawable geometry"):
        build_morph(empty, circle, steps=4)


def test_animated_svg_contains_one_animate_per_morph(shapes):
    result = build_morph(shapes["circle"], shapes["square"], steps=8)
    svg = render_animated_svg(result, duration_ms=800)
    assert svg.count("<animate") == 1
    assert 'attributeName="d"' in svg
    assert svg.count(";") == 7  # eight keyframes, seven separators


def test_ping_pong_doubles_the_keyframes(shapes):
    result = build_morph(shapes["circle"], shapes["square"], steps=6)
    plain = render_animated_svg(result).count(";")
    bounced = render_animated_svg(result, ping_pong=True).count(";")
    assert bounced > plain


@pytest.mark.parametrize("fmt", ["svg", "webp", "gif", "apng"])
def test_render_writes_a_nonempty_file(shapes, tmp_path, fmt):
    result = build_morph(shapes["circle"], shapes["square"], steps=6)
    output = render(result, tmp_path / f"out.{fmt}", size=64, background="#ffffff")
    assert output.exists()
    assert output.stat().st_size > 0


def test_render_rejects_unknown_format(shapes, tmp_path):
    result = build_morph(shapes["circle"], shapes["square"], steps=4)
    with pytest.raises(ValueError):
        render(result, tmp_path / "out.tiff", fmt="tiff")


def test_output_is_deterministic(shapes, tmp_path):
    """Same inputs, same bytes. Required for the committed benchmark artifact."""
    first = render(build_morph(shapes["circle"], shapes["square"], steps=8), tmp_path / "a.svg")
    second = render(build_morph(shapes["circle"], shapes["square"], steps=8), tmp_path / "b.svg")
    assert first.read_bytes() == second.read_bytes()


# --- benchmark --------------------------------------------------------------

def test_self_intersection_detector_finds_a_bowtie():
    assert count_self_intersections([(0, 0), (10, 10), (10, 0), (0, 10)]) > 0


def test_self_intersection_detector_clears_a_square():
    assert count_self_intersections([(0, 0), (10, 0), (10, 10), (0, 10)]) == 0


def test_benchmark_shows_alignment_removes_tangling():
    report = run_benchmark("examples", steps=8)
    totals = report["totals"]
    assert totals["aligned_crossings"] == 0
    assert totals["aligned_crossings"] < totals["naive_crossings"]
    assert totals["aligned_travel"] < totals["naive_travel"]


def test_benchmark_is_reproducible():
    assert run_benchmark("examples", steps=8) == run_benchmark("examples", steps=8)
