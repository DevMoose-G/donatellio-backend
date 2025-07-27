from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.common.models import GetMeshInfo, get_mesh_info
from donna_api.types import ResponseMeshPreviewUrl
from donna_common.orm.dal.mesh import MeshDAL, get_mesh_dal
from donna_common.orm.dal.project import ProjectDAL, get_project_dal
from donna_common.orm.dal.texture import TextureDAL, get_texture_dal
from donna_common.orm.models.user import User
from donna_common.providers.storage import StorageProvider

load_dotenv()  # reads .env from cwd


router = APIRouter(prefix="/texture")


class GetTextureInfo(BaseModel):
    mesh_info: GetMeshInfo
    texture_id: str
    texture_url: str


@router.get("/{texture_id}")
async def get_model(
    texture_id: str,
    current_user: User = Depends(get_current_user),
    texture_dal: TextureDAL = Depends(get_texture_dal),
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
) -> GetTextureInfo:
    texture = await texture_dal.get_texture_by_id(texture_id)
    if not texture:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Texture not found"},
        )

    mesh = await mesh_dal.get_mesh_by_id(texture.mesh_id)

    mesh_info = await get_mesh_info(mesh.id)
    texture_url = None
    if texture.storage_key:
        texture_url = StorageProvider().generate_get_url(texture.storage_key)
    return GetTextureInfo(
        mesh_info=mesh_info,
        texture_id=texture.id,
        texture_url=texture_url,
    )

@router.get("/{texture_id}/preview")
async def get_texture_preview_url(
    texture_id: str,
    texture_dal: TextureDAL = Depends(get_texture_dal),
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
):
    texture = await texture_dal.get_texture_by_id(texture_id)
    if not texture:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "Mesh not found"},
        )
    project = await project_dal.get_project_by_id(texture.project_id)

    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "You don't have permission to view this mesh"},
        )
    
    preview_url = None
    if texture.static_render_storage_key:
        preview_url = StorageProvider().generate_get_url(texture.static_render_storage_key)

    return ResponseMeshPreviewUrl(
        mesh_id=texture.mesh_id,
        texture_id=texture.id,
        preview_url=preview_url,
    )