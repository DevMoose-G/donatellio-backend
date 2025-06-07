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


Action = Union[ImageAction, MeshAction]


class RedisMessage(BaseModel):
    id: str
    action: Action


# @dataclass
# class RedisPayload:
#     project_id: str
#     function_name: str
#     type: str
#     payload: Dict[str, Any]
#     # params: list


# @dataclass
# class RedisMessage:
#     id: str
#     json: RedisPayload


# @dataclass
# class RedisReadResponse:
#     stream_key: str
#     messages: List[RedisMessage]


# @dataclass
# class ImagePayload(RedisPayload):
#     image_id: str
#     is_partial: bool


# @dataclass
# class MeshPayload(RedisPayload):
#     mesh_ids: List[str]
