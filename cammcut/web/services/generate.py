"""Text→image generation via the nexos.ai gateway (OpenAI-compatible).

Verified against the real gateway with the operator's key: POST
/images/generations with a Bearer key; GPT Image models return
{"data": [{"b64_json": ...}]} by default. dall-e-3 is NOT hosted there.
"""

import base64

import httpx

from ...cammcut import CammcutError
from .. import settings

# Image-capable models on the gateway (IDs as listed by GET /models —
# they contain spaces). Sizes are the GPT Image set; FLUX models may
# reject the non-square ones, which surfaces as a nexos error.
IMAGE_MODELS = [
    "GPT Image 1 mini",
    "GPT Image 1.5",
    "GPT Image 2",
    "GPT Image 2.5 Flare",
    "GPT Image 2.5 Sunburst",
    "FLUX 1.1 Pro",
    "FLUX 1.1 Pro (1)",
]
DEFAULT_MODEL = "GPT Image 1 mini"
SIZES = ["1024x1024", "1536x1024", "1024x1536"]

# Image models can take tens of seconds; give the read plenty of slack.
TIMEOUT = httpx.Timeout(240.0, connect=10.0)

_client: httpx.Client | None = None


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=TIMEOUT)
    return _client


def _detail(body: bytes) -> str:
    return body.decode("utf-8", "replace").strip()[:300]


def generate_image(prompt: str, model: str, size: str) -> bytes:
    """Generate one image, return the image bytes."""
    if not settings.NEXOS_KEY:
        raise CammcutError(
            "image generation is not configured — set CAMMCUT_NEXOS_KEY "
            "(in data/env.local) and restart the server")
    try:
        r = _http().post(
            "%s/images/generations" % settings.NEXOS_URL,
            headers={"Authorization": "Bearer %s" % settings.NEXOS_KEY},
            json={"model": model, "prompt": prompt, "size": size},
        )
    except httpx.HTTPError as e:
        raise CammcutError("nexos.ai request failed: %s" % e) from e
    if r.status_code != 200:
        raise CammcutError(
            "nexos.ai error %s: %s" % (r.status_code, _detail(r.content)))
    data = r.json().get("data") or []
    if not data:
        raise CammcutError("nexos.ai returned no image data")
    b64 = data[0].get("b64_json")
    if b64:
        try:
            return base64.b64decode(b64)
        except (ValueError, TypeError) as e:
            raise CammcutError("nexos.ai sent undecodable image data") from e
    url = data[0].get("url")
    if url:
        try:
            img = _http().get(url)
        except httpx.HTTPError as e:
            raise CammcutError("nexos.ai image download failed: %s" % e) from e
        if img.status_code != 200:
            raise CammcutError(
                "nexos.ai image download failed: HTTP %s" % img.status_code)
        return img.content
    raise CammcutError("nexos.ai response had neither b64_json nor url")