"""Tidy tools: path parsing, ops, and the /api/tidy endpoints."""

import os
import tempfile

os.environ["CAMMCUT_DATA_DIR"] = tempfile.mkdtemp(prefix="cammcut-test-")

import math

import pytest
from fastapi.testclient import TestClient

from cammcut.web.app import create_app
from cammcut.web.schemas import Item
from cammcut.web.services import paths, svg_tools


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------- path parsing

def test_parse_square_with_close():
    subs = paths.parse_d("M0 0 L10 0 L10 10 Z")
    assert len(subs) == 1
    segs, closed = subs[0]
    assert closed is True
    assert segs[-1] == ("L", (10, 10), (0, 0))  # Z adds the closing line


def test_parse_relative_and_implicit_repeat():
    subs = paths.parse_d("M10 10 20 10 20 20z")
    segs, closed = subs[0]
    assert closed is True
    assert segs[0] == ("L", (10, 10), (20, 10))
    assert segs[1] == ("L", (20, 10), (20, 20))


def test_parse_cubic_quadratic_smooth():
    subs = paths.parse_d("M0 0 C5 0 5 10 10 10 S15 20 20 20 Q25 25 30 20 T40 20")
    segs, _closed = subs[0]
    assert segs[0][0] == "C"
    # S reflects the previous cubic control point: p1 = 2*end - prev_ctrl
    assert segs[1][0] == "C" and segs[1][2] == (15, 10)
    assert segs[2][0] == "Q"
    # T reflects the previous quadratic control point
    assert segs[3][0] == "Q" and segs[3][2] == (35, 15)


def test_parse_h_v_arcs():
    subs = paths.parse_d("M0 0 H10 V10 A5 5 0 0 1 0 10 H0 Z")
    segs, closed = subs[0]
    assert segs[0][0] == "L" and segs[0][2] == (10, 0)
    assert segs[2][0] == "A"
    assert closed is True


def test_parse_two_subpaths():
    subs = paths.parse_d("M0 0 L1 0 M5 5 L6 5")
    assert len(subs) == 2


def test_parse_error_cases():
    with pytest.raises(paths.PathError):
        paths.parse_d("L0 0")  # must start with a move
    with pytest.raises(paths.PathError):
        paths.parse_d("M0 0 X5")


# ---------------------------------------------------------------- flattening

def test_flatten_half_circle_arc_endpoint_exact():
    subs = paths.parse_d("M0 0 A10 10 0 0 1 20 0")
    (pts, closed), = paths.flatten(subs, tol=0.05)
    assert closed is False
    assert math.isclose(pts[-1][0], 20.0, abs_tol=1e-6)
    # a sweep-1 arc from (0,0) to (20,0) bulges upward: min y ≈ -10 (SVG y-down)
    assert min(p[1] for p in pts) < -9.9


def test_flatten_cubic_endpoints_exact():
    subs = paths.parse_d("M0 0 C10 -10 20 -10 30 0")
    (pts, _), = paths.flatten(subs, tol=0.1)
    assert pts[0] == (0.0, 0.0) or pts[0] == (0, 0)  # start kept
    assert math.isclose(pts[-1][0], 30.0, abs_tol=1e-9)
    assert math.isclose(pts[-1][1], 0.0, abs_tol=1e-9)


def test_rdp_removes_collinear_only():
    pts = [(i * 10.0, 0.0) for i in range(11)] + [(100.0, 5.0)]
    kept = paths.rdp(pts, 0.1)
    assert len(kept) == 3  # start, the corner at (100, 0)... -> (0,0),(100,0),(100,5)
    assert kept[0] == (0.0, 0.0) and kept[-1] == (100.0, 5.0)


def test_self_crossings_finds_x():
    poly = [([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)], True)]
    xs = paths.self_crossings(poly)
    assert len(xs) == 1
    assert math.isclose(xs[0][0], 5.0, abs_tol=0.01)
    assert math.isclose(xs[0][1], 5.0, abs_tol=0.01)


def test_self_crossings_square_is_clean():
    poly = [([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)], True)]
    assert paths.self_crossings(poly) == []


def test_self_crossings_two_separate_squares_clean():
    poly = [([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)], True),
            ([(20, 20), (30, 20), (30, 30), (20, 30), (20, 20)], True)]
    assert paths.self_crossings(poly) == []


# --------------------------------------------------------------- svg_tools

def mk(d: str, scale: float = 1.0) -> Item:
    return Item(id="t1", d=d, transform=[scale, 0, 0, scale, 0, 0])


def test_check_counts_open_and_dupes():
    items = [mk("M0 0 L10 0 L10 10"), mk("M0 0 L0 0 L5 5 Z")]
    r = svg_tools.check_items(items)
    assert r["open_subpaths"] == 1
    assert r["duplicate_points"] >= 1
    assert r["self_crossings"] == 0


def test_check_finds_crossing():
    r = svg_tools.check_items([mk("M0 0 L10 10 M0 10 L10 0")])
    assert r["self_crossings"] == 1


def test_close_paths_adds_z():
    out, changed = svg_tools.close_paths([mk("M0 0 L10 0 L10 10")])
    assert changed == 1
    assert out[0].d.endswith("Z")


def test_close_paths_untouched_when_closed():
    out, changed = svg_tools.close_paths([mk("M0 0 L10 0 Z")])
    assert changed == 0
    assert out[0].d == "M0 0 L10 0 Z"


def test_dedupe_removes_degenerate_segment():
    out, removed = svg_tools.dedupe_points([mk("M0 0 L5 0 L5 0 L10 0")])
    assert removed >= 1
    assert "L5 0 L5 0" not in out[0].d


def test_flatten_bakes_cubic():
    out, n = svg_tools.flatten_curves([mk("M0 0 C10 0 10 10 20 10")])
    assert n == 1
    assert "C" not in out[0].d
    subs = paths.parse_d(out[0].d)
    (pts, _), = paths.flatten(subs, 0.05)
    assert math.isclose(pts[-1][0], 20.0, abs_tol=0.01)


def test_simplify_stays_closed_and_reduces_points():
    # circle approximated with 720 line points, radius 10
    pts = [(10 + 10 * math.cos(2 * math.pi * k / 720),
            10 + 10 * math.sin(2 * math.pi * k / 720)) for k in range(721)]
    d = "M" + " L".join(f"{x:.4f} {y:.4f}" for x, y in pts) + "Z"
    out, removed = svg_tools.simplify([mk(d)], tol_mm=0.05)
    assert removed > 300
    assert out[0].d.endswith("Z")
    # resulting geometry stays within tolerance of the original circle
    subs = paths.parse_d(out[0].d)
    (flat, _), = paths.flatten(subs, 0.01)
    for x, y in flat:
        assert math.isclose(math.hypot(x - 10, y - 10), 10.0, abs_tol=0.06)


def test_simplify_respects_px_scale_item():
    # 100 px-long line on a px-space item (scale 25.4/96 like imports)
    scale = 25.4 / 96.0
    d = "M0 0 " + " ".join(f"L{k}.5 0" for k in range(100)) + " L100 0"
    out, _removed = svg_tools.simplify([mk(d, scale=scale)], tol_mm=0.05)
    subs = paths.parse_d(out[0].d)
    (flat, _), = paths.flatten(subs, 0.001)
    assert len(flat) <= 3  # collinear px steps collapse
    assert math.isclose(flat[-1][0] * scale, 100 * scale, abs_tol=0.06)


# --------------------------------------------------------------------- API

def test_tidy_api_roundtrip(client):
    r = client.post("/api/tidy/check", json={"items": [
        {"id": "a", "d": "M0 0 L10 10 M0 10 L10 0"}]})
    assert r.status_code == 200
    assert r.json()["self_crossings"] == 1

    r = client.post("/api/tidy", json={
        "items": [{"id": "a", "d": "M0 0 L10 0 L10 10"}],
        "ops": [{"op": "close_paths"}, {"op": "simplify", "params": {"tol_mm": 0.1}}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["report"][0] == {"op": "close_paths", "changed": 1}
    assert body["items"][0]["d"].endswith("Z")


def test_tidy_api_unknown_op_400(client):
    r = client.post("/api/tidy", json={
        "items": [{"id": "a", "d": "M0 0 L1 1"}],
        "ops": [{"op": "explode"}],
    })
    assert r.status_code == 400


def test_tidy_api_bad_path_400(client):
    r = client.post("/api/tidy/check", json={"items": [{"id": "a", "d": "L0 0"}]})
    assert r.status_code == 400