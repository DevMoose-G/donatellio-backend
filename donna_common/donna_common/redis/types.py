from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class BaseAction(BaseModel):
    type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project_id: str
    function_name: str


class ImageAction(BaseAction):
    type: Literal["image"] = "image"
    params: Dict[str, Any]
    image_id: Optional[str] = None
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
