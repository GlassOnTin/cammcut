"""Pydantic models: the project document and API DTOs.

The frontend mirrors this schema with zod (web/src/types.ts). Keep the two
in sync: Item is always kind "path"; shapes/text/emoji/traces are converted
at insert time so nothing downstream ever sees other element types.
"""

from typing import Literal

from pydantic import BaseModel, Field

IDENTITY = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]


class Artboard(BaseModel):
    w_mm: float = Field(gt=0, le=2000)
    h_mm: float = Field(gt=0, le=30000)


class Item(BaseModel):
    id: str
    kind: Literal["path"] = "path"
    d: str
    transform: list[float] = Field(default_factory=lambda: list(IDENTITY))
    fill_rule: Literal["nonzero", "evenodd"] | None = None


class Layer(BaseModel):
    id: str
    name: str
    visible: bool = True
    locked: bool = False
    items: list[Item] = Field(default_factory=list)


class Project(BaseModel):
    id: str
    name: str
    version: int = 1
    artboard: Artboard = Artboard(w_mm=584.0, h_mm=300.0)
    layers: list[Layer] = Field(default_factory=list)


class ProjectMeta(BaseModel):
    id: str
    name: str
    mtime: float


class JobSettings(BaseModel):
    speed: int = Field(default=5, ge=1, le=30)  # cm/s -> VS<n>;
    x_mm: float = 0.0
    y_mm: float = 0.0
    scale: float = Field(default=1.0, gt=0)
    mirror: bool = False
    origin: Literal["content", "artboard"] = "content"
    media_w_mm: float = Field(default=584.0, gt=0)
    media_h_mm: float = Field(default=5000.0, gt=0)
    device: str | None = None


class Bounds(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float


class Violation(BaseModel):
    axis: Literal["x", "y"]
    detail: str


class Preview(BaseModel):
    toolpath_svg: str
    bounds: Bounds | None
    violations: list[Violation] = []
    cut_len_mm: float
    travel_len_mm: float
    est_seconds: float
    byte_len: int


class JobStatus(BaseModel):
    job_id: str
    state: Literal["queued", "running", "done", "cancelled", "failed"]
    device: str | None
    bytes_sent: int
    bytes_total: int
    cut_len_mm: float
    est_seconds: float
    started_at: float | None
    finished_at: float | None
    error: str | None = None
    note: str | None = None  # e.g. "adapter stall cleared" before the send


class DeviceInfo(BaseModel):
    path: str
    vid: str
    pid: str
    exists: bool
    writable: bool