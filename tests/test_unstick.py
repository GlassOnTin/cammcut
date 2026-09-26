"""Unstick-before-job: stall detection from the kernel log + automatic
adapter cycle at the start of real-device jobs."""

import os
import tempfile
import time

os.environ["CAMMCUT_DATA_DIR"] = tempfile.mkdtemp(prefix="cammcut-unstick-")

import pytest

from cammcut.web import settings
from cammcut.web.pubsub import Broadcaster
from cammcut.web.schemas import JobSettings, Project
from cammcut.web.services import device
from cammcut.web.services.jobrunner import JobRunner


def square_project() -> dict:
    return {
        "id": "rt",
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


def wait_state(runner, job_id, states, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = runner.status(job_id)
        if st and st.state in states:
            return st
        time.sleep(0.02)
    raise AssertionError("job did not reach %s (last: %s)" % (states, st))


@pytest.fixture()
def runner(tmp_path):
    return JobRunner(Broadcaster(), sink=device.file_sink(tmp_path / "out.hpgl"))


@pytest.fixture()
def recording_sink():
    """Sink that records the device it was called with."""
    calls = []

    def sink(dev, data, on_progress, is_cancelled):
        calls.append(("send", dev))
        on_progress(len(data))

    return sink, calls


def test_usblp_kernel_name():
    assert device._usblp_kernel_name("/dev/usb/lp7") == "usblp7"
    assert device._usblp_kernel_name("/dev/null") is None


def test_stall_detected_defaults_true_when_undetectable():
    # an unrecognised node can't be matched against the journal -> assume
    # stalled, so the safe default is to cycle the adapter
    assert device.stall_detected("/dev/null", 0.0) is True


def test_always_mode_unsticks_before_send(runner, recording_sink, monkeypatch):
    monkeypatch.setattr(settings, "UNSTICK", "always")
    sink, calls = recording_sink

    def fake_unstick():
        calls.append(("unstick",))
        return "cycled 5-2.2.3:1.0 — endpoint stall cleared"

    runner.sink = sink
    runner.unstick_fn = fake_unstick
    jid = runner.submit(Project.model_validate(square_project()),
                        JobSettings(device="/dev/null"))
    st = wait_state(runner, jid, ("done",))
    assert calls == [("unstick",), ("send", "/dev/null")]
    assert st.note is not None and "cycled" in st.note


def test_unstick_failure_sets_note_but_job_still_runs(runner, recording_sink, monkeypatch):
    monkeypatch.setattr(settings, "UNSTICK", "always")
    sink, calls = recording_sink

    def fake_unstick():
        raise RuntimeError("sudo: a password is required")

    runner.sink = sink
    runner.unstick_fn = fake_unstick
    jid = runner.submit(Project.model_validate(square_project()),
                        JobSettings(device="/dev/null"))
    st = wait_state(runner, jid, ("done",))
    assert calls == [("send", "/dev/null")]
    assert st.note is not None and "password is required" in st.note


def test_auto_mode_skips_unstick_when_no_stall(runner, recording_sink, monkeypatch):
    monkeypatch.setattr(settings, "UNSTICK", "auto")
    sink, calls = recording_sink
    monkeypatch.setattr(device, "stall_detected", lambda *a, **k: False)
    called = []

    def fake_unstick():
        called.append(True)
        return "cycled"

    runner.sink = sink
    runner.unstick_fn = fake_unstick
    jid = runner.submit(Project.model_validate(square_project()),
                        JobSettings(device="/dev/null"))
    wait_state(runner, jid, ("done",))
    assert calls == [("send", "/dev/null")]
    assert called == []
    assert runner.status(jid).note is None


def test_auto_mode_unsticks_when_stall_detected(runner, recording_sink, monkeypatch):
    monkeypatch.setattr(settings, "UNSTICK", "auto")
    sink, calls = recording_sink
    monkeypatch.setattr(device, "stall_detected", lambda *a, **k: True)

    def fake_unstick():
        calls.append(("unstick",))
        return "cycled 5-2.2.3:1.0"

    runner.sink = sink
    runner.unstick_fn = fake_unstick
    jid = runner.submit(Project.model_validate(square_project()),
                        JobSettings(device="/dev/null"))
    st = wait_state(runner, jid, ("done",))
    assert calls == [("unstick",), ("send", "/dev/null")]
    assert "cycled" in st.note


def test_off_mode_never_unsticks(runner, recording_sink, monkeypatch):
    monkeypatch.setattr(settings, "UNSTICK", "off")
    sink, calls = recording_sink
    runner.sink = sink
    runner.unstick_fn = lambda: calls.append(("unstick",))
    jid = runner.submit(Project.model_validate(square_project()),
                        JobSettings(device="/dev/null"))
    wait_state(runner, jid, ("done",))
    assert calls == [("send", "/dev/null")]


def test_demo_job_never_unsticks(runner, monkeypatch):
    monkeypatch.setattr(settings, "UNSTICK", "always")
    runner.demo_enabled = True
    called = []
    runner.unstick_fn = lambda: called.append(1)
    jid = runner.submit(Project.model_validate(square_project()),
                        JobSettings(device=device.DEMO_DEVICE))
    st = wait_state(runner, jid, ("done",))
    assert called == []
    assert st.note is None


def test_job_status_schema_has_note():
    from cammcut.web.schemas import JobStatus
    assert "note" in JobStatus.model_fields

# --- stall_detected journalctl exit codes -----------------------------------

def test_stall_detected_no_match_is_not_a_stall(monkeypatch):
    # journalctl exits 1 when the grep matches nothing: a confident "no
    # stall". Treating it as "undetectable" cycled the adapter on every job.
    from types import SimpleNamespace
    monkeypatch.setattr(device.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=1, stdout=""))
    assert device.stall_detected("/dev/usb/lp7", 0.0) is False


def test_stall_detected_match_is_a_stall(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(device.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout="Sep 06 ... -32\n"))
    assert device.stall_detected("/dev/usb/lp7", 0.0) is True


def test_stall_detected_other_error_falls_back_to_stalled(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(device.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=2, stdout=""))
    assert device.stall_detected("/dev/usb/lp7", 0.0) is True


# --- wait_openable (udev rule race after a driver cycle) ---------------------

def test_wait_openable_returns_for_openable_node(tmp_path):
    f = tmp_path / "lp0"
    f.write_text("")
    device.wait_openable(str(f), timeout=1.0)  # must not raise


def test_wait_openable_retries_through_eacces(monkeypatch, tmp_path):
    f = tmp_path / "lp0"
    f.write_text("")
    real_open = device.os.open
    attempts = []

    def flaky(path, flags):
        attempts.append(path)
        if len(attempts) < 3:
            raise PermissionError(13, "udev has not caught up yet")
        return real_open(path, flags)

    monkeypatch.setattr(device.os, "open", flaky)
    device.wait_openable(str(f), timeout=5.0)
    assert len(attempts) == 3


def test_wait_openable_raises_after_timeout(monkeypatch, tmp_path):
    def always(path, flags):
        raise PermissionError(13, "denied")

    monkeypatch.setattr(device.os, "open", always)
    with pytest.raises(PermissionError):
        device.wait_openable(str(tmp_path / "lp0"), timeout=0.0)
