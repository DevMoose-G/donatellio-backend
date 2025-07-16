from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class JWTToken(BaseModel):
    access_token: str
    token_type: str
    expires_in: datetime  # access token expires in
    refresh_token: Optional[str] = None


class RequestCalculateMeshGenCost(BaseModel):
    mesh_model: str
    n_meshes: int
    quality: str
    seed: Optional[int]
    labels: List[str]
    max_polygon_count: Optional[int]


class RequestCalculateTextureGenCost(BaseModel):
    prompt: str
    texture_quality: str
    seed: int


class ItemCollection(BaseModel):
    collection_id: str
    name: str
    parent_id: Optional[str]


class CollectionResponse(BaseModel):
    collections: List[ItemCollection]


step1x_labels = {
    "symmetry": [
        "symmetric",  # have to convert this to 'x'
        "asymmetric",  # have to convert this to 'asymmetry' when inputted to model
    ],
    "geometry_type": ["sharp", "normal", "smooth"],
    "pose": ["t-pose", "a-pose"],
}


class ResponseGenerateMeshInfo(BaseModel):
    cost: int
    labels: Dict[str, List[str]]


class ResponseGenerateTextureInfo(BaseModel):
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
    seed: Optional[int]
    labels: List[str]
    max_polygon_count: Optional[int]


class RequestCreateImage(BaseModel):
    prompt: str
    n: int
    size: str
    quality: str
    image_model: str

    style_image_storage_url: Optional[str] = None


class RequestEditImage(BaseModel):
    project_id: str
    parent_image_id: str
    prompt: str
    n: int
    size: str
    quality: str
    image_model: str


class RequestCreateUser(BaseModel):
    username: str
    email: str
    password: str


class RequestLoginUser(BaseModel):
    password: str
    username: Optional[str] = None
    email: Optional[str] = None
    is_web: Optional[bool] = True


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
    image_id: str
    prompt: str
    created_at: datetime
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    parent_image_url: Optional[str] = None
    error: Optional[str] = None


class ResponseImagePromptChat(BaseModel):
    chats: List[ItemImagePromptChat]


class WSImageItem(BaseModel):
    id: str
    url: Optional[str] = None
    is_partial: bool = False


class GetImageInfo(BaseModel):
    id: str
    url: Optional[str] = None


class WSImageEditsResponse(BaseModel):
    images: List[WSImageItem]
    chats: List[ItemImagePromptChat] = []


class MeshFormat(BaseModel):
    obj_url: Optional[str] = None
    fbx_url: Optional[str] = None
    stl_url: Optional[str] = None
    blend_url: Optional[str] = None


class WSMeshItem(BaseModel):
    mesh_id: str
    parent_mesh_id: Optional[str] = None
    mesh_url: Optional[str] = None
    mesh_image_url: Optional[str] = None
    status: str
    expected_completion_date: Optional[datetime] = None
    created_at: datetime


class WSTextureItem(BaseModel):
    texture_id: str
    texture_url: Optional[str] = None
    texture_image_url: Optional[str] = None
    status: str
    expected_completion_date: Optional[datetime] = None
    created_at: datetime


class WSModelItem(BaseModel):
    image_id: str
    mesh: WSMeshItem
    texture: Optional[WSTextureItem] = None


class WSModelResponse(BaseModel):
    models: List[WSModelItem]


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


class GetAssetsResponse(BaseModel):
    assets: List[AssetDisplay]
    count: int


class GetProjectsResponse(BaseModel):
    projects: List[ProjectDisplay]
    count: int
