"""Tidy ops on the document's path items.

Ops run in each item's local space; mm tolerances are converted using the
item's transform scale, so an imported px-space path behaves the same as a
native mm-space one. `check` is detection-only; the fixing ops each report
what they changed. Honest limits: simplify/flatten bake curves into line
segments; closing open paths adds a straight cut; self-crossing detection
finds proper transversal crossings only (tangential touches are missed).
"""

from __future__ import annotations

import math

from ..schemas import Item
from . import paths

# flatten tolerance for geometry used by checks, in mm
CHECK_CHORD_MM = 0.05


class TidyError(ValueError):
    pass


def _item_scale(item: Item) -> float:
    a, b, c, d = item.transform[0:4]
    det = abs(a * d - b * c)
    if det == 0:
        raise TidyError(f"item {item.id} has a degenerate transform")
    return math.sqrt(det)


# ----------------------------------------------------------------- checks

def check_items(items: list[Item]) -> dict:
    """Detection-only pass over the whole item list (document mm space)."""
    open_subpaths = 0
    dup_points = 0
    crossings = 0
    crossing_examples: list[str] = []
    for item in items:
        try:
            subpaths = paths.parse_d(item.d)
        except paths.PathError as e:
            raise TidyError(f"item {item.id}: {e}") from e
        open_subpaths += sum(1 for _segs, closed in subpaths if not closed)
        local = 1.0 / _item_scale(item)
        eps = 0.001 * local  # same threshold dedupe_points removes at
        for pts, _closed in paths.flatten(subpaths, eps):
            for k in range(1, len(pts)):
                if math.isclose(pts[k][0], pts[k - 1][0], abs_tol=eps) \
                        and math.isclose(pts[k][1], pts[k - 1][1], abs_tol=eps):
                    dup_points += 1
        polys = paths.flatten(subpaths, CHECK_CHORD_MM * local)
        t = item.transform
        for pt in paths.self_crossings(polys):
            crossings += 1
            if len(crossing_examples) < 5:
                dx = t[0] * pt[0] + t[2] * pt[1] + t[4]
                dy = t[1] * pt[0] + t[3] * pt[1] + t[5]
                crossing_examples.append(f"{item.id} @ ({dx:.2f}, {dy:.2f}) mm")
    return {
        "open_subpaths": open_subpaths,
        "duplicate_points": dup_points,
        "self_crossings": crossings,
        "crossing_examples": crossing_examples,
    }


# --------------------------------------------------------------------- ops

def close_paths(items: list[Item]) -> tuple[list[Item], int]:
    """Append Z to every open subpath. Warns: the close is a straight cut."""
    changed = 0
    out = []
    for item in items:
        try:
            subpaths = paths.parse_d(item.d)
        except paths.PathError as e:
            raise TidyError(f"item {item.id}: {e}") from e
        n_open = sum(1 for _segs, closed in subpaths if not closed)
        if n_open == 0:
            out.append(item)
            continue
        # re-serialise with closure flags; keep original command geometry
        parts = []
        for segs, closed in subpaths:
            first = segs[0][1]
            parts.append(f"M{paths.fmt(first[0])} {paths.fmt(first[1])}")
            for seg in segs:
                if seg[0] == "L":
                    p = seg[2]
                    parts.append(f"L{paths.fmt(p[0])} {paths.fmt(p[1])}")
                elif seg[0] == "C":
                    p1, p2, p3 = seg[2], seg[3], seg[4]
                    parts.append(
                        f"C{paths.fmt(p1[0])} {paths.fmt(p1[1])} "
                        f"{paths.fmt(p2[0])} {paths.fmt(p2[1])} "
                        f"{paths.fmt(p3[0])} {paths.fmt(p3[1])}")
                elif seg[0] == "Q":
                    p1, p2 = seg[2], seg[3]
                    parts.append(
                        f"Q{paths.fmt(p1[0])} {paths.fmt(p1[1])} "
                        f"{paths.fmt(p2[0])} {paths.fmt(p2[1])}")
                else:  # "A"
                    _p0, rx, ry, rot, large, sweep, p2 = seg[1:]
                    parts.append(
                        f"A{paths.fmt(rx)} {paths.fmt(ry)} {paths.fmt(rot)} "
                        f"{int(large)} {int(sweep)} {paths.fmt(p2[0])} {paths.fmt(p2[1])}")
            if not closed:
                parts.append("Z")
        out.append(item.model_copy(update={"d": "".join(parts)}))
        changed += n_open
    return out, changed


def _reserialise(item: Item, polys: list) -> Item:
    parts = []
    for pts, closed in polys:
        parts.append(f"M{paths.fmt(pts[0][0])} {paths.fmt(pts[0][1])}")
        for x, y in pts[1:]:
            parts.append(f"L{paths.fmt(x)} {paths.fmt(y)}")
        if closed:
            parts.append("Z")
    return item.model_copy(update={"d": "".join(parts)})


def dedupe_points(items: list[Item]) -> tuple[list[Item], int]:
    """Drop consecutive points closer than 0.001 mm (flattened to lines)."""
    removed = 0
    out = []
    for item in items:
        subpaths = paths.parse_d(item.d)
        local = 1.0 / _item_scale(item)
        eps = 0.001 * local
        polys = paths.flatten(subpaths, eps)
        new_polys = []
        for pts, closed in polys:
            kept = [pts[0]]
            for p in pts[1:]:
                if math.isclose(p[0], kept[-1][0], abs_tol=eps) and \
                        math.isclose(p[1], kept[-1][1], abs_tol=eps):
                    removed += 1
                    continue
                kept.append(p)
            if len(kept) < 2:
                removed += 1  # single point subpath is noise
                continue
            new_polys.append((kept, closed))
        out.append(_reserialise(item, new_polys))
    return out, removed


def flatten_curves(items: list[Item], chord_mm: float = 0.1) -> tuple[list[Item], int]:
    """Bake curves into line segments at the given chord tolerance."""
    out = []
    n_curves = 0
    for item in items:
        subpaths = paths.parse_d(item.d)
        n_curves += sum(1 for segs, _c in subpaths for seg in segs if seg[0] in ("C", "Q", "A"))
        local = 1.0 / _item_scale(item)
        polys = paths.flatten(subpaths, chord_mm * local)
        out.append(_reserialise(item, polys))
    return out, n_curves


def simplify(items: list[Item], tol_mm: float = 0.05) -> tuple[list[Item], int]:
    """Flatten then RDP at tol_mm. Bakes curves; reports points removed."""
    out = []
    removed = 0
    for item in items:
        subpaths = paths.parse_d(item.d)
        local = 1.0 / _item_scale(item)
        polys = paths.flatten(subpaths, min(tol_mm, 0.05) * local)
        new_polys = []
        for pts, closed in polys:
            if closed:
                # compare against the loop start so the result stays closed
                body = pts[:-1] if math.isclose(pts[0][0], pts[-1][0], abs_tol=1e-9) \
                    and math.isclose(pts[0][1], pts[-1][1], abs_tol=1e-9) else pts
                kept = paths.rdp(body + [body[0]], tol_mm * local)
            else:
                kept = paths.rdp(pts, tol_mm * local)
            removed += len(pts) - len(kept)
            if len(kept) >= 2:
                new_polys.append((kept, closed))
        out.append(_reserialise(item, new_polys))
    return out, removed


def run_op(name: str, items: list[Item], params: dict) -> tuple[list[Item], int]:
    if name == "close_paths":
        return close_paths(items)
    if name == "dedupe_points":
        return dedupe_points(items)
    if name == "flatten":
        return flatten_curves(items, chord_mm=float(params.get("chord_mm", 0.1)))
    if name == "simplify":
        return simplify(items, tol_mm=float(params.get("tol_mm", 0.05)))
    raise TidyError(f"unknown op {name!r}")