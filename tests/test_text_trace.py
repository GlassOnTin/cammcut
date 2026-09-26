"""Text-to-path and potrace tracing tests (trace tests skip without potrace)."""

import io
import os
import tempfile

os.environ["CAMMCUT_DATA_DIR"] = tempfile.mkdtemp(prefix="cammcut-test-")

import pytest
from fastapi.testclient import TestClient

from cammcut.web.app import create_app
from cammcut.web.services import textpath, trace


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def find_font(name_part: str) -> dict:
    fonts = textpath.list_fonts()
    matches = [f for f in fonts if name_part in f["path"]]
    assert matches, f"font {name_part} not found on this system"
    return matches[0]


# -------------------------------------------------------------------- fonts

def test_fonts_listed(client):
    r = client.get("/api/fonts")
    assert r.status_code == 200
    fonts = r.json()
    assert len(fonts) > 0
    for f in fonts:
        assert set(f) == {"id", "family", "style", "path"}
    assert any("DejaVu" in f["family"] for f in fonts)


def test_font_file_served(client):
    f = find_font("DejaVuSans.ttf")
    r = client.get("/api/fonts/%s/file" % f["id"])
    assert r.status_code == 200
    assert len(r.content) > 1000


def test_text_via_api(client):
    f = find_font("DejaVuSans.ttf")
    r = client.post("/api/text", json={
        "text": "Ag", "font_id": f["id"], "size_mm": 20.0,
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["d"].startswith("M")
    assert body["width_mm"] > 10  # 'A'+'g' at 20 mm em is well over 10 mm wide
    assert body["height_mm"] > 10
    # insertion code needs the bbox origin, not just the size
    assert isinstance(body["x_mm"], (int, float)) and isinstance(body["y_mm"], (int, float))


def test_text_unknown_font_400(client):
    r = client.post("/api/text", json={
        "text": "x", "font_id": "does-not-exist", "size_mm": 10,
    })
    assert r.status_code == 400


def test_text_empty_400(client):
    f = find_font("DejaVuSans.ttf")
    r = client.post("/api/text", json={"text": "", "font_id": f["id"], "size_mm": 10})
    assert r.status_code == 400


def test_text_missing_glyph_warns():
    f = find_font("DejaVuSans.ttf")
    r = textpath.text_to_path("ab", f["path"], 10.0)
    assert any("missing" in w for w in r["warnings"])


def test_text_kern_or_warning():
    f = find_font("DejaVuSans.ttf")
    r = textpath.text_to_path("AV", f["path"], 10.0)
    # DejaVu has a legacy kern table; if not, the API must say so
    assert r["warnings"] == [] or "kern" in r["warnings"][0]


# -------------------------------------------------------------------- trace

@pytest.fixture()
def disc_png():
    from PIL import Image, ImageDraw

    img = Image.new("L", (200, 200), 255)
    d = ImageDraw.Draw(img)
    d.ellipse((50, 50, 150, 150), fill=0)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.skipif(not trace.potrace_available(), reason="potrace not installed")
def test_trace_disc(client, disc_png):
    r = client.post(
        "/api/trace",
        params={"threshold": 128},
        files={"file": ("disc.png", disc_png, "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) >= 1
    assert any("1-bit" in w for w in body["warnings"])
    # 200 px image at the document's 96 dpi convention; potrace's fitted
    # curves run ~1% over, so allow 3%
    assert abs(body["width_mm"] - 200 * 25.4 / 96) < 200 * 25.4 / 96 * 0.03
    # the item's real geometry matches too (the 100 px disc), in doc mm
    from cammcut.web.services import paths as P

    it = body["items"][0]
    t = it["transform"]
    xs, ys = [], []
    for pts, _c in P.flatten(P.parse_d(it["d"]), 0.05):
        for x, y in pts:
            xs.append(t[0] * x + t[2] * y + t[4])
            ys.append(t[1] * x + t[3] * y + t[5])
    w = max(xs) - min(xs)
    assert abs(w - 100 * 25.4 / 96) < 100 * 25.4 / 96 * 0.03


@pytest.mark.skipif(not trace.potrace_available(), reason="potrace not installed")
def test_trace_empty_threshold_400(client, disc_png):
    # a gray-1 disc: at threshold 0 no pixel passes `<= 0`, so nothing to trace
    from PIL import Image, ImageDraw

    img = Image.new("L", (200, 200), 255)
    d = ImageDraw.Draw(img)
    d.ellipse((50, 50, 150, 150), fill=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    r = client.post(
        "/api/trace",
        params={"threshold": 0},
        files={"file": ("dim.png", buf.getvalue(), "image/png")},
    )
    assert r.status_code == 400
    assert "nothing to trace" in r.json()["detail"]


def test_trace_no_potrace_message(client, disc_png, monkeypatch):
    if trace.potrace_available():
        monkeypatch.setattr(trace.shutil, "which", lambda name: None)
    r = client.post(
        "/api/trace",
        params={"threshold": 128},
        files={"file": ("disc.png", disc_png, "image/png")},
    )
    assert r.status_code == 400
    assert "apt install potrace" in r.json()["detail"]