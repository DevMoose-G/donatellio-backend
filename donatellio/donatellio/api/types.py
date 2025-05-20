from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

class RequestCreateMesh(BaseModel):
    project_id: str
    image_id: str

class RequestCreateImage(BaseModel):
    prompt: str
    n: int
    size: str
    quality: str

class RequestEditImage(BaseModel):
    project_id: str
    original_image_id: str
    prompt: str
    n: int
    size: str
    quality: str

class RequestCreateUser(BaseModel):
    username: str
    email: str
    password: str

class RequestLoginUser(BaseModel):
    password: str
    username: Optional[str] = None
    email: Optional[str] = None

class RequestGetElaboratingQuestions(BaseModel):
    project_id: str
    prompt: str
    image_id: Optional[str] = None


class ItemImagePromptChat(BaseModel):
    prompt: str
    created_at: datetime
    original_image_id: Optional[str] = None

class ResponseImagePromptChat(BaseModel):
    chats: List[ItemImagePromptChat]

class WSImageItem(BaseModel):
    id: str
    url: str

class WSImageEditsResponse(BaseModel):
    images: List[WSImageItem]
    chats: List[ItemImagePromptChat] = []

class WSMeshItem(BaseModel):
    id: str
    url: str

class WSMeshResponse(BaseModel):
    meshes: List[WSMeshItem]

class AssetDisplay(BaseModel):
    project_id: str
    url: str
    user_name: str

class GetAssetsResponse(BaseModel):
    assets: List[AssetDisplay]
    count: int

class GetProjectsResponse(BaseModel):
    projects: List[AssetDisplay]
    count: int