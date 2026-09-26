"""Web API tests: FastAPI TestClient + file sink (no device needed)."""

import asyncio
import os
import tempfile
import threading
import time

os.environ["CAMMCUT_DATA_DIR"] = tempfile.mkdtemp(prefix="cammcut-test-")

import pytest
from fastapi.testclient import TestClient

from cammcut.web import settings
from cammcut.web.app import create_app
from cammcut.web.services import device

SQUARE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm">'
    '<rect x="0" y="0" width="10" height="10"/></svg>'
)

NS = 'xmlns="http://www.w3.org/2000/svg"'


def square_project(client, size_mm=10.0):
    r = client.post("/api/projects", json={"name": "square"})
    pid = r.json()["project"]["id"]
    return {
        "id": pid,
        "name": "square",
        "version": 1,
        "artboard": {"w_mm": 584.0, "h_mm": 300.0},
        "layers": [{
            "id": "l1", "name": "L", "visible": True, "locked": False,
            "items": [{
                "id": "i1", "kind": "path",
                "d": "M 0 0 L %f 0 L %f %f L 0 %f Z" % (size_mm, size_mm, size_mm, size_mm),
                "transform": [1, 0, 0, 1, 0, 0],
            }],
        }],
    }


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # jobs without an explicit device resolve settings.DEVICE; point it at a
    # node that always exists so the suite does not need the cutter attached
    monkeypatch.setattr(settings, "DEVICE", "/dev/null")
    app = create_app(sink=device.file_sink(tmp_path / "job-output.hpgl"))
    with TestClient(app) as c:
        c.tmp_path = tmp_path
        yield c


def wait_state(client, states, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            st = client.get("/api/jobs/current").json()
        except Exception:
            st = None
        if st and st["state"] in states:
            return st
        time.sleep(0.02)
    raise AssertionError("job did not reach %s (last: %s)" % (states, st))


# ------------------------------------------------------------------ basics

def test_system_info(client):
    r = client.get("/api/system/info")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body
    assert isinstance(body["devices"], list)


def test_project_roundtrip(client):
    r = client.post("/api/projects", json={"name": "rt"})
    assert r.status_code == 201
    body = r.json()
    pid = body["project"]["id"]
    assert isinstance(body["mtime"], float)
    doc = square_project(client)
    doc["id"] = pid
    r = client.put("/api/projects/%s" % pid, json=doc)
    assert r.status_code == 200
    r = client.get("/api/projects/%s" % pid)
    assert r.json()["project"]["layers"][0]["items"][0]["id"] == "i1"
    r = client.get("/api/projects")
    assert any(p["id"] == pid for p in r.json())


def test_save_conflict_rejected(client):
    r = client.post("/api/projects", json={"name": "conflict"})
    pid = r.json()["project"]["id"]
    mtime = r.json()["mtime"]
    doc = square_project(client)
    doc["id"] = pid
    # a save from another client advances the file's mtime
    time.sleep(0.01)
    r = client.put("/api/projects/%s" % pid, json=doc)
    assert r.status_code == 200
    new_mtime = r.json()["mtime"]
    # the first client saves again with its stale mtime -> 409
    r = client.put("/api/projects/%s?base_mtime=%f" % (pid, mtime), json=doc)
    assert r.status_code == 409
    assert "saved by someone else" in r.json()["detail"]
    # saving with the up-to-date mtime works
    r = client.put("/api/projects/%s?base_mtime=%f" % (pid, new_mtime), json=doc)
    assert r.status_code == 200
    # no base_mtime at all (old clients, curl) is never rejected
    r = client.put("/api/projects/%s" % pid, json=doc)
    assert r.status_code == 200


def test_save_creates_missing_project(client):
    # a client-side draft's first explicit save is a PUT with its own id
    doc = square_project(client)
    doc["id"] = "draft1a2b3c"
    r = client.put("/api/projects/draft1a2b3c", json=doc)
    assert r.status_code == 200, r.text
    assert r.json()["mtime"] > 0
    r = client.get("/api/projects/draft1a2b3c")
    assert r.status_code == 200
    assert r.json()["project"]["name"] == "square"


def test_save_draft_base_mtime_zero_rejects_id_collision(client):
    # base_mtime=0 (what drafts send) must never silently overwrite an
    # existing project that happens to share the id
    r = client.post("/api/projects", json={"name": "taken"})
    pid = r.json()["project"]["id"]
    doc = square_project(client)
    doc["id"] = pid
    r = client.put("/api/projects/%s?base_mtime=0" % pid, json=doc)
    assert r.status_code == 409


def test_save_rejects_bad_project_id(client):
    # ids become file names; anything outside [a-z0-9] is refused (this also
    # rules out ../ traversal, which the same regex guards)
    doc = square_project(client)
    doc["id"] = "bad_id_99"
    r = client.put("/api/projects/bad_id_99", json=doc)
    assert r.status_code == 400
    assert "invalid project id" in r.json()["detail"]
    escaped = (settings.DATA_DIR / "projects").parent / "bad_id_99.json"
    assert not escaped.exists()


def test_import_svg(client):
    r = client.post("/api/import/svg",
                    files={"file": ("sq.svg", SQUARE_SVG.encode(), "image/svg+xml")})
    assert r.status_code == 200
    body = r.json()
    assert body["width_mm"] == pytest.approx(10.0, abs=0.01)
    assert len(body["items"]) == 1
    # px-space d scaled to mm via the transform
    t = body["items"][0]["transform"]
    assert t[0] == pytest.approx(25.4 / 96.0)


# ----------------------------------------------------------------- preview

def test_preview_bounds_and_violations(client):
    doc = square_project(client)
    r = client.post("/api/compose/preview", json={
        "project": doc,
        "settings_body": {"media_w_mm": 584.0, "media_h_mm": 300.0},
    })
    assert r.status_code == 200
    p = r.json()
    assert p["bounds"]["max_x"] == pytest.approx(10.0, abs=0.01)
    assert p["violations"] == []
    assert p["cut_len_mm"] == pytest.approx(40.0, abs=0.1)

    r = client.post("/api/compose/preview", json={
        "project": doc,
        "settings_body": {"media_w_mm": 5.0, "media_h_mm": 300.0, "x_mm": 0.0},
    })
    v = r.json()["violations"]
    assert len(v) == 1 and v[0]["axis"] == "x"

    r = client.post("/api/compose/preview", json={
        "project": doc,
        "settings_body": {"x_mm": 580.0, "media_w_mm": 584.0, "media_h_mm": 300.0},
    })
    v = r.json()["violations"]
    assert len(v) == 1 and v[0]["axis"] == "x"


def test_preview_empty_document(client):
    doc = square_project(client)
    doc["layers"] = []
    r = client.post("/api/compose/preview", json={"project": doc})
    assert r.status_code == 400


# -------------------------------------------------------------------- jobs

def test_job_run_and_artifact(client, tmp_path):
    doc = square_project(client)
    r = client.post("/api/jobs", json={"project": doc, "job": {"speed": 5}})
    assert r.status_code == 202
    st = wait_state(client, ("done", "cancelled", "failed"))
    assert st["state"] == "done", st
    assert st["bytes_sent"] == st["bytes_total"]
    out = tmp_path / "job-output.hpgl"
    assert out.exists() and out.read_text().startswith("IN;VS5;")


def test_job_busy_409(client):
    gate = threading.Event()
    calls = {"n": 0}

    def blocking_sink(dev, data, on_progress, is_cancelled):
        calls["n"] += 1
        on_progress(len(data))
        gate.wait(10)
        with open(dev + ".out", "wb") as f:
            f.write(data)

    client.app.state.runner.sink = blocking_sink
    doc = square_project(client)
    r1 = client.post("/api/jobs", json={"project": doc})
    assert r1.status_code == 202
    wait_state(client, ("running",))
    r2 = client.post("/api/jobs", json={"project": doc})
    assert r2.status_code == 409
    gate.set()
    wait_state(client, ("done", "failed"))
    assert calls["n"] == 1


def test_job_cancel(client, tmp_path):
    out = tmp_path / "cancel.hpgl"

    def slow_sink(dev, data, on_progress, is_cancelled):
        # write a chunk at a time; honour cancel
        with open(out, "wb") as f:
            for i in range(0, len(data), 64):
                if is_cancelled():
                    raise device.CancelledError()
                f.write(data[i:i + 64])
                f.flush()
                on_progress(i + 64)
                time.sleep(0.05)

    client.app.state.runner.sink = slow_sink
    doc = square_project(client)
    # make it long enough to still be running when we cancel
    for layer in doc["layers"]:
        for item in layer["items"]:
            item["d"] = " ".join(
                "M %d %d L %d %d" % (k, k % 7, k + 1, (k + 1) % 7) for k in range(200)
            )
    r = client.post("/api/jobs", json={"project": doc})
    assert r.status_code == 202
    wait_state(client, ("running",))
    r = client.delete("/api/jobs/current")
    assert r.status_code == 200
    st = wait_state(client, ("cancelled",))
    assert st["state"] == "cancelled"


def test_sink_precedence_injected_wins_over_dry_run(tmp_path, monkeypatch):
    """Regression: the injected (file) sink must beat CAMMCUT_DRY_RUN.

    Previously env_sink shadowed the injected sink and test/dry-run jobs went
    to the real device (/dev/usb/lp*).
    """
    monkeypatch.setenv("CAMMCUT_DRY_RUN", "1")
    monkeypatch.setattr(settings, "DEVICE", "/dev/null")  # no hardware needed
    app = create_app(sink=device.file_sink(tmp_path / "injected.hpgl"))
    with TestClient(app) as client:
        doc = square_project(client)
        r = client.post("/api/jobs", json={"project": doc})
        assert r.status_code == 202
        st = wait_state(client, ("done", "failed"))
        assert st["state"] == "done", st
        out = tmp_path / "injected.hpgl"
        assert out.exists()
        assert out.read_text().startswith("IN;VS5;")
        # the dry-run file must not exist: this data dir is fresh for this
        # test run, so its presence would mean the env sink ran the job
        dry = os.path.join(os.environ["CAMMCUT_DATA_DIR"], "jobs", "dry-run.hpgl")
        assert not os.path.exists(dry)


def test_job_no_device_fails_cleanly(client):
    client.app.state.runner.sink = device.real_sink
    client.app.state.runner.jobs.clear()
    doc = square_project(client)
    r = client.post("/api/jobs", json={"project": doc, "job": {"device": "/dev/does-not-exist"}})
    assert r.status_code == 202
    st = wait_state(client, ("failed",))
    assert "does not exist" in st["error"]

# --- TLS ----------------------------------------------------------------------

def test_tls_san_entries_cover_hostname_and_ips():
    from cammcut.web import tls
    entries = tls.san_entries()
    assert any(e.startswith("DNS:localhost") for e in entries)
    assert "IP:127.0.0.1" in entries


def test_tls_ensure_cert_generates_loadable_pair(tmp_path):
    import ssl

    from cammcut.web import tls
    cert, key = tls.ensure_cert(tmp_path / "c.pem", tmp_path / "k.pem")
    assert cert is not None and key is not None
    assert cert.exists() and key.exists()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)  # raises if the pair is unusable
    # second call is a no-op (files kept)
    mtime = cert.stat().st_mtime_ns
    cert2, _ = tls.ensure_cert(tmp_path / "c.pem", tmp_path / "k.pem")
    assert cert2 == cert and cert2.stat().st_mtime_ns == mtime


def test_tls_cert_expiry_far_future(tmp_path):
    import datetime

    from cammcut.web import tls
    cert, _ = tls.ensure_cert(tmp_path / "c.pem", tmp_path / "k.pem")
    exp = tls.not_after(cert)
    assert exp is not None
    assert exp > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3600)


# ------------------------------------------------- rename & delete projects

def test_rename_and_delete_project(client):
    r = client.post("/api/projects", json={"name": "old name"})
    pid = r.json()["project"]["id"]
    mtime = r.json()["mtime"]
    # PUT with a new name renames; items are not needed for that
    doc = square_project(client)
    doc["id"] = pid
    doc["name"] = "new name"
    r = client.put("/api/projects/%s?base_mtime=%f" % (pid, mtime), json=doc)
    assert r.status_code == 200
    assert client.get("/api/projects/%s" % pid).json()["project"]["name"] == "new name"
    # delete removes it from the list
    assert client.delete("/api/projects/%s" % pid).json()["deleted"] is True
    assert client.get("/api/projects/%s" % pid).status_code == 404
    assert all(p["id"] != pid for p in client.get("/api/projects").json())


# ------------------------------------------------- SSE shutdown behaviour

class _FakeRequest:
    def __init__(self, app):
        self.app = app

    async def is_disconnected(self):
        return False


def test_lifespan_owns_sse_stop_event():
    # create + set the shutdown signal the SSE stream waits on
    app = create_app()
    with TestClient(app):
        assert isinstance(app.state.sse_stop, asyncio.Event)
        assert not app.state.sse_stop.is_set()
    assert app.state.sse_stop.is_set()


@pytest.mark.anyio
async def test_events_stream_ends_on_shutdown_event():
    """An open SSE stream must not hold server shutdown until the 90 s
    SIGKILL (observed live: systemd restart stalled stop-sigterm)."""
    from cammcut.web.app import broadcaster
    from cammcut.web.routers import jobs as jobs_router

    app = create_app()
    app.state.bus = broadcaster
    app.state.sse_stop = asyncio.Event()
    resp = await jobs_router.events(_FakeRequest(app))
    agen = resp.body_iterator
    assert "retry" in await agen.__anext__()
    app.state.sse_stop.set()
    t0 = time.monotonic()
    with pytest.raises(StopAsyncIteration):
        while True:
            await agen.__anext__()
    # pre-fix the loop never returns; a 2 s bound keeps the suite finite
    assert time.monotonic() - t0 < 2.0
