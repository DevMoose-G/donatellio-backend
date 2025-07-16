from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field
from rq.job import JobStatus

# do i need to make a meshjobupdate, imagejobupdate, etc.?
# i don't think so, because job update is more about the job itself, not the action
class JobUpdate(BaseModel):
    job_id: str
    status: JobStatus | None # one of: queued, started, finished, failed
    message: Optional[str] = None
    ping_at: Optional[datetime] = Field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(seconds=15)))

class BaseAction(BaseModel):
    type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project_id: str
    function_name: str
    attempts: int = 0


class ImageAction(BaseAction):
    type: Literal["image"] = "image"
    params: Dict[str, Any]
    image_id: str
    is_partial: Optional[bool] = False
    successful: Optional[bool] = True


class MeshAction(BaseAction):
    type: Literal["mesh"] = "mesh"
    params: Dict[str, Any]
    mesh_ids: Optional[List[str]] = None


class TexturedMeshAction(BaseAction):
    type: Literal["textured_mesh"] = "textured_mesh"
    params: Dict[str, Any]
    texture_id: Optional[str] = None
    successful: Optional[bool] = True


Action = Union[ImageAction, MeshAction, TexturedMeshAction]


class RedisMessage(BaseModel):
    id: str
    action: Action