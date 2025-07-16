import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from donna_api.auth import authenticate_jwt
from donna_api.types import (
    WSImageEditsResponse,
    WSImageItem,
    WSMeshItem,
    WSModelItem,
    WSModelResponse,
    WSTextureItem,
)
from donna_api.utils import (
    expected_mesh_gen_time,
    expected_texture_gen_time,
)
from donna_common.orm import ImageDAL, ProjectDAL
from donna_common.orm.base import AssetStage
from donna_common.orm.dal.mesh import MeshDAL
from donna_common.orm.dal.project_action import ProjectActionDAL
from donna_common.orm.dal.project_version import (
    ProjectVersionDAL,
)
from donna_common.orm.dal.texture import TextureDAL
from donna_common.orm.dal.user import UserDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.orm.models.project import Project
from donna_common.orm.models.project_action import ProjectAction
from donna_common.orm.models.user import User
from donna_common.providers.storage import StorageProvider
from donna_common.redis.redisstream import RedisStream

class BasicModelInfo(BaseModel):
    image_id: str
    mesh_id: str
    texture_id: Optional[str] = None
    model_preview_url: Optional[str] = None

async def get_all_basic_model_infos(
    project_version_id,
    storage_provider: StorageProvider,
) -> List[BasicModelInfo]:
    model_items: List[BasicModelInfo] = []
    already_sent_meshes_ids = set()

    async with AsyncSessionLocal() as session:
        project_version_dal = ProjectVersionDAL(session)
        texture_dal = TextureDAL(session)
        mesh_dal = MeshDAL(session)
        project_version = await project_version_dal.get_version_by_id(
            project_version_id
        )
        assets = project_version.assets

        texture_ids = [
            asset.asset_id for asset in assets if asset.asset_type == AssetStage.texture
        ]

        for texture_id in texture_ids:
            texture = await texture_dal.get_texture_by_id(texture_id)
            if texture is None:
                return
            
            model_preview_storage_key = texture.static_render_storage_key or mesh.static_render_storage_key

            preview_url = None
            if model_preview_storage_key is not None:
                preview_url = storage_provider.generate_get_url(model_preview_storage_key)
            
            already_sent_meshes_ids.add(texture.mesh_id)

            model_items.append(
                BasicModelInfo(
                    image_id=texture.image_id,
                    mesh_id=texture.mesh_id,
                    texture_id=texture_id,
                    model_preview_url=preview_url,
                )
            )

        mesh_ids = [
            asset.asset_id for asset in assets if asset.asset_type == AssetStage.mesh
        ]

        for mesh_id in mesh_ids:
            if mesh_id in already_sent_meshes_ids:
                continue
            mesh = await mesh_dal.get_mesh_by_id(mesh_id)

            preview_url = None
            if mesh.static_render_storage_key is not None:
                preview_url = storage_provider.generate_get_url(mesh.static_render_storage_key)
            
            already_sent_meshes_ids.add(mesh_id)

            model_items.append(
                BasicModelInfo(
                    image_id=mesh.image_id,
                    mesh_id=mesh.id,
                    model_preview_url=preview_url,
                )
            )

    return model_items

class GetMeshInfo(BaseModel):
    project_id: str
    # eventually remove this source_image_url and move it to GetModelInfo
    image_id: str
    source_image_url: str
    mesh_quality: str
    created_at: datetime
    level_of_detail: Optional[int] = None
    mc_level: Optional[float] = None
    num_faces: Optional[int] = None
    mesh_url: Optional[str] = None
    # do i need these
    # mesh_status: Optional[str] = None
    # texture_status: Optional[str] = None

async def get_mesh_info(mesh_id: str):
    storage_provider = StorageProvider()
    async with AsyncSessionLocal() as session:
        mesh_dal = MeshDAL(session)
        image_dal = ImageDAL(session)
        mesh = await mesh_dal.get_mesh_by_id(mesh_id)
        image = await image_dal.get_image_by_id(mesh.image_id)
    image_url = storage_provider.generate_get_url(image.storage_key)

    mesh_quality = ""
    if mesh.num_inference_steps == 30:
        mesh_quality = "low"
    elif mesh.num_inference_steps == 50:
        mesh_quality = "medium"
    elif mesh.num_inference_steps == 70:
        mesh_quality = "high"

    lod = None
    if mesh.octree_resolution == None:
        lod = 0  # TEMP
    elif int(mesh.octree_resolution) == 128:
        lod = 1
    elif int(mesh.octree_resolution) == 256:
        lod = 2
    elif int(mesh.octree_resolution) == 384:
        lod = 3
    elif int(mesh.octree_resolution) == 512:
        lod = 4
    elif int(mesh.octree_resolution) == 768:
        lod = 5
    else:
        raise Exception(f"Invalid octree resolution for mesh {mesh_id}")
    
    mesh_url = None
    if mesh.storage_key:
        mesh_url = storage_provider.generate_get_url(mesh.storage_key)

    return GetMeshInfo(
        project_id=mesh.project_id,
        num_faces=mesh.face_count,
        source_image_url=image_url,
        image_id=mesh.image_id,
        mesh_quality=mesh_quality,
        level_of_detail=lod,
        mc_level=0 if mesh.mc_level == None else mesh.mc_level,
        created_at=mesh.created_at,
        mesh_url=mesh_url,
    )