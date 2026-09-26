"""Demo mode: the mock cutter pseudo-device, end to end through the API."""

import os
import tempfile
import time

os.environ["CAMMCUT_DATA_DIR"] = tempfile.mkdtemp(prefix="cammcut-test-")

import pytest
from fastapi.testclient import TestClient

from cammcut.web.app import create_app
from cammcut.web.services.device import file_sink


@pytest.fixture()
def client(tmp_path):
    app = create_app(sink=file_sink(tmp_path / "job-output.hpgl"))
    with TestClient(app) as c:
        yield c


def square_project(client):
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
                "d": "M 0 0 L 10 0 L 10 10 L 0 10 Z",
                "transform": [1, 0, 0, 1, 0, 0],
            }],
        }],
    }


def wait_state(client, states, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get("/api/jobs/current").json()
        if st and st["state"] in states:
            return st
        time.sleep(0.05)
    return None


def test_demo_off_by_default(client):
    info = client.get("/api/system/info").json()
    assert info["demo"] is False
    assert "demo" not in [d["path"] for d in info["devices"]]


def test_demo_toggle_lists_pseudo_device(client):
    r = client.post("/api/devices/demo", json={"enabled": True})
    assert r.status_code == 200
    assert r.json() == {"demo": True}
    info = client.get("/api/system/info").json()
    assert info["demo"] is True
    assert "demo" in [d["path"] for d in info["devices"]]
    # and back off
    client.post("/api/devices/demo", json={"enabled": False})
    info = client.get("/api/system/info").json()
    assert "demo" not in [d["path"] for d in info["devices"]]


def test_demo_job_rejected_when_off(client):
    project = square_project(client)
    r = client.post("/api/jobs", json={
        "project": project, "job": {"device": "demo"},
    })
    assert r.status_code == 400
    assert "demo mode is off" in r.json()["detail"]


def test_demo_job_runs_to_done(client):
    client.post("/api/devices/demo", json={"enabled": True})
    project = square_project(client)
    r = client.post("/api/jobs", json={
        "project": project, "job": {"device": "demo"},
    })
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    st = wait_state(client, {"done"})
    assert st is not None, "demo job never finished"
    assert st["job_id"] == job_id
    assert st["device"].startswith("demo")
    assert st["bytes_total"] > 0
    assert st["bytes_sent"] == st["bytes_total"]
    # the demo job paced in real time: a ~200-byte stream takes >= 2 s
    assert st["finished_at"] - st["started_at"] >= 1.5
    # artifact saved like a real job, inspectable afterwards
    art = client.get("/api/jobs/%s" % job_id).json()
    assert art["state"] == "done"


def test_demo_cancel_stops_send(client):
    client.post("/api/devices/demo", json={"enabled": True})
    project = square_project(client)
    r = client.post("/api/jobs", json={
        "project": project, "job": {"device": "demo"},
    })
    assert r.status_code == 202
    # cancel while the paced send is still going
    time.sleep(0.3)
    r = client.delete("/api/jobs/current")
    assert r.status_code == 200
    st = wait_state(client, {"cancelled"})
    assert st is not None, "demo job never cancelled"
    assert st["bytes_sent"] < st["bytes_total"]


def test_demo_claim_allowed_when_enabled(client):
    r = client.post("/api/devices/claim", json={"path": "demo"})
    assert r.status_code == 400  # demo off -> not a listed device
    client.post("/api/devices/demo", json={"enabled": True})
    r = client.post("/api/devices/claim", json={"path": "demo"})
    assert r.status_code == 200
    r = client.post("/api/devices/claim", json={"path": "/dev/usb/lp0"})
    assert r.status_code == 400  # real path still validated