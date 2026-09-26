"""SVG upload -> path items for the editor document.

svgelements with reify=True bakes viewport and element transforms into the
coordinates, so each element's d() is already in the file's output pixel
space. Items keep that px-space d and carry a scale transform converting to
the document's mm space. Text elements cannot be cut (the CLI errors on
them); they are reported and skipped. Masks/clip-paths are ignored by the
cut pipeline, so their presence is a warning, not silence.
"""

import io

import svgelements

from ...cammcut import PX_PER_MM, CammcutError
from ..schemas import Item

MM_PER_PX = 25.4 / 96.0
SCALE_TO_MM = [MM_PER_PX, 0.0, 0.0, MM_PER_PX, 0.0, 0.0]


def import_svg(source, item_prefix: str = "imp") -> dict:
    """SVG bytes -> {width_mm, height_mm, warnings, items}."""
    if not hasattr(source, "read"):
        source = io.BytesIO(source)
    data = source.read()
    svg = svgelements.SVG.parse(io.BytesIO(data), reify=True)
    width_mm = svg.width / PX_PER_MM
    height_mm = svg.height / PX_PER_MM

    warnings = []
    lower = data.decode("utf-8", errors="replace").lower()
    for marker, msg in (
        ("<text", "<text> element skipped: convert text to paths first "
         "(Inkscape: Path > Object to Path)"),
        ("<image", "<image> element skipped: raster data is not cuttable"),
        ("clip-path", "clip-path present: clipping is ignored, clipped parts "
         "will still be cut"),
        ("<mask", "mask present: masks are ignored, masked parts will still "
         "be cut"),
    ):
        if marker in lower:
            warnings.append(msg)

    items = []
    idx = 0
    for elem in svg.elements():
        if isinstance(elem, (svgelements.Group, svgelements.SVG)):
            continue
        if isinstance(elem, svgelements.Text):
            continue
        if not isinstance(elem, (svgelements.Path, svgelements.Shape)):
            continue
        try:
            d = elem.d()
        except AttributeError:
            continue
        if not d:
            continue
        idx += 1
        items.append(
            Item(id="%s-%d" % (item_prefix, idx), d=d, transform=list(SCALE_TO_MM))
        )
    if not items:
        raise CammcutError("no importable geometry found in SVG")
    return {
        "width_mm": round(width_mm, 3),
        "height_mm": round(height_mm, 3),
        "warnings": warnings,
        "items": items,
    }