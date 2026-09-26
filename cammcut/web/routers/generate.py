"""Text→image generation endpoints (nexos.ai)."""

import io

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...cammcut import CammcutError
from .. import settings
from ..services import generate
from .assets import _store_asset

router = APIRouter(prefix="/api/generate", tags=["generate"])


class GenerateBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    model: str | None = None
    size: str | None = None


@router.get("/status")
def status():
    return {
        "configured": bool(settings.NEXOS_KEY),
        "models": generate.IMAGE_MODELS,
        "default_model": generate.DEFAULT_MODEL,
        "sizes": generate.SIZES,
    }


@router.post("/image")
def generate_image(body: GenerateBody):
    """Sync endpoint on purpose: the upstream call blocks for tens of
    seconds, so it must run in FastAPI's threadpool, not the event loop
    (SSE and job progress share that loop)."""
    if not settings.NEXOS_KEY:
        raise HTTPException(
            400,
            "image generation is not configured — set CAMMCUT_NEXOS_KEY "
            "(in data/env.local) and restart the server")
    model = body.model or generate.DEFAULT_MODEL
    size = body.size or generate.SIZES[0]
    if model not in generate.IMAGE_MODELS:
        raise HTTPException(400, "unknown model %r" % model)
    if size not in generate.SIZES:
        raise HTTPException(400, "unsupported size %r" % size)
    try:
        data = generate.generate_image(body.prompt, model, size)
    except CammcutError as e:
        # upstream/gateway trouble is not a client error
        raise HTTPException(502, str(e)) from e
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        img.load()
    except Exception as e:
        raise HTTPException(502, "nexos.ai returned an unreadable image: %s" % e) from e
    image_id = _store_asset(
        ".png", data,
        {"kind": "image", "name": "generated.png", "w": w, "h": h,
         "model": model, "prompt": body.prompt[:200]})
    return {"image_id": image_id, "w_px": w, "h_px": h, "model": model}