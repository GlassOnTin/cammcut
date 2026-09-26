"""Text to path outlines via fontTools.

Glyph outlines are converted with SVGPathPen, flipped vertically (font units
are y-up, SVG y-down) and scaled so `size_mm` is the em size. Kerning uses the
legacy `kern` table only — complex scripts will be wrong; callers get a
warning back when the font has no kern table.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

FONT_DIRS = ["/usr/share/fonts", str(Path(__file__).parents[3] / "data" / "fonts")]
FONT_EXTS = (".ttf", ".otf")


class TextError(ValueError):
    pass


def list_fonts() -> list[dict]:
    """All usable font files, as {id, family, style, path}."""
    out: list[dict] = []
    seen: set[str] = set()
    for root in FONT_DIRS:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if not f.lower().endswith(FONT_EXTS):
                    continue
                p = os.path.join(dirpath, f)
                if p in seen:
                    continue
                seen.add(p)
                try:
                    font = TTFont(p, fontNumber=0, lazy=True)
                    name = font["name"]
                    family = name.getDebugName(16) or name.getDebugName(1) or Path(f).stem
                    style = name.getDebugName(17) or name.getDebugName(2) or ""
                    font.close()
                except Exception:
                    family, style = Path(f).stem, ""
                out.append({
                    "id": hashlib.sha1(p.encode()).hexdigest()[:12],
                    "family": family,
                    "style": style,
                    "path": p,
                })
    out.sort(key=lambda d: (d["family"].lower(), d["style"]))
    return out


def resolve_font(font_id: str) -> dict:
    for f in list_fonts():
        if f["id"] == font_id:
            return f
    raise TextError(f"unknown font id {font_id!r}")


def text_to_path(text: str, font_path: str, size_mm: float, tracking_mm: float = 0.0) -> dict:
    """Convert one line of text to a single path 'd' in mm.

    Origin: pen starts at (0, 0), baseline y=0, glyphs extend up (negative y).
    Returns {d, width_mm, height_mm, warnings}.
    """
    if not text:
        raise TextError("empty text")
    if size_mm <= 0:
        raise TextError("size_mm must be > 0")

    font = TTFont(font_path, fontNumber=0)
    upm = font["head"].unitsPerEm
    scale = size_mm / upm
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"]

    kern: dict[tuple[str, str], int] = {}
    if "kern" in font:
        try:
            kern = font["kern"].kernTables[0].kernTable
        except Exception:
            kern = {}

    warnings: list[str] = []
    missing = [ch for ch in text if ord(ch) not in cmap and ch not in ("\n", "\r", "\t")]
    if missing:
        uniq = "".join(sorted(set(missing)))
        warnings.append(f"glyphs missing from font and skipped: {uniq!r}")
    if not kern:
        warnings.append("font has no legacy kern table; spacing is un-kerned")

    parts: list[str] = []
    bounds: list[tuple[float, float, float, float]] = []
    pen_x = 0.0
    prev_glyph: str | None = None
    for ch in text:
        gname = cmap.get(ord(ch))
        if gname is None:
            continue
        if prev_glyph is not None and (prev_glyph, gname) in kern:
            pen_x += kern[(prev_glyph, gname)] * scale
        glyph = glyph_set[gname]
        t = Transform(scale, 0, 0, -scale, pen_x, 0)
        spen = SVGPathPen(glyph_set)
        glyph.draw(TransformPen(spen, t))
        d = spen.getCommands()
        if d:
            parts.append(d)
            bp = BoundsPen(glyph_set)
            glyph.draw(TransformPen(bp, t))
            if bp.bounds:
                bounds.append(bp.bounds)
        pen_x += hmtx[gname][0] * scale + tracking_mm
        prev_glyph = gname

    if not parts:
        raise TextError("no drawable glyphs in text")

    x0 = min(b[0] for b in bounds)
    y0 = min(b[1] for b in bounds)
    x1 = max(b[2] for b in bounds)
    y1 = max(b[3] for b in bounds)
    return {
        "d": " ".join(parts),
        "width_mm": x1 - x0,
        "height_mm": y1 - y0,
        "x_mm": x0,
        "y_mm": y0,
        "warnings": warnings,
    }