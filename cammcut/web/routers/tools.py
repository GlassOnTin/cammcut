"""Tool endpoints: compose preview and the document tidy tools."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..schemas import Item, JobSettings, Project
from ..services import compose, svg_tools

router = APIRouter(prefix="/api", tags=["tools"])


@router.post("/compose/preview")
def compose_preview(project: Project, settings_body: JobSettings | None = None):
    s = settings_body or JobSettings()
    try:
        return compose.build_preview(project, s).model_dump()
    except Exception as e:
        raise HTTPException(400, str(e)) from e


class TidyRequest(BaseModel):
    items: list[Item]
    ops: list[dict] = Field(default_factory=list)  # [{op, params?}]


@router.post("/tidy/check")
def tidy_check(req: TidyRequest):
    try:
        return svg_tools.check_items(req.items)
    except svg_tools.TidyError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/tidy")
def tidy(req: TidyRequest):
    items = req.items
    report = []
    try:
        for entry in req.ops:
            op = entry.get("op", "")
            params = entry.get("params") or {}
            items, changed = svg_tools.run_op(op, items, params)
            report.append({"op": op, "changed": changed})
    except svg_tools.TidyError as e:
        raise HTTPException(400, str(e)) from e
    return {"items": items, "report": report}