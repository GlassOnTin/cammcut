"""Raster to vector via the potrace binary.

potrace is 1-bit: the result is a threshold silhouette, not a colour-aware
trace. The UI must say so. Requires the `potrace` executable on PATH.
"""

from __future__ import annotations

import io
import shutil
import subprocess

from PIL import Image

from ...cammcut import CammcutError
from .importsvg import import_svg


def potrace_available() -> bool:
    return shutil.which("potrace") is not None


def trace_image(
    data: bytes,
    threshold: int = 128,
    invert: bool = False,
    turdsize: int = 2,
    alphamax: float = 1.0,
    opttolerance: float = 0.2,
) -> dict:
    if not potrace_available():
        raise CammcutError(
            "potrace is not installed — run: sudo apt install potrace"
        )
    if not 0 <= threshold <= 255:
        raise CammcutError("threshold must be 0..255")

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        raise CammcutError(f"cannot read image: {e}") from e

    gray = img.convert("L")
    # pixels darker than the threshold become black; potrace traces black
    mask = gray.point(lambda v: 0 if v <= threshold else 255)
    if invert:
        mask = mask.point(lambda v: 255 - v)
    if mask.getextrema() == (255, 255):
        raise CammcutError(
            "nothing to trace: no pixels below the threshold — lower it or invert"
        )

    pbm = io.BytesIO()
    mask.convert("1").save(pbm, format="PPM")
    cmd = [
        "potrace", "-", "-s",
        "-t", str(int(turdsize)),
        "-a", str(float(alphamax)),
        "-O", str(float(opttolerance)),
        "-o", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, input=pbm.getvalue(), capture_output=True, timeout=120
        )
    except subprocess.TimeoutExpired as e:
        raise CammcutError("potrace timed out") from e
    if proc.returncode != 0:
        raise CammcutError(
            "potrace failed: " + proc.stderr.decode(errors="replace").strip()[:300]
        )

    result = import_svg(proc.stdout, item_prefix="trace")
    # potrace sizes input pixels at 72 dpi (its SVG says width=<n>pt for an
    # n-px image); the document convention is 96 dpi, so shrink by 72/96 to
    # keep a PNG and an SVG of the same design the same physical size
    k = 72.0 / 96.0
    for it in result["items"]:
        t = it.transform
        it.transform = [t[0] * k, t[1] * k, t[2] * k, t[3] * k, t[4], t[5]]
    result["width_mm"] = round(result["width_mm"] * k, 3)
    result["height_mm"] = round(result["height_mm"] * k, 3)
    result["warnings"].insert(
        0, "potrace traces a 1-bit threshold silhouette; fine detail depends "
           "on the threshold and source resolution"
    )
    return result