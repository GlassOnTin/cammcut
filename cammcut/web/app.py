"""FastAPI app factory.

Run (dev):  .venv/bin/uvicorn cammcut.web.app:create_app --factory --port 8799
Run (prod): build web/ with npm, then the same command serves the built
frontend from cammcut/web/static on 0.0.0.0:8799.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..cammcut import CammcutError
from . import settings
from .pubsub import Broadcaster
from .routers import assets, devices, generate, jobs, projects, system, texttrace, tools
from .services import device
from .services.jobrunner import JobRunner

log = logging.getLogger("cammcut.web")

broadcaster = Broadcaster()

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    app.state.bus = broadcaster
    # precedence: injected sink (tests) > CAMMCUT_DRY_RUN file sink > real device
    injected = getattr(app.state, "sink", None)
    env_sink, _ = device.sink_from_env()
    sink = injected or env_sink
    # stall clearing only makes sense when jobs go to the real adapter
    app.state.runner = JobRunner(
        broadcaster, sink=sink,
        unstick=device.unstick if sink is device.real_sink else None,
    )
    log.info("cammcut web ready on %s:%s (data: %s)", settings.HOST, settings.PORT,
             settings.DATA_DIR)
    # SSE streams wait on this so a SIGTERM ends them immediately instead of
    # holding uvicorn's graceful shutdown for TimeoutStopSec (seen live).
    app.state.sse_stop = asyncio.Event()
    yield
    app.state.sse_stop.set()
    app.state.runner.claim(None)


def create_app(sink=None) -> FastAPI:
    app = FastAPI(title="cammcut", version="web", lifespan=lifespan)
    app.state.sink = sink

    app.include_router(system.router)
    app.include_router(projects.router)
    app.include_router(assets.router)
    app.include_router(generate.router)
    app.include_router(texttrace.router)
    app.include_router(tools.router)
    app.include_router(devices.router)
    app.include_router(jobs.router)

    @app.exception_handler(CammcutError)
    async def cammcut_error(request: Request, exc: CammcutError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={"detail": str(exc.errors()[:3])})

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        # Built frontend only; nothing to serve in dev (vite proxies /api).
        index = STATIC_DIR / "index.html"
        if index.exists() and not path.startswith("api"):
            return FileResponse(index)
        return JSONResponse(status_code=404, content={"detail": "not found"})

    return app


app = create_app()