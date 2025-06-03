from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

class BaseResponse(BaseModel):
    success: bool
    error_msg: Optional[str] = None
    
class JWTToken(BaseResponse):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: datetime # access token expires in

class RequestCalculateMeshGenCost(BaseModel):
    mesh_model: str
    n_meshes: int
    quality: str
    seed: int
    labels: List[str]
    max_polygon_count: Optional[int]
    
class RequestCalculateTextureGenCost(BaseModel):
    prompt: str
    texture_quality: str
    seed: int

class ResponseCalculateMeshGenCost(BaseModel):
    cost: int

class RequestCreateTexture(BaseModel):
    project_id: str
    image_id: str
    mesh_id: str
    prompt: str
    texture_quality: str
    seed: int

class RequestCreateMesh(BaseModel):
    project_id: str
    image_id: str
    mesh_model: str
    n_meshes: int
    quality: str
    seed: int
    labels: List[str]
    max_polygon_count: Optional[int]

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
    prompt: str
    project_id: Optional[str] = None
    image_id: Optional[str] = None

class RequestCheckElaboratingQuestions(BaseModel):
    prompt: str
    project_id: Optional[str] = None
    image_id: Optional[str] = None
    elaborating_questions: List[str]


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
    mesh_id: str
    image_id: str
    url: str
    texture_id: Optional[str] = None

class WSMeshResponse(BaseModel):
    meshes: List[WSMeshItem]

class AssetDisplay(BaseModel):
    project_id: str
    url: str
    user_name: str

class ProjectDisplay(BaseModel):
    project_id: str
    url: str
    user_name: str
    current_state: str

class GetAssetsResponse(BaseModel):
    assets: List[AssetDisplay]
    count: int

class GetProjectsResponse(BaseModel):
    projects: List[ProjectDisplay]
    count: int