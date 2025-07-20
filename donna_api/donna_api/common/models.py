from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple

from pydantic import BaseModel

from donna_api.types import (
    WSMeshItem,
    WSModelItem,
    WSTextureItem,
)
from donna_api.utils import (
    expected_mesh_gen_time,
    expected_texture_gen_time,
)
from donna_common.orm import ImageDAL
from donna_common.orm.base import AssetStage
from donna_common.orm.dal.mesh import MeshDAL
from donna_common.orm.dal.project_action import ProjectActionDAL
from donna_common.orm.dal.project_version import (
    ProjectVersionDAL,
)
from donna_common.orm.dal.texture import TextureDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.orm.models.project_action import ProjectAction
from donna_common.providers.storage import StorageProvider


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
        # breakpoint()
        assets = project_version.assets

        texture_ids = [
            asset.asset_id for asset in assets if asset.asset_type == AssetStage.texture
        ]

        for texture_id in texture_ids:
            texture = await texture_dal.get_texture_by_id(texture_id)
            if texture is None:
                return

            model_preview_storage_key = (
                texture.static_render_storage_key or mesh.static_render_storage_key
            )

            preview_url = None
            if model_preview_storage_key is not None:
                preview_url = storage_provider.generate_get_url(
                    model_preview_storage_key
                )

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
                preview_url = storage_provider.generate_get_url(
                    mesh.static_render_storage_key
                )

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


async def get_mesh_item(
    storage_provider: StorageProvider, mesh_id: str
) -> Optional[WSMeshItem]:
    mesh_storage_key = None
    mesh_image_storage_key = None
    mesh_item = None
    async with AsyncSessionLocal() as session:
        mesh_dal = MeshDAL(session)

        mesh = await mesh_dal.get_mesh_by_id(mesh_id)
        if mesh is None:
            print(f"Mesh {mesh_id} not found")
            return
        mesh_storage_key = mesh.storage_key

        mesh_image_storage_key = mesh.static_render_storage_key

        expected_time = None
        if mesh.status == "PENDING":
            # find the action that generated this mesh, then count # of other meshes generated in this version
            async with AsyncSessionLocal() as session:
                project_action_dal = ProjectActionDAL(session)
                actions = await project_action_dal.get_actions_by_asset(
                    asset_id=mesh_id, asset_type=AssetStage.mesh
                )
                mesh_action = None
                for action in actions:
                    if (action.action_type == "generate_mesh") or (
                        action.action_type == "regenerate_mesh"
                    ):
                        mesh_action = action
                        break

                mesh_quality = action.parameters.get("quality", None)

                if mesh_action != None:
                    all_actions_in_version = (
                        await project_action_dal.get_all_actions_in_project_version(
                            version_id=mesh_action.project_version_id
                        )
                    )
                    sorted_actions: List[ProjectAction] = sorted(
                        all_actions_in_version, key=lambda action: action.created_at
                    )
                    # figure out how many meshes being generated are before this one in the queue
                    num_of_meshes_before = 0
                    for action in sorted_actions:
                        if action.action_type == "generate_mesh":
                            num_of_meshes_before += 1
                            if action.id == mesh_action.id:
                                break

            if mesh_quality == None:
                estimated_total_time = 30
            else:
                estimated_total_time = num_of_meshes_before * expected_mesh_gen_time(
                    mesh_quality
                )
            expected_time = mesh.created_at + timedelta(seconds=estimated_total_time)

        mesh_item = WSMeshItem(
            mesh_id=mesh.id,
            status=mesh.status,
            created_at=mesh.created_at,
            parent_mesh_id=mesh.parent_mesh_id,
            expected_completion_date=expected_time,
        )

    mesh_url = (
        storage_provider.generate_get_url(mesh_storage_key)
        if mesh_storage_key
        else None
    )
    mesh_image_url = (
        storage_provider.generate_get_url(mesh_image_storage_key)
        if mesh_image_storage_key
        else None
    )

    mesh_item.mesh_url = mesh_url
    mesh_item.mesh_image_url = mesh_image_url

    return mesh_item


async def get_texture_item(
    storage_provider: StorageProvider, texture_id: str
) -> WSTextureItem:
    texture_storage_key = None
    texture_image_storage_key = None
    texture_item = None
    async with AsyncSessionLocal() as session:
        texture_dal = TextureDAL(session)

        texture = await texture_dal.get_texture_by_id(texture_id)
        texture_storage_key = texture.storage_key

        texture_image_storage_key = texture.static_render_storage_key

        expected_time = None
        if texture.status == "PENDING":
            # find the action that generated this texture and get the quality of texture
            async with AsyncSessionLocal() as session:
                project_action_dal = ProjectActionDAL(session)
                actions = await project_action_dal.get_actions_by_asset(
                    asset_id=texture_id, asset_type=AssetStage.texture
                )
                texture_action = None
                for action in actions:
                    if action.action_type == "generate_texture":
                        texture_action = action
                        break

                texture_quality = texture_action.parameters["texture_quality"]

            estimated_total_time = expected_texture_gen_time(texture_quality)
            expected_time = texture.created_at + timedelta(seconds=estimated_total_time)

        texture_item = WSTextureItem(
            texture_id=texture.id,
            status=texture.status,
            created_at=texture.created_at,
            expected_completion_date=expected_time,
        )

    texture_url = (
        storage_provider.generate_get_url(texture_storage_key)
        if texture_storage_key
        else None
    )
    texture_image_url = (
        storage_provider.generate_get_url(texture_image_storage_key)
        if texture_image_storage_key
        else None
    )

    texture_item.texture_url = texture_url
    texture_item.texture_image_url = texture_image_url

    return texture_item


async def get_model_items(
    project_version_id,
    storage_provider: StorageProvider,
) -> List[WSModelItem]:
    model_items: List[WSModelItem] = []
    mesh_items = {}
    mesh_id_to_image_id = {}
    already_textured_meshes_ids = set()

    parent_mesh_ids = []

    async with AsyncSessionLocal() as session:
        project_version_dal = ProjectVersionDAL(session)
        texture_dal = TextureDAL(session)
        mesh_dal = MeshDAL(session)
        project_version = await project_version_dal.get_version_by_id(
            project_version_id
        )
        assets = project_version.assets

        mesh_ids = [
            asset.asset_id for asset in assets if asset.asset_type == AssetStage.mesh
        ]

        for mesh_id in mesh_ids:
            mesh = await mesh_dal.get_mesh_by_id(mesh_id)

            if mesh != None and mesh.parent_mesh_id != None:
                parent_mesh_ids.append(mesh.parent_mesh_id)

            mesh_item = await get_mesh_item(storage_provider, mesh_id)
            if mesh_item != None:
                mesh_items[mesh_id] = mesh_item
                mesh_id_to_image_id[mesh_id] = mesh.image_id

        texture_ids = [
            asset.asset_id for asset in assets if asset.asset_type == AssetStage.texture
        ]

        for texture_id in texture_ids:
            texture = await texture_dal.get_texture_by_id(texture_id)
            if texture is None:
                return
            texture_item = await get_texture_item(storage_provider, texture_id)

            mesh_item = mesh_items[texture.mesh_id]

            already_textured_meshes_ids.add(texture.mesh_id)
            model_items.append(
                WSModelItem(
                    texture=texture_item,
                    image_id=texture.image_id,
                    mesh=mesh_item,
                )
            )

    for mesh_id in mesh_items.keys():
        if mesh_id not in already_textured_meshes_ids:
            mesh_item = mesh_items[mesh_id]
            model_items.append(
                WSModelItem(
                    mesh=mesh_item,
                    image_id=mesh_id_to_image_id[mesh_id],
                    texture=None,
                )
            )

    # filter out parent meshes
    model_items = [
        item for item in model_items if item.mesh.mesh_id not in parent_mesh_ids
    ]

    return model_items


@dataclass(frozen=True)
class MeshTextureIDPair:
    mesh_id: str
    texture_id: Optional[str] = None


async def get_all_models_items(
    storage_provider: StorageProvider,
    added_meshes: Set[MeshTextureIDPair],
    version_id: str,
) -> Tuple[List[WSModelItem], Set]:
    model_items = await get_model_items(version_id, storage_provider)
    new_model_items = []
    for model_item in model_items:
        if model_item.texture is not None:
            mesh_texture_pair = MeshTextureIDPair(
                mesh_id=model_item.mesh.mesh_id,
                texture_id=model_item.texture.texture_id,
            )
        else:
            mesh_texture_pair = MeshTextureIDPair(mesh_id=model_item.mesh.mesh_id)

        if mesh_texture_pair not in added_meshes:
            new_model_items.append(model_item)
            added_meshes.add(mesh_texture_pair)

    return new_model_items, added_meshes
