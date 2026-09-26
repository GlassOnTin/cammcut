"""Project persistence: JSON files, atomic writes."""

import json
import os
import re
import time
import uuid

from ...cammcut import CammcutError
from .. import settings
from ..schemas import Project, ProjectMeta

# ids become file names; both the server (uuid hex) and the client (base36
# drafts) produce lowercase alphanumeric ids
_ID_RE = re.compile(r"[a-z0-9]{1,32}$")


def _path(project_id: str):
    return settings.subdir("projects") / ("%s.json" % project_id)


def create(name: str) -> Project:
    project = Project(id=uuid.uuid4().hex[:12], name=name)
    save(project)
    return project


def save(project: Project):
    # the id lands in a file path: no traversal (a PUT with a crafted id
    # would otherwise write outside data/projects)
    if not _ID_RE.fullmatch(project.id):
        raise CammcutError("invalid project id %r" % project.id)
    p = _path(project.id)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(project.model_dump_json(), encoding="utf-8")
    os.replace(tmp, p)


def get(project_id: str) -> Project:
    p = _path(project_id)
    if not p.exists():
        raise KeyError(project_id)
    return Project.model_validate_json(p.read_text(encoding="utf-8"))


def list_projects() -> list[ProjectMeta]:
    metas = []
    for p in settings.subdir("projects").glob("*.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            metas.append(
                ProjectMeta(
                    id=doc["id"], name=doc.get("name", doc["id"]), mtime=p.stat().st_mtime
                )
            )
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    metas.sort(key=lambda m: -m.mtime)
    return metas


def delete(project_id: str):
    p = _path(project_id)
    if p.exists():
        p.unlink()


def mtime_of(project_id: str) -> float:
    p = _path(project_id)
    return p.stat().st_mtime if p.exists() else 0.0


def now() -> float:
    return time.time()