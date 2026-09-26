"""Device discovery + logical claim."""

from fastapi import APIRouter, HTTPException, Request

from ..schemas import DeviceInfo
from ..services import device

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("")
def list_all(request: Request) -> list[DeviceInfo]:
    runner = request.app.state.runner
    return device.list_devices(include_demo=runner.demo_enabled)


@router.post("/demo")
def set_demo(request: Request, body: dict):
    """Demo mode: jobs sent to the `demo` pseudo-device run against a mock
    cutter (paced progress, no hardware)."""
    runner = request.app.state.runner
    runner.set_demo(bool(body.get("enabled")))
    return {"demo": runner.demo_enabled}


@router.post("/claim")
def claim(request: Request, body: dict):
    runner = request.app.state.runner
    if runner.busy():
        raise HTTPException(409, "cannot change claim while a job is queued or running")
    dev = body.get("path")
    if dev:
        paths = [d.path for d in device.list_devices(include_demo=runner.demo_enabled)]
        if dev not in paths:
            raise HTTPException(400, "not a PL2305 usblp device: %s" % dev)
        if dev != device.DEMO_DEVICE and not device.resolve(dev):
            raise HTTPException(400, "device not usable: %s" % dev)
    runner.claim(dev)
    return {"claim": dev}


@router.delete("/claim")
def unclaim(request: Request):
    request.app.state.runner.claim(None)
    return {"claim": None}