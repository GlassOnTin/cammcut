"""Job submission, status, cancel, and the SSE event stream."""

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..schemas import JobSettings, Project
from ..services import device
from ..services.jobrunner import JobRunner

router = APIRouter(prefix="/api", tags=["jobs"])


@router.post("/jobs", status_code=202)
def submit_job(request: Request, body: dict):
    runner: JobRunner = request.app.state.runner
    try:
        project = Project.model_validate(body["project"])
        js = JobSettings.model_validate(body.get("job") or {})
    except (KeyError, ValueError) as e:
        raise HTTPException(400, "bad request: %s" % e) from e
    if js.device == device.DEMO_DEVICE and not runner.demo_enabled:
        raise HTTPException(400, "demo mode is off — enable it in the cutter panel")
    try:
        job_id = runner.submit(project, js)
    except device.DeviceBusy as e:
        raise HTTPException(409, str(e)) from e
    except Exception as e:
        # queue full means a job slipped in between the check and the put
        raise HTTPException(409, "job queue is full: %s" % e) from e
    return {"job_id": job_id}


@router.get("/jobs/current")
def current(request: Request):
    st = request.app.state.runner.status()
    if not st:
        raise HTTPException(404, "no jobs yet")
    return st.model_dump()


@router.get("/jobs/{job_id}")
def job_status(request: Request, job_id: str):
    j = request.app.state.runner.jobs.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@router.delete("/jobs/{job_id}")
def cancel(request: Request, job_id: str | None = None):
    ok = request.app.state.runner.cancel(job_id)
    if not ok:
        raise HTTPException(409, "no running job to cancel")
    return {"cancelled": True}


@router.get("/events")
async def events(request: Request):
    bus = request.app.state.bus
    stop = request.app.state.sse_stop

    async def stream():
        idx = bus.cursor()
        yield "retry: 3000\n\n"
        while True:
            if await request.is_disconnected():
                break
            for msg in bus.since(idx):
                idx = msg[0]
                yield "data: %s\n\n" % msg[1]
            # sleep, but wake the instant the server starts shutting down —
            # a plain sleep leaves the stream running and blocks SIGTERM
            # handling until the process manager's kill timeout
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.3)
                break
            except asyncio.TimeoutError:
                pass

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )