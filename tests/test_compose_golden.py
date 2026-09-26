"""Golden tests: project JSON -> exact HPGL through the compose pipeline.

Pins the placement semantics: content-bbox paging (artwork bottom-left on
machine origin + offset) and the y-flip, independent of artboard size.
"""

from cammcut.web.schemas import Item, JobSettings, Layer, Project
from cammcut.web.services.compose import build_plan

SQ = "M 0 0 L 10 0 L 10 10 L 0 10 Z"
IDENTITY = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]


def make_project(d=SQ, transform=IDENTITY, artboard=(584.0, 300.0)):
    return Project(
        id="t", name="t",
        artboard={"w_mm": artboard[0], "h_mm": artboard[1]},
        layers=[Layer(id="l", name="L", items=[Item(id="i", d=d, transform=list(transform))])],
    )


def test_rotation_golden():
    # square rotated 90 degrees about its centre: same bbox, different start
    # corner -> traversal starts at device (10,10) in y-down page space
    proj = make_project(transform=[0, 1, -1, 0, 10, 0])
    plan = build_plan(proj, JobSettings(speed=5))
    assert plan.hpgl == "IN;VS5;PU400,400;PD400,0,0,0,0,400,400,400;"


def test_artboard_origin_golden():
    # origin=artboard: the artboard is the page; square offset (100,100) in
    # artboard mm -> device (100..110, 190..200) (y-up)
    proj = make_project(transform=[1, 0, 0, 1, 100, 100])
    plan = build_plan(proj, JobSettings(speed=5, origin="artboard"))
    assert plan.hpgl == "IN;VS5;PU4000,8000;PD4400,8000,4400,7600,4000,7600,4000,8000;"


def test_content_origin_offset_golden():
    # origin=content (default): content bbox corner lands on origin + offset
    proj = make_project(transform=[1, 0, 0, 1, 100, 100])
    plan = build_plan(proj, JobSettings(speed=5, x_mm=2.0, y_mm=3.0))
    assert plan.hpgl == "IN;VS5;PU80,520;PD480,520,480,120,80,120,80,520;"


def test_scale_golden():
    proj = make_project()
    plan = build_plan(proj, JobSettings(speed=5, scale=0.5))
    assert plan.hpgl == "IN;VS5;PU0,200;PD200,200,200,0,0,0,0,200;"


def test_mirror_keeps_placement():
    proj = make_project()
    plan = build_plan(proj, JobSettings(speed=5, mirror=True))
    assert plan.hpgl == "IN;VS5;PU400,400;PD0,400,0,0,400,0,400,400;"