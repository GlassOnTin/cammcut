"""Project CRUD."""

from fastapi import APIRouter, HTTPException

from ..schemas import Project
from ..services import workspace

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def list_projects():
    return [m.model_dump() for m in workspace.list_projects()]


@router.post("", status_code=201)
def create_project(body: dict):
    name = str(body.get("name") or "untitled").strip() or "untitled"
    project = workspace.create(name)
    return {"project": project.model_dump(), "mtime": workspace.mtime_of(project.id)}


@router.get("/{project_id}")
def get_project(project_id: str):
    try:
        project = workspace.get(project_id)
    except KeyError:
        raise HTTPException(404, "project not found") from None
    return {"project": project.model_dump(), "mtime": workspace.mtime_of(project_id)}


@router.put("/{project_id}")
def save_project(project_id: str, project: Project, base_mtime: float | None = None):
    """Save with optimistic concurrency: pass base_mtime (the mtime the client
    loaded) and the save is rejected if the file changed since. A PUT to an
    id that does not exist yet creates the project — a client-side draft's
    first explicit save is a PUT, and drafts send base_mtime=0 so an id
    collision with an existing file is a 409, never a silent overwrite."""
    try:
        existing = workspace.get(project_id)
    except KeyError:
        existing = None
    if project.id != project_id:
        raise HTTPException(400, "document id does not match URL")
    if existing is not None:
        current = workspace.mtime_of(project_id)
        if base_mtime is not None and abs(current - base_mtime) > 1e-6:
            raise HTTPException(
                409,
                "project was saved by someone else %d s ago — reload it (open…) "
                "to pick up their changes, or overwrite by saving again"
                % max(0, int(current - base_mtime)),
            )
        project.name = existing.name if not project.name else project.name
    workspace.save(project)
    return {"saved": True, "mtime": workspace.mtime_of(project_id)}


@router.delete("/{project_id}")
def delete_project(project_id: str):
    try:
        workspace.get(project_id)
    except KeyError:
        raise HTTPException(404, "project not found") from None
    workspace.delete(project_id)
    return {"deleted": True}