from datetime import datetime
from typing import Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.common.models import GetMeshInfo, get_mesh_info
from donna_api.types import (
    RequestCalculateMeshGenCost,
    RequestCalculateTextureGenCost,
    RequestCreateMesh,
    RequestCreateTexture,
    ResponseGenerateMeshInfo,
    ResponseGenerateTextureInfo,
    step1x_labels,
)
from donna_api.utils import (
    calculate_mesh_gen_cost,
    calculate_texture_gen_cost,
    regen_mesh_cost,
)
from donna_common.orm import (
    ImageDAL,
    ProjectDAL,
    UserDAL,
    get_image_dal,
    get_project_dal,
    get_user_dal,
)
from donna_common.orm.base import AssetStage
from donna_common.orm.dal.mesh import MeshDAL, get_mesh_dal
from donna_common.orm.dal.project_branch import ProjectBranchDAL, get_project_branch_dal
from donna_common.orm.dal.project_version import (
    ProjectVersionDAL,
    get_project_version_dal,
)
from donna_common.orm.dal.project_version_asset import (
    ProjectVersionAssetDAL,
    get_project_version_asset_dal,
)
from donna_common.orm.dal.texture import TextureDAL, get_texture_dal
from donna_common.orm.models.texture import Texture
from donna_common.orm.models.user import User
from donna_common.providers.storage import StorageProvider
from donna_common.redis.types import MeshAction, TexturedMeshAction
from donna_worker.worker.mesh import MESH_DIR

load_dotenv()  # reads .env from cwd


router = APIRouter(prefix="/texture")

class GetTextureInfo(BaseModel):
    mesh_info: GetMeshInfo
    texture_id: str
    texture_url: str

@router.get("/{texture_id}")
async def get_model(texture_id: str, current_user: User = Depends(get_current_user), texture_dal: TextureDAL = Depends(get_texture_dal), mesh_dal: MeshDAL = Depends(get_mesh_dal)) -> GetTextureInfo:
    texture = await texture_dal.get_texture_by_id(texture_id)
    if not texture:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Texture not found"},
        )
    
    mesh = await mesh_dal.get_mesh_by_id(texture.mesh_id)

    mesh_info = await get_mesh_info(mesh.id)
    texture_url = None
    if (texture.storage_key):
        texture_url = StorageProvider().generate_get_url(texture.storage_key)
    return GetTextureInfo(
        mesh_info=mesh_info,
        texture_id=texture.id,
        texture_url=texture_url,
    )