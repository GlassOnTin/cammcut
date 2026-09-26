"""nexos.ai generate service + router tests (mocked transport, no network)."""

import base64
import os
import tempfile

os.environ["CAMMCUT_DATA_DIR"] = tempfile.mkdtemp(prefix="cammcut-test-gen-")

import httpx
import pytest
from fastapi.testclient import TestClient

from cammcut.web import settings
from cammcut.web.app import create_app
from cammcut.web.services import generate

# 1x1 white PNG
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture()
def client(monkeypatch):
    # no key by default: tests opt in per-case
    monkeypatch.setattr(settings, "NEXOS_KEY", None)
    app = create_app()
    with TestClient(app) as c:
        yield c


def mock_nexos(monkeypatch, handler):
    monkeypatch.setattr(generate, "_client", httpx.Client(transport=httpx.MockTransport(handler)))


def test_generate_b64_response(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["json"] = request.read()
        return httpx.Response(200, json={"created": 1, "data": [
            {"b64_json": base64.b64encode(PNG_1PX).decode()}]})

    mock_nexos(monkeypatch, handler)
    monkeypatch.setattr(settings, "NEXOS_KEY", "k-test")
    out = generate.generate_image("a small anchor", "GPT Image 1 mini", "1024x1024")
    assert out == PNG_1PX
    assert seen["url"].endswith("/v1/images/generations")
    assert seen["auth"] == "Bearer k-test"
    body = seen["json"]
    assert b"GPT Image 1 mini" in body and b"a small anchor" in body
    assert b"response_format" not in body  # b64 is the gateway default


def test_generate_url_response(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/images/generations"):
            return httpx.Response(200, json={"data": [{"url": "https://img.nexos.test/x.png"}]})
        return httpx.Response(200, content=PNG_1PX)

    mock_nexos(monkeypatch, handler)
    monkeypatch.setattr(settings, "NEXOS_KEY", "k-test")
    assert generate.generate_image("p", "GPT Image 1 mini", "1024x1024") == PNG_1PX


def test_generate_no_key(monkeypatch):
    monkeypatch.setattr(settings, "NEXOS_KEY", None)
    with pytest.raises(Exception, match="CAMMCUT_NEXOS_KEY"):
        generate.generate_image("p", "GPT Image 1 mini", "1024x1024")


def test_generate_upstream_error(monkeypatch):
    mock_nexos(monkeypatch, lambda req: httpx.Response(500, text="boom"))
    monkeypatch.setattr(settings, "NEXOS_KEY", "k-test")
    with pytest.raises(Exception, match="500.*boom"):
        generate.generate_image("p", "GPT Image 1 mini", "1024x1024")


def test_generate_network_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    mock_nexos(monkeypatch, handler)
    monkeypatch.setattr(settings, "NEXOS_KEY", "k-test")
    with pytest.raises(Exception, match="nexos.ai request failed"):
        generate.generate_image("p", "GPT Image 1 mini", "1024x1024")


# ------------------------------------------------------------- API surface

def test_status_unconfigured(client):
    r = client.get("/api/generate/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert "GPT Image 1 mini" in body["models"]
    assert "key" not in str(body).lower()


def test_generate_endpoint_stores_asset(client, monkeypatch):
    monkeypatch.setattr(settings, "NEXOS_KEY", "k-test")
    monkeypatch.setattr(generate, "generate_image", lambda *a, **k: PNG_1PX)
    r = client.post("/api/generate/image",
                    json={"prompt": "anchor", "model": "GPT Image 1 mini", "size": "1024x1024"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == "GPT Image 1 mini"
    assert (body["w_px"], body["h_px"]) == (1, 1)
    raw = client.get("/api/assets/%s/raw" % body["image_id"])
    assert raw.status_code == 200
    assert raw.headers["content-type"] == "image/png"
    assert raw.content == PNG_1PX


def test_generate_endpoint_maps_upstream_error_to_502(client, monkeypatch):
    from cammcut.cammcut import CammcutError

    monkeypatch.setattr(settings, "NEXOS_KEY", "k-test")

    def boom(*a, **k):
        raise CammcutError("nexos.ai error 500: model unavailable")

    monkeypatch.setattr(generate, "generate_image", boom)
    r = client.post("/api/generate/image", json={"prompt": "anchor"})
    assert r.status_code == 502
    assert "500" in r.json()["detail"]


def test_generate_endpoint_validates_model_and_size(client, monkeypatch):
    monkeypatch.setattr(settings, "NEXOS_KEY", "k-test")
    assert client.post("/api/generate/image",
                       json={"prompt": "x", "model": "dall-e-3"}).status_code == 400
    assert client.post("/api/generate/image",
                       json={"prompt": "x", "size": "64x64"}).status_code == 400
    # empty prompt fails validation (app maps validation errors to 400)
    assert client.post("/api/generate/image", json={"prompt": ""}).status_code == 400


def test_generate_endpoint_unconfigured_is_400(client):
    r = client.post("/api/generate/image", json={"prompt": "anchor"})
    assert r.status_code == 400
    assert "CAMMCUT_NEXOS_KEY" in r.json()["detail"]


def test_asset_raw_png_mime(client):
    # a stored png must come back as image/png (was octet-stream)

    from cammcut.web.routers.assets import _store_asset
    aid = _store_asset(".png", PNG_1PX, {"kind": "image", "w": 1, "h": 1})
    r = client.get("/api/assets/%s/raw" % aid)
    assert r.headers["content-type"] == "image/png"