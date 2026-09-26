"""System info endpoint."""

import shutil
import sys

from fastapi import APIRouter, Request

from ... import __version__
from ...cammcut import _node_vid_pid, find_devices
from .. import settings
from ..schemas import DeviceInfo
from ..services import device

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/info")
def info(request: Request):
    runner = request.app.state.runner
    devices = [
        DeviceInfo(
            path=node,
            vid=_node_vid_pid(node)[0] or "",
            pid=_node_vid_pid(node)[1] or "",
            exists=True,
            writable=_writable(node),
        )
        for node in find_devices()
    ]
    if runner.demo_enabled:
        devices.append(
            DeviceInfo(path=device.DEMO_DEVICE, vid="", pid="", exists=True, writable=True)
        )
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "data_dir": str(settings.DATA_DIR),
        "potrace": shutil.which("potrace") is not None,
        "demo": runner.demo_enabled,
        "devices": [d.model_dump() for d in devices],
    }


def _writable(path: str) -> bool:
    import os

    return os.access(path, os.W_OK)