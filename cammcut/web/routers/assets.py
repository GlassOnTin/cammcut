"""Asset upload/serving: SVG imports and raster images."""

import io
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import settings
from ..services import importsvg

router = APIRouter(prefix="/api", tags=["assets"])

ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def _upload_dir(asset_id: str) -> Path:
    return settings.subdir("uploads") / asset_id


def _store_asset(ext: str, data: bytes, meta: dict) -> str:
    asset_id = uuid.uuid4().hex[:12]
    d = _upload_dir(asset_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / ("original%s" % ext)).write_bytes(data)
    (d / "meta.json").write_text(json.dumps(meta))
    return asset_id


def get_asset_dir(asset_id: str) -> Path:
    d = _upload_dir(asset_id)
    if not d.is_dir():
        raise HTTPException(404, "asset not found")
    return d


@router.post("/import/svg")
async def import_svg(file: UploadFile):
    data = await file.read()
    try:
        result = importsvg.import_svg(data, item_prefix=file.filename or "import")
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    asset_id = _store_asset(".svg", data, {"kind": "svg", "name": file.filename})
    result["svg_id"] = asset_id
    return result


@router.post("/import/image")
async def import_image(file: UploadFile):
    from PIL import Image

    data = await file.read()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE:
        raise HTTPException(400, "unsupported image type %r" % ext)
    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        img.load()
    except Exception as e:
        raise HTTPException(400, "cannot read image: %s" % e) from e
    asset_id = _store_asset(ext, data, {"kind": "image", "name": file.filename,
                                        "w": w, "h": h})
    return {"image_id": asset_id, "w_px": w, "h_px": h, "name": file.filename}


IMAGE_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".tif": "image/tiff", ".tiff": "image/tiff",
}


@router.get("/assets/{asset_id}/raw")
def asset_raw(asset_id: str):
    d = get_asset_dir(asset_id)
    files = list(d.glob("original.*"))
    if not files:
        raise HTTPException(404, "asset file missing")
    suffix = files[0].suffix.lower()
    if suffix == ".svg":
        media = "image/svg+xml"
    else:
        media = IMAGE_MIME.get(suffix, "application/octet-stream")
    return FileResponse(files[0], media_type=media)