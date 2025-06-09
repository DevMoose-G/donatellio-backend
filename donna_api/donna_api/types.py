from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class JWTToken(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: datetime  # access token expires in


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


step1x_labels = {
    "symmetry": [
        "symmetric",  # have to convert this to 'x'
        "asymmetric",  # have to convert this to 'asymmetry' when inputted to model
    ],
    "edge_type": ["sharp", "normal", "smooth"],
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
    is_partial: bool = False


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
    image_id: str
    url: Optional[str]
    other_formats: MeshFormat
    texture_id: Optional[str] = None

    textured_image_url: Optional[str] = None
    mesh_image_url: Optional[str] = None
    status: str


class WSMeshResponse(BaseModel):
    meshes: List[WSMeshItem]


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
    url: str
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
