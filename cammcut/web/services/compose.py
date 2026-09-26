"""Project JSON -> standalone SVG -> polylines -> HPGL + job estimates.

Placement semantics: polylines_to_hpgl y-flips within the page, putting the
page's bottom-left corner at the machine origin + (x_mm, y_mm). A project
artboard is not the page; by default we page-tight the *content* bbox so the
artwork's own bottom-left lands on the origin regardless of artboard size.
origin="artboard" makes the artboard itself the page (the user must set the
artboard height to the loaded material length for that to be meaningful).
"""

import math

from ...cammcut import (
    HPGL_PER_MM,
    MAX_X_MM,
    MAX_Y_MM,
    PX_PER_MM,
    polylines_to_hpgl,
    preview_svg,
    svg_to_polylines,
)
from ..schemas import Bounds, Item, JobSettings, Preview, Project, Violation

MM_PER_PX = 1.0 / PX_PER_MM


def _path_attrs(item: Item) -> str:
    attrs = 'd="%s"' % item.d
    if item.transform != [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]:
        t = item.transform
        attrs += ' transform="matrix(%s,%s,%s,%s,%s,%s)"' % tuple(
            _num(v) for v in t
        )
    if item.fill_rule == "evenodd":
        attrs += ' fill-rule="evenodd"'
    return attrs


def _num(v: float) -> str:
    s = "%.6f" % v
    return s.rstrip("0").rstrip(".") if "." in s else s


def project_to_svg(project: Project) -> str:
    """Artboard-space SVG: user units are mm, viewBox == physical size."""
    w, h = project.artboard.w_mm, project.artboard.h_mm
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%smm" height="%smm" '
        'viewBox="0 0 %s %s">' % (_num(w), _num(h), _num(w), _num(h))
    ]
    for layer in project.layers:
        if not layer.visible or not layer.items:
            continue
        out.append("<g>")
        for item in layer.items:
            out.append("<path %s/>" % _path_attrs(item))
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out)


def page_polylines(project: Project, origin: str):
    """Project -> (polylines, page_w_mm, page_h_mm) with the origin mode
    applied. Raises CammcutError when there is nothing to cut."""
    polylines, page_w, page_h = svg_to_polylines(project_to_svg(project).encode())
    if origin == "artboard":
        return polylines, page_w, page_h
    xs = [p[0] for poly in polylines for p in poly]
    ys = [p[1] for poly in polylines for p in poly]
    min_x, min_y = min(xs), min(ys)
    tight = [[(x - min_x, y - min_y) for x, y in poly] for poly in polylines]
    return tight, max(xs) - min_x, max(ys) - min_y


def bounds_violations(bounds, media_w_mm: float, media_h_mm: float) -> list[Violation]:
    """Bounds are device mm (y up). Check against media size and machine max."""
    out = []
    if bounds[0] == float("inf"):
        return out
    for axis, lo, hi, media, hard in (
        ("x", bounds[0], bounds[2], media_w_mm, MAX_X_MM),
        ("y", bounds[1], bounds[3], media_h_mm, MAX_Y_MM),
    ):
        if lo < 0 or hi > min(media, hard):
            out.append(
                Violation(
                    axis=axis,
                    detail="artwork spans %.1f..%.1f mm, media allows 0..%.1f mm"
                    % (lo, hi, min(media, hard)),
                )
            )
    return out


def polyline_lengths(polylines, scale: float):
    """(cut_len_mm, travel_len_mm) in device mm. Scale is uniform, so lengths
    measured in artboard mm scale linearly; translation/mirror don't matter."""
    cut = 0.0
    travel = 0.0
    prev_end = None
    for poly in polylines:
        if len(poly) < 2:
            continue
        if prev_end is not None:
            travel += (
                math.hypot(poly[0][0] - prev_end[0], poly[0][1] - prev_end[1]) * scale
            )
        for i in range(len(poly) - 1):
            cut += math.hypot(poly[i + 1][0] - poly[i][0], poly[i + 1][1] - poly[i][1])
        prev_end = poly[-1]
    return cut * scale, travel


def build_preview(project: Project, settings: JobSettings) -> Preview:
    """Full preview pipeline; CammcutError propagates for empty documents."""
    polylines, _page_w, _page_h = page_polylines(project, settings.origin)
    plan = build_plan(project, settings)
    return Preview(
        toolpath_svg=preview_svg(polylines),
        bounds=(
            Bounds(min_x=plan.bounds[0], min_y=plan.bounds[1],
                   max_x=plan.bounds[2], max_y=plan.bounds[3])
            if plan.bounds[0] != float("inf")
            else None
        ),
        violations=plan.violations,
        cut_len_mm=plan.cut_len_mm,
        travel_len_mm=plan.travel_len_mm,
        est_seconds=plan.est_seconds,
        byte_len=len(plan.hpgl),
    )


class JobPlan:
    def __init__(self, hpgl: str, bounds, violations: list[Violation],
                 cut_len_mm: float, travel_len_mm: float, est_seconds: float):
        self.hpgl = hpgl
        self.bounds = bounds
        self.violations = violations
        self.cut_len_mm = cut_len_mm
        self.travel_len_mm = travel_len_mm
        self.est_seconds = est_seconds


def build_plan(project: Project, settings: JobSettings) -> JobPlan:
    """Everything the runner and preview need, computed once."""
    polylines, page_w, page_h = page_polylines(project, settings.origin)
    hpgl, bounds = polylines_to_hpgl(
        polylines, settings.speed, page_w, page_h,
        settings.x_mm, settings.y_mm, settings.scale, settings.mirror,
    )
    cut, travel = polyline_lengths(polylines, settings.scale)
    # cut at speed cm/s; travel assumed 3x faster
    est = (cut / (settings.speed * 10.0)) + (travel / (settings.speed * 30.0))
    return JobPlan(
        hpgl=hpgl,
        bounds=bounds,
        violations=bounds_violations(bounds, settings.media_w_mm, settings.media_h_mm),
        cut_len_mm=round(cut, 1),
        travel_len_mm=round(travel, 1),
        est_seconds=round(est, 1),
    )


def item_count(project: Project) -> int:
    return sum(len(layer.items) for layer in project.layers)


# re-exported for routers
__all__ = [
    "MM_PER_PX", "JobPlan", "build_plan", "build_preview", "bounds_violations",
    "page_polylines", "project_to_svg", "item_count", "HPGL_PER_MM",
]