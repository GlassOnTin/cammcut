#!/usr/bin/env python3
"""cammcut — cut SVG files on a Roland CAMM-1 (CX-24) via USB-parallel.

Pipeline: SVG (svgelements, transforms reified) -> polylines (mm) ->
CAMM-GL III mode 2 (HPGL-compatible) -> write-only stream to /dev/usb/lpN.

Verified against a CX-24 over a Prolific PL2305 (067b:2305) adapter.
Never read from the device: a read stalls the adapter's bulk endpoints
and every later write is silently swallowed.
"""

import argparse
import glob
import io
import math
import os
import sys

import svgelements

# 1 HPGL unit = 0.025 mm; svgelements works in px at 96 ppi.
HPGL_PER_MM = 40.0
PX_PER_MM = 96.0 / 25.4

# CX-24 cutting area in mm; used to sanity-check placement.
MAX_X_MM = 584.0
MAX_Y_MM = 25000.0

PL2305_VID = "067b"
PL2305_PID = "2305"

FLATTEN_TOL_MM = 0.1


class CammcutError(Exception):
    pass


# ---------------------------------------------------------------- geometry

def _segment_steps(seg):
    """Subdivision count for a curve segment at FLATTEN_TOL_MM."""
    try:
        # svgelements' default length error is 1e-12 user units, which float64
        # never reaches on smooth curves — pass a px-level tolerance instead.
        # 0.05 px is ~0.013 mm: far below FLATTEN_TOL_MM, so the step count
        # is unchanged in practice but the recursion stops in a few levels.
        length_mm = seg.length(error=0.05, min_depth=4) / PX_PER_MM
    except Exception:
        return 1
    if length_mm <= 0:
        return 1
    n = int(math.ceil(math.sqrt(length_mm / FLATTEN_TOL_MM)))
    return max(2, min(512, n))


def svg_to_polylines(source):
    """Parse SVG bytes -> (polylines in mm +y down, page_w_mm, page_h_mm).

    Raises CammcutError on <text> (convert to paths first) or empty input.
    """
    if not hasattr(source, "read"):
        source = io.BytesIO(source)
    svg = svgelements.SVG.parse(source, reify=True)
    page_w = svg.width / PX_PER_MM
    page_h = svg.height / PX_PER_MM
    polylines = []
    for elem in svg.elements():
        if isinstance(elem, svgelements.Text):
            raise CammcutError(
                "SVG contains <text>; text needs outlines. Convert with "
                "Inkscape (Path > Object to Path) and re-export."
            )
        if not isinstance(elem, (svgelements.Path, svgelements.Shape)):
            continue
        if isinstance(elem, (svgelements.Group, svgelements.SVG)):
            continue
        try:
            d = elem.d()
        except AttributeError:
            continue
        path = svgelements.Path(d)
        for cur in _split_subpaths(path):
            pts = [(cur[0].end.real, cur[0].end.imag)]
            for seg in cur[1:]:  # cur[0] is the Move; pts starts at its end
                if isinstance(seg, svgelements.Close):
                    pts.append((cur[0].end.real, cur[0].end.imag))
                elif isinstance(seg, svgelements.Line):
                    pts.append((seg.end.real, seg.end.imag))
                else:
                    n = _segment_steps(seg)
                    for i in range(1, n + 1):
                        p = seg.point(i / n)
                        pts.append((p.real, p.imag))
            mm_pts = [(x / PX_PER_MM, y / PX_PER_MM) for x, y in pts]
            if len(mm_pts) >= 2:
                polylines.append(mm_pts)
    if not polylines:
        raise CammcutError("no cuttable geometry found in SVG")
    return polylines, page_w, page_h


def _split_subpaths(path):
    """Split a Path's segment list on Move; Close rejoins the start point."""
    subs = []
    cur = []
    for seg in path:
        if isinstance(seg, svgelements.Move):
            if len(cur) >= 2:
                subs.append(cur)
            cur = [seg]
        elif isinstance(seg, svgelements.Close):
            if cur:
                cur.append(seg)
        else:
            cur.append(seg)
    if len(cur) >= 2:
        subs.append(cur)
    return subs


# ---------------------------------------------------------------- transform

def polylines_to_hpgl(polylines, speed, page_w_mm, page_h_mm, x_mm=0.0,
                      y_mm=0.0, scale=1.0, mirror=False):
    """mm-space polylines -> (hpgl_string, device_mm_bounds).

    Y is flipped so the artwork's bottom-left corner sits at the machine
    origin plus (x_mm, y_mm). --mirror flips around the artwork's vertical
    centerline so placement is unchanged.
    """
    out = ["IN;", "VS%d;" % speed]
    bounds = [math.inf, math.inf, -math.inf, -math.inf]
    span_x = page_w_mm * scale
    span_y = page_h_mm * scale

    for poly in polylines:
        dev = []
        for x, y in poly:
            x = x * scale
            y = y * scale
            xd = (span_x - x if mirror else x) + x_mm  # device mm, x right
            yd = span_y - y + y_mm                     # device mm, y up
            dev.append((xd, yd))
            bounds[0] = min(bounds[0], xd)
            bounds[1] = min(bounds[1], yd)
            bounds[2] = max(bounds[2], xd)
            bounds[3] = max(bounds[3], yd)
            xu = round(xd * HPGL_PER_MM)
            yu = round(yd * HPGL_PER_MM)
            if len(dev) == 1:
                out.append("PU%d,%d;" % (xu, yu))
            elif len(dev) == 2:
                out.append("PD%d,%d," % (xu, yu))
            else:
                out[-1] += "%d,%d," % (xu, yu)
        if len(dev) >= 2:
            out[-1] = out[-1][:-1] + ";"  # terminate the PD run
    return "".join(out), bounds


# ---------------------------------------------------------------- device

def find_devices():
    """All /dev/usb/lp* nodes whose USB parent is the PL2305."""
    found = []
    for node in sorted(glob.glob("/dev/usb/lp*")):
        vid, pid = _node_vid_pid(node)
        if (vid, pid) == (PL2305_VID, PL2305_PID):
            found.append(node)
    return found


def _node_vid_pid(node):
    name = os.path.basename(node)
    iface = os.path.realpath("/sys/class/usbmisc/%s/device" % name)
    dev = os.path.dirname(iface)
    try:
        vid = open(os.path.join(dev, "idVendor")).read().strip().lower()
        pid = open(os.path.join(dev, "idProduct")).read().strip().lower()
        return vid, pid
    except OSError:
        return None, None


def resolve_device(explicit=None):
    if explicit:
        if not os.path.exists(explicit):
            raise CammcutError("device %s does not exist" % explicit)
        return explicit
    devs = find_devices()
    if not devs:
        raise CammcutError(
            "no PL2305 (067b:2305) usblp device found. Plug in the adapter "
            "or pass --device."
        )
    if len(devs) > 1:
        raise CammcutError(
            "multiple PL2305 devices found: %s. Pass --device." % ", ".join(devs)
        )
    return devs[0]


def send(device, data, chunk=4096):
    """Write-only stream. NEVER read: reads stall the PL2305 permanently."""
    fd = os.open(device, os.O_WRONLY)
    try:
        for i in range(0, len(data), chunk):
            os.write(fd, data[i:i + chunk])
    finally:
        os.close(fd)


# ---------------------------------------------------------------- preview

def preview_svg(polylines):
    xs = [p[0] for poly in polylines for p in poly]
    ys = [p[1] for poly in polylines for p in poly]
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    w, h = hi_x - lo_x, hi_y - lo_y
    pad = max(w, h) * 0.05 + 1
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%.2fmm" height="%.2fmm" '
        'viewBox="%.2f %.2f %.2f %.2f">'
        % (w + 2 * pad, h + 2 * pad, lo_x - pad, lo_y - pad, w + 2 * pad, h + 2 * pad)
    ]
    for poly in polylines:
        d = "M " + " L ".join("%.3f %.3f" % p for p in poly)
        lines.append('<path d="%s" fill="none" stroke="black" stroke-width="0.1"/>' % d)
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- cli

def check_bounds(bounds):
    if bounds[0] == math.inf:
        return
    if (bounds[0] < 0 or bounds[1] < 0
            or bounds[2] > MAX_X_MM or bounds[3] > MAX_Y_MM):
        print(
            "warning: artwork extends outside the CX-24 cutting area: "
            "x %.1f..%.1f mm (max 0..%d), y %.1f..%.1f mm (max 0..%d)"
            % (bounds[0], bounds[2], MAX_X_MM, bounds[1], bounds[3], MAX_Y_MM),
            file=sys.stderr,
        )


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cammcut", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_cut = sub.add_parser("cut", help="parse SVG and cut it")
    p_cut.add_argument("svg", type=argparse.FileType("rb"))
    p_cut.add_argument("--speed", type=int, default=5, metavar="CM/S")
    p_cut.add_argument("--x", type=float, default=0.0, metavar="MM",
                       help="offset right of machine origin")
    p_cut.add_argument("--y", type=float, default=0.0, metavar="MM",
                       help="offset up of machine origin")
    p_cut.add_argument("--scale", type=float, default=1.0)
    p_cut.add_argument("--mirror", action="store_true",
                       help="mirror horizontally (cut face-down)")
    p_cut.add_argument("--device", default=None, metavar="DEV")
    p_cut.add_argument("--dry-run", default=None, metavar="FILE",
                       help="write CAMM-GL to FILE instead of cutting")

    p_prev = sub.add_parser("preview", help="render the toolpath to an SVG")
    p_prev.add_argument("svg", type=argparse.FileType("rb"))
    p_prev.add_argument("-o", "--out", default="cammcut-preview.svg")

    sub.add_parser("probe", help="send invalid bytes (expect Er1 on machine LCD)")
    sub.add_parser("devices", help="list detected PL2305 usblp nodes")

    args = ap.parse_args(argv)

    try:
        if args.cmd == "devices":
            devs = find_devices()
            print("\n".join(devs) if devs else "no PL2305 usblp devices found")
            return 0

        if args.cmd == "probe":
            dev = resolve_device(None)
            send(dev, b"z" * 200)
            print("sent 200 invalid bytes to %s — expect 'Er1: Wrong Cmd' "
                  "on the machine LCD" % dev)
            return 0

        polylines, page_w, page_h = svg_to_polylines(args.svg.read())

        if args.cmd == "preview":
            with open(args.out, "w") as f:
                f.write(preview_svg(polylines))
            print("wrote %s" % args.out)
            return 0

        # cut
        hpgl, bounds = polylines_to_hpgl(
            polylines, args.speed, page_w, page_h,
            args.x, args.y, args.scale, args.mirror)
        check_bounds(bounds)
        if args.dry_run:
            with open(args.dry_run, "w") as f:
                f.write(hpgl)
            print("wrote %s (%d bytes)" % (args.dry_run, len(hpgl)))
            return 0
        dev = resolve_device(args.device)
        send(dev, hpgl.encode("ascii"))
        print("cut %d bytes -> %s (speed %d cm/s)" % (len(hpgl), dev, args.speed))
        return 0
    except CammcutError as e:
        print("cammcut: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())