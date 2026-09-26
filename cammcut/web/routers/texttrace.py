"""Text-to-path and raster-trace endpoints."""

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..schemas import Item
from ..services import textpath, trace

router = APIRouter(prefix="/api", tags=["text-trace"])


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    font_id: str
    size_mm: float = Field(gt=0, le=500)
    tracking_mm: float = Field(default=0.0, ge=-50, le=50)


@router.get("/fonts")
def fonts():
    return textpath.list_fonts()


@router.get("/fonts/{font_id}/file")
def font_file(font_id: str):
    try:
        f = textpath.resolve_font(font_id)
    except textpath.TextError as e:
        raise HTTPException(404, str(e)) from e
    return FileResponse(f["path"], media_type="font/ttf", filename=f["family"])


@router.post("/text")
def text_to_path(req: TextRequest):
    try:
        f = textpath.resolve_font(req.font_id)
        result = textpath.text_to_path(
            req.text, f["path"], req.size_mm, req.tracking_mm
        )
    except textpath.TextError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "width_mm": result["width_mm"],
        "height_mm": result["height_mm"],
        "x_mm": result["x_mm"],
        "y_mm": result["y_mm"],
        "warnings": result["warnings"],
        "items": [Item(id="text-1", d=result["d"], transform=[1, 0, 0, 1, 0, 0])],
    }


class TraceParams(BaseModel):
    threshold: int = Field(default=128, ge=0, le=255)
    invert: bool = False
    turdsize: int = Field(default=2, ge=0, le=100)
    alphamax: float = Field(default=1.0, ge=0, le=1.334)
    opttolerance: float = Field(default=0.2, ge=0, le=5)


@router.post("/trace")
async def trace_image(file: UploadFile, threshold: int = 128, invert: bool = False,
                      turdsize: int = 2, alphamax: float = 1.0,
                      opttolerance: float = 0.2):
    params = TraceParams(threshold=threshold, invert=invert, turdsize=turdsize,
                         alphamax=alphamax, opttolerance=opttolerance)
    data = await file.read()
    try:
        return trace.trace_image(
            data,
            threshold=params.threshold,
            invert=params.invert,
            turdsize=params.turdsize,
            alphamax=params.alphamax,
            opttolerance=params.opttolerance,
        )
    except trace.CammcutError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/trace/status")
def trace_status():
    return {"potrace": trace.potrace_available()}