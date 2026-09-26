"""Single-slot job runner for the write-only cutter transport.

Machine reality: there is no readback, so "done" means the stream was
written, never that the cut finished. Progress in bytes is real — os.write
blocks when the PL2305's on-chip buffer fills, so bytes sent tracks bytes
the machine consumed. One job at a time; a second submit while one is
queued or running raises DeviceBusy (HTTP 409 at the router).
"""

import json
import queue
import threading
import time
import uuid
from typing import Callable

from .. import settings
from ..pubsub import Broadcaster
from ..schemas import JobSettings, JobStatus, Project
from . import compose, device

TERMINAL = ("done", "cancelled", "failed")


class JobRunner:
    def __init__(self, broadcaster: Broadcaster, sink: device.Sink | None = None,
                 demo_sink: device.Sink | None = None,
                 unstick: Callable[[], str] | None = None):
        self.bus = broadcaster
        self.sink = sink or device.real_sink
        self.demo_sink = demo_sink or device.demo_sink()
        # clears a stalled PL2305 before real sends; None disables (tests)
        self.unstick_fn = unstick
        self.demo_enabled = False
        self._q: queue.Queue[str] = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self.jobs: dict[str, dict] = {}
        self.claimed_device: str | None = None
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    # ---------------------------------------------------------------- api

    def busy(self) -> bool:
        with self._lock:
            return any(j["state"] in ("queued", "running") for j in self.jobs.values())

    def submit(self, project: Project, js: JobSettings) -> str:
        if self.busy():
            raise device.DeviceBusy("a job is already queued or running")
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self.jobs[job_id] = {
                "job_id": job_id,
                "state": "queued",
                "device": None,
                "bytes_sent": 0,
                "bytes_total": 0,
                "cut_len_mm": 0.0,
                "est_seconds": 0.0,
                "started_at": None,
                "finished_at": None,
                "error": None,
                "note": None,
            }
        self._q.put((job_id, project, js))
        self._publish(job_id, "job.state")
        return job_id

    def cancel(self, job_id: str | None = None) -> bool:
        with self._lock:
            j = self._current_job(job_id)
            if not j or j["state"] not in ("queued", "running"):
                return False
        self._cancel.set()
        return True

    def status(self, job_id: str | None = None) -> JobStatus | None:
        with self._lock:
            j = self._current_job(job_id)
            return JobStatus(**j) if j else None

    def claim(self, dev: str | None) -> str | None:
        self.claimed_device = dev
        self.bus.publish("device.changed", {"claim": dev})
        return dev

    def set_demo(self, enabled: bool) -> bool:
        self.demo_enabled = enabled
        self.bus.publish("device.changed", {"demo": enabled})
        return enabled

    # ------------------------------------------------------------ internal

    def _current_job(self, job_id: str | None) -> dict | None:
        """Most recent job, or the named one."""
        if job_id and job_id in self.jobs:
            return self.jobs[job_id]
        for j in reversed(list(self.jobs.values())):
            return j
        return None

    def _publish(self, job_id: str, kind: str):
        j = self.jobs.get(job_id)
        if j:
            self.bus.publish(kind, {"job": JobStatus(**j).model_dump()})

    def _maybe_unstick(self, j: dict, device_path: str):
        """Clear a stalled PL2305 before sending. Writes into a stalled
        adapter succeed silently (the machine ignores everything), and the
        kernel logs the stall as -EPIPE bulk status, so in "auto" mode we
        clear only when the journal shows one since the last successful
        clear. Failures are reported on the job, never fatal: sending
        proceeds as before the automation existed."""
        if not self.unstick_fn or settings.UNSTICK == "off":
            return
        if settings.UNSTICK == "auto":
            try:
                stalled = device.stall_detected(device_path, self._unstick_since())
            except Exception:
                stalled = True
            if not stalled:
                return
        try:
            msg = self.unstick_fn()
        except Exception as e:
            j["note"] = str(e)
            return
        marker = settings.DATA_DIR / ".unstick-marker"
        try:
            marker.write_text(str(time.time()))
        except OSError:
            pass
        j["note"] = msg

    def _unstick_since(self) -> float:
        try:
            return float((settings.DATA_DIR / ".unstick-marker").read_text().strip())
        except (OSError, ValueError):
            return 0.0

    def _worker(self):
        while True:
            job_id, project, js = self._q.get()
            j = self.jobs[job_id]
            if self._cancel.is_set() and j["state"] == "queued":
                # cancelled before it started
                j["state"] = "cancelled"
                j["finished_at"] = time.time()
                self._publish(job_id, "job.state")
                self._cancel.clear()
                continue
            self._cancel.clear()
            try:
                j["state"] = "running"
                j["started_at"] = time.time()
                self._publish(job_id, "job.state")

                plan = compose.build_plan(project, js)
                j["bytes_total"] = len(plan.hpgl)
                j["cut_len_mm"] = plan.cut_len_mm
                j["est_seconds"] = plan.est_seconds
                if js.device == device.DEMO_DEVICE:
                    if not self.demo_enabled:
                        raise ValueError("demo mode is off")
                    dev = "demo (mock cutter)"
                    sink = self.demo_sink
                else:
                    dev_hint = device.resolve(js.device or settings.DEVICE)
                    self._maybe_unstick(j, dev_hint)
                    # re-resolve: the driver cycle can renumber /dev/usb/lpN
                    dev = device.resolve(js.device or settings.DEVICE)
                    # after a cycle, udev may not have applied the group rule
                    # to the fresh node yet — don't open into EACCES
                    device.wait_openable(dev)
                    sink = self.sink
                j["device"] = dev

                # artifact: exact bytes sent, for post-mortems
                jobs_dir = settings.subdir("jobs")
                (jobs_dir / ("%s.hpgl" % job_id)).write_text(plan.hpgl, encoding="ascii")
                (jobs_dir / ("%s.json" % job_id)).write_text(json.dumps({
                    "project": project.model_dump(),
                    "settings": js.model_dump(),
                    "device": dev,
                }))

                def on_progress(sent, _j=j, _id=job_id):
                    _j["bytes_sent"] = sent
                    self._publish(_id, "job.progress")

                sink(dev, plan.hpgl.encode("ascii"),
                     on_progress, self._cancel.is_set)
                j["state"] = "done"
            except device.CancelledError:
                j["state"] = "cancelled"
            except Exception as e:
                j["state"] = "failed"
                j["error"] = str(e)
            finally:
                j["finished_at"] = time.time()
                self._publish(job_id, "job.state")