from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ItemImagePromptChat(BaseModel):
    image_id: str
    prompt: str
    created_at: datetime
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    parent_image_url: Optional[str] = None
    parent_image_id: Optional[str] = None
    error: Optional[str] = None


class ResponseImagePromptChat(BaseModel):
    chats: List[ItemImagePromptChat]
    
class AssetDisplay(BaseModel):
    project_id: str
    project_name: str
    url: str
    user_name: str

    textured_image_url: Optional[str] = None
    mesh_image_url: Optional[str] = None


class ProjectDisplay(BaseModel):
    project_id: str
    project_name: str
    url: Optional[str] = None
    user_name: str
    current_state: str

    textured_image_url: Optional[str] = None
    mesh_image_url: Optional[str] = None