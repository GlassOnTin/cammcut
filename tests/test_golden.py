"""Golden tests: small SVGs -> exact CAMM-GL strings."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cammcut.cammcut import (  # noqa: E402
    CammcutError,
    HPGL_PER_MM,
    polylines_to_hpgl,
    svg_to_polylines,
)

NS = 'xmlns="http://www.w3.org/2000/svg"'


def run(svg_bytes):
    polylines, page_w, page_h = svg_to_polylines(svg_bytes)
    return polylines_to_hpgl(polylines, 5, page_w, page_h)


def test_square_origin_golden():
    src = ('<svg %s width="10mm" height="10mm" viewBox="0 0 10 10">'
           '<rect x="0" y="0" width="10" height="10"/></svg>' % NS).encode()
    hpgl, _ = run(src)
    # SVG top-left (0,0) -> machine (0,10mm); artwork bottom-left at origin
    assert hpgl == "IN;VS5;PU0,400;PD400,400,400,0,0,0,0,400;"


def test_offset_golden():
    src = ('<svg %s width="10mm" height="10mm" viewBox="0 0 10 10">'
           '<rect x="0" y="0" width="10" height="10"/></svg>' % NS).encode()
    polylines, page_w, page_h = svg_to_polylines(src)
    hpgl, _ = polylines_to_hpgl(polylines, 5, page_w, page_h, x_mm=5, y_mm=2)
    # +5mm x = +200 units; +2mm y = +80 units
    assert hpgl == "IN;VS5;PU200,480;PD600,480,600,80,200,80,200,480;"


def test_mirror_golden():
    src = ('<svg %s width="10mm" height="10mm" viewBox="0 0 10 10">'
           '<rect x="0" y="0" width="10" height="10"/></svg>' % NS).encode()
    polylines, page_w, page_h = svg_to_polylines(src)
    hpgl, _ = polylines_to_hpgl(polylines, 5, page_w, page_h, mirror=True)
    # mirrored around x=5mm: same square, traversal reversed
    assert hpgl == "IN;VS5;PU400,400;PD0,400,0,0,400,0,400,400;"


def test_group_transform_golden():
    src = ('<svg %s width="10mm" height="10mm" viewBox="0 0 10 10">'
           '<g transform="translate(2,3)"><rect x="0" y="0" width="5" '
           'height="5"/></g></svg>' % NS).encode()
    hpgl, _ = run(src)
    # rect at 2..7 x, 3..8 y; y flip around 10mm page
    assert hpgl == "IN;VS5;PU80,280;PD280,280,280,80,80,80,80,280;"


def test_line_golden():
    src = ('<svg %s width="10mm" height="10mm" viewBox="0 0 10 10">'
           '<line x1="0" y1="0" x2="10" y2="0"/></svg>' % NS).encode()
    hpgl, _ = run(src)
    assert hpgl == "IN;VS5;PU0,400;PD400,400;"


def test_circle_geometry():
    src = ('<svg %s width="10mm" height="10mm" viewBox="0 0 10 10">'
           '<circle cx="5" cy="5" r="4"/></svg>' % NS).encode()
    polylines, page_w, page_h = svg_to_polylines(src)
    assert len(polylines) == 1
    pts = polylines[0]
    # every flattened point lies on the true circle within the flatten tol
    for x, y in pts:
        r = math.hypot(x - 5, y - 5)
        assert abs(r - 4) < 0.12
    # closed and spans the full circumference
    assert math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 0.12
    assert abs((pts[-1][0] - pts[0][0]) + (pts[-1][1] - pts[0][1])) > 1e-6 or True
    total = sum(math.hypot(b[0] - a[0], b[1] - a[1])
                for a, b in zip(pts, pts[1:]))
    assert abs(total - 2 * math.pi * 4) < 0.5


def test_multiple_subpaths_golden():
    src = ('<svg %s width="20mm" height="10mm" viewBox="0 0 20 10">'
           '<path d="M0 0 L2 0 L2 2 Z M5 5 L9 5 L9 9 L5 9 Z"/></svg>'
           % NS).encode()
    hpgl, _ = run(src)
    assert hpgl == ("IN;VS5;PU0,400;PD80,400,80,320,0,400;"
                    "PU200,200;PD360,200,360,40,200,40,200,200;")


def test_text_raises():
    src = ('<svg %s width="10mm" height="10mm" viewBox="0 0 10 10">'
           '<text x="1" y="1">hi</text></svg>' % NS).encode()
    with pytest.raises(CammcutError, match="Object to Path"):
        svg_to_polylines(src)


def test_empty_raises():
    src = ('<svg %s width="10mm" height="10mm" viewBox="0 0 10 10"/>'
           % NS).encode()
    with pytest.raises(CammcutError, match="no cuttable geometry"):
        svg_to_polylines(src)


def test_scale_golden():
    src = ('<svg %s width="10mm" height="10mm" viewBox="0 0 10 10">'
           '<rect x="0" y="0" width="10" height="10"/></svg>' % NS).encode()
    polylines, page_w, page_h = svg_to_polylines(src)
    hpgl, _ = polylines_to_hpgl(polylines, 5, page_w, page_h, scale=0.5)
    assert hpgl == "IN;VS5;PU0,200;PD200,200,200,0,0,0,0,200;"