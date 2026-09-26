"""Path 'd' parsing, flattening and serialising for the tidy tools.

Documents hold only path items, but the 'd' may contain every SVG command
(imports go through svgelements, which emits arcs). Everything here works in
the item's local space; callers convert tolerances using the item's transform
scale (see svg_tools.local_scale).
"""

from __future__ import annotations

import math

Pt = tuple[float, float]
Seg = tuple  # ("L", p0, p1) | ("C", p0, p1, p2, p3) | ("Q", p0, p1, p2) | ("A", ...)
# SubPath = (segments, closed: bool)


class PathError(ValueError):
    pass


_NUM_CHARS = set("0123456789+-.eE")


def _read_number(s: str, i: int) -> tuple[float, int]:
    i = _skip_sep(s, i)
    j = i
    while j < len(s) and s[j] in _NUM_CHARS:
        j += 1
    if j == i:
        raise PathError(f"expected a number at offset {i}")
    return float(s[i:j]), j


def _skip_sep(s: str, i: int) -> int:
    while i < len(s) and s[i] in " ,\t\r\n":
        i += 1
    return i


def _arc_centre(x1, y1, rx, ry, phi_deg, large, sweep, x2, y2):
    """SVG endpoint -> centre parameterisation (mirrors the frontend one)."""
    phi = math.radians(phi_deg)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p = cos_p * dx + sin_p * dy
    y1p = -sin_p * dx + cos_p * dy
    rx, ry = max(abs(rx), 1e-12), max(abs(ry), 1e-12)
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp = coef * rx * y1p / ry
    cyp = -coef * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x1 + x2) / 2
    cy = sin_p * cxp + cos_p * cyp + (y1 + y2) / 2
    th1 = math.atan2((y1p - cyp) / ry, (x1p - cxp) / rx)
    th2 = math.atan2((-y1p - cyp) / ry, (-x1p - cxp) / rx)
    dth = th2 - th1
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi
    return cx, cy, rx, ry, th1, dth


def parse_d(d: str) -> list[tuple[list[Seg], bool]]:
    """Parse 'd' into subpaths [(segments, closed)]. Handles MmLlHhVvCcSsQqTtAaZz
    with implicit repeats and S/T control-point reflection."""
    subpaths: list[tuple[list[Seg], bool]] = []
    segs: list[Seg] = []
    cur: Pt | None = None
    start: Pt | None = None
    closed = False
    # previous drawing command, uppercase, for S/T reflection; "" after a move
    prev_draw = ""

    def finish():
        nonlocal segs, closed
        if segs:
            subpaths.append((segs, closed))
        segs = []
        closed = False

    i, n = 0, len(d)
    cmd = ""
    rel = False
    while i < n:
        i = _skip_sep(d, i)
        if i >= n:
            break
        if d[i].isalpha():
            cmd = d[i]
            rel = cmd.islower()
            i += 1
        elif not cmd:
            raise PathError(f"unexpected character at offset {i}")
        # (implicit repeats keep cmd/rel from the previous round)
        c = cmd.upper()

        if c == "Z":
            if cur is not None and start is not None \
                    and not (math.isclose(cur[0], start[0], abs_tol=1e-9)
                             and math.isclose(cur[1], start[1], abs_tol=1e-9)):
                segs.append(("L", cur, start))
            closed = True
            finish()
            cur, start = start, None
            prev_draw = ""
            continue

        if cur is None and c != "M":
            raise PathError("path data must start with a move")

        if c == "M":
            x, i = _read_number(d, i)
            y, i = _read_number(d, i)
            pt = (cur[0] + x, cur[1] + y) if (rel and cur is not None) else (x, y)
            finish()
            cur, start = pt, pt
            cmd, rel = "L", False  # implicit repeats after M are lines
            prev_draw = ""
            continue

        if c == "L":
            x, i = _read_number(d, i)
            y, i = _read_number(d, i)
            p2 = (cur[0] + x, cur[1] + y) if rel else (x, y)
            segs.append(("L", cur, p2))
            cur = p2
        elif c == "H":
            x, i = _read_number(d, i)
            p2 = (cur[0] + x, cur[1]) if rel else (x, cur[1])
            segs.append(("L", cur, p2))
            cur = p2
        elif c == "V":
            y, i = _read_number(d, i)
            p2 = (cur[0], cur[1] + y) if rel else (cur[0], y)
            segs.append(("L", cur, p2))
            cur = p2
        elif c == "C":
            x1, i = _read_number(d, i)
            y1, i = _read_number(d, i)
            x2, i = _read_number(d, i)
            y2, i = _read_number(d, i)
            x, i = _read_number(d, i)
            y, i = _read_number(d, i)
            p1 = (cur[0] + x1, cur[1] + y1) if rel else (x1, y1)
            p2 = (cur[0] + x2, cur[1] + y2) if rel else (x2, y2)
            p3 = (cur[0] + x, cur[1] + y) if rel else (x, y)
            segs.append(("C", cur, p1, p2, p3))
            cur = p3
        elif c == "S":
            x2, i = _read_number(d, i)
            y2, i = _read_number(d, i)
            x, i = _read_number(d, i)
            y, i = _read_number(d, i)
            if prev_draw in ("C", "S"):
                last = segs[-1]
                p1 = (2 * cur[0] - last[3][0], 2 * cur[1] - last[3][1])
            else:
                p1 = cur
            p2 = (cur[0] + x2, cur[1] + y2) if rel else (x2, y2)
            p3 = (cur[0] + x, cur[1] + y) if rel else (x, y)
            segs.append(("C", cur, p1, p2, p3))
            cur = p3
        elif c == "Q":
            x1, i = _read_number(d, i)
            y1, i = _read_number(d, i)
            x, i = _read_number(d, i)
            y, i = _read_number(d, i)
            p1 = (cur[0] + x1, cur[1] + y1) if rel else (x1, y1)
            p2 = (cur[0] + x, cur[1] + y) if rel else (x, y)
            segs.append(("Q", cur, p1, p2))
            cur = p2
        elif c == "T":
            x, i = _read_number(d, i)
            y, i = _read_number(d, i)
            if prev_draw in ("Q", "T"):
                last = segs[-1]
                p1 = (2 * cur[0] - last[2][0], 2 * cur[1] - last[2][1])
            else:
                p1 = cur
            p2 = (cur[0] + x, cur[1] + y) if rel else (x, y)
            segs.append(("Q", cur, p1, p2))
            cur = p2
        elif c == "A":
            rx, i = _read_number(d, i)
            ry, i = _read_number(d, i)
            rot, i = _read_number(d, i)
            large, i = _read_number(d, i)
            sweep, i = _read_number(d, i)
            x, i = _read_number(d, i)
            y, i = _read_number(d, i)
            p2 = (cur[0] + x, cur[1] + y) if rel else (x, y)
            segs.append(("A", cur, rx, ry, rot, large, sweep, p2))
            cur = p2
        else:
            raise PathError(f"unsupported command {cmd!r}")

        prev_draw = {"L": "L", "H": "L", "V": "L", "C": "C", "S": "C",
                     "Q": "Q", "T": "Q", "A": "A"}[c]
    finish()
    return subpaths


def _flatten_arc(seg: Seg, tol: float) -> list[Pt]:
    _, p0, rx, ry, rot, large, sweep, p1 = seg
    if math.isclose(p0[0], p1[0]) and math.isclose(p0[1], p1[1]):
        return []
    cx, cy, rx, ry, th1, dth = _arc_centre(
        p0[0], p0[1], abs(rx), abs(ry), rot, large, sweep, p1[0], p1[1])
    # sample so the chord stays under tol: sagitta s ≈ r*(1-cos(Δ/2))
    r = max(rx, ry)
    if r <= 0 or tol <= 0:
        steps = 64
    else:
        d_ang = 2 * math.acos(max(-1.0, min(1.0, 1 - tol / r)))
        steps = max(4, min(512, math.ceil(abs(dth) / d_ang) if d_ang > 0 else 512))
    phi = math.radians(rot)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    pts = []
    for k in range(1, steps + 1):
        t = th1 + dth * k / steps
        ex, ey = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + cos_p * ex - sin_p * ey, cy + sin_p * ex + cos_p * ey))
    return pts


def _flatten_cubic(seg: Seg, tol: float) -> list[Pt]:
    _, p0, p1, p2, p3 = seg
    length = math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
    steps = max(8, min(256, math.ceil(length / max(tol, 1e-6) / 2)))
    out = []
    for k in range(1, steps + 1):
        t = k / steps
        mt = 1 - t
        out.append((
            mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0],
            mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1],
        ))
    return out


def _flatten_quad(seg: Seg, tol: float) -> list[Pt]:
    _, p0, p1, p2 = seg
    length = math.dist(p0, p1) + math.dist(p1, p2)
    steps = max(8, min(256, math.ceil(length / max(tol, 1e-6) / 2)))
    out = []
    for k in range(1, steps + 1):
        t = k / steps
        mt = 1 - t
        out.append((
            mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0],
            mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1],
        ))
    return out


def flatten(subpaths: list[tuple[list[Seg], bool]], tol: float) -> list[tuple[list[Pt], bool]]:
    """Subpaths -> [(points, closed)]; every point list starts at the subpath
    start and ends at the last on-path point (no implicit closure)."""
    out = []
    for segs, closed in subpaths:
        pts: list[Pt] = []
        if segs:
            pts.append(segs[0][1])  # subpath start point
        for seg in segs:
            kind = seg[0]
            if kind == "L":
                pts.append(seg[2])
            elif kind == "C":
                pts.extend(_flatten_cubic(seg, tol))
            elif kind == "Q":
                pts.extend(_flatten_quad(seg, tol))
            elif kind == "A":
                pts.extend(_flatten_arc(seg, tol))
            else:  # pragma: no cover
                raise PathError(f"unknown segment {kind}")
        if pts:
            out.append((pts, closed))
    return out


def fmt(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def polylines_to_d(polys: list[tuple[list[Pt], bool]]) -> str:
    parts = []
    for pts, closed in polys:
        parts.append(f"M{fmt(pts[0][0])} {fmt(pts[0][1])}")
        for x, y in pts[1:]:
            parts.append(f"L{fmt(x)} {fmt(y)}")
        if closed:
            parts.append("Z")
    return "".join(parts)


def rdp(points: list[Pt], tol: float) -> list[Pt]:
    """Ramer–Douglas–Peucker (iterative, no recursion limit on long paths)."""
    if len(points) < 3 or tol <= 0:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        best, idx = -1.0, -1
        for k in range(a + 1, b):
            px, py = points[k]
            if norm == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                d = abs(dy * (px - ax) - dx * (py - ay)) / norm
            if d > best:
                best, idx = d, k
        if best > tol and idx > 0:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [p for p, k in zip(points, keep, strict=True) if k]


def _segs_proper_cross(p1, p2, p3, p4) -> bool:
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)
    return ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4))


def self_crossings(polys: list[tuple[list[Pt], bool]], eps: float = 1e-9) -> list[Pt]:
    """Proper crossing points within/between polylines. Segments that merely
    share an endpoint (corners, loop closures, subpath joins) are excluded.
    Returns the crossing points (one per crossing pair)."""
    segments: list[tuple[Pt, Pt, int, int]] = []
    for pi, (pts, _closed) in enumerate(polys):
        for si in range(len(pts) - 1):
            segments.append((pts[si], pts[si + 1], pi, si))
    segments.sort(key=lambda s: min(s[0][0], s[1][0]))
    crossings: list[Pt] = []
    seen: set[tuple[float, float]] = set()
    n = len(segments)
    for i in range(n):
        p1, p2, pi, si = segments[i]
        hi = max(p1[0], p2[0])
        for j in range(i + 1, n):
            q1, q2, pj, sj = segments[j]
            lo_j = min(q1[0], q2[0])
            if lo_j > hi + eps:
                break
            if pi == pj and abs(si - sj) == 1:
                continue
            if _segs_proper_cross(p1, p2, q1, q2):
                # one crossing may span several segment pairs (overlapping
                # sliver lines): count distinct locations, to 0.01 local units
                loc = (round((p1[0] + p2[0]) / 2, 2), round((p1[1] + p2[1]) / 2, 2))
                if loc not in seen:
                    seen.add(loc)
                    crossings.append(loc)
    return crossings