import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from donna_api.auth import authenticate_jwt, get_current_user
from donna_api.types import (
    WSImageEditsResponse,
    WSImageItem,
    WSMeshItem,
    WSTextureItem,
    WSModelResponse,
    WSModelItem
)
from donna_api.utils import calculate_texture_gen_cost, expected_mesh_gen_time, expected_texture_gen_time
from donna_common.orm import ImageDAL, ProjectDAL
from donna_common.orm.base import AssetStage
from donna_common.orm.dal.mesh import MeshDAL
from donna_common.orm.dal.project import get_project_dal
from donna_common.orm.dal.project_action import ProjectActionDAL
from donna_common.orm.dal.project_branch import ProjectBranchDAL, get_project_branch_dal
from donna_common.orm.dal.project_version import ProjectVersionDAL, get_project_version_dal
from donna_common.orm.dal.project_version_asset import ProjectVersionAssetDAL
from donna_common.orm.dal.texture import TextureDAL
from donna_common.orm.dal.user import UserDAL, get_user_dal
from donna_common.orm.main import AsyncSessionLocal
from donna_common.orm.models.project import Project
from donna_common.orm.models.project_action import ProjectAction
from donna_common.orm.models.user import User
from donna_common.providers.storage import StorageProvider
from donna_common.redis.redisstream import RedisStream

router = APIRouter()


async def authenticate_ws(websocket: WebSocket, user_dal: UserDAL) -> User:
    await websocket.accept(subprotocol="access_token")
    # now wait for the auth message
    auth = await websocket.receive_json()
    token = auth.get("token")

    user_id = await authenticate_jwt(token)
    user = await user_dal.get_user_by(filter=(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if user.active == False:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


@router.websocket("/ws/projects/{project_id}/image")
async def image_updates(
    websocket: WebSocket,
    project_id: str,
):
    try:
        async with AsyncSessionLocal() as session:
            current_user = await authenticate_ws(websocket, UserDAL(session))
        
        async with AsyncSessionLocal() as session:
            project = await ProjectDAL(session).get_project_by((Project.id == project_id))
        if current_user.id != project.user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        stream = RedisStream("completed-jobs", group_name="image")
        await stream.setup_group(new_only=False)
        current_img_s3_keys = []
        while True:
            async with AsyncSessionLocal() as session:
                images = await ProjectDAL(session).get_images(project_id)

            if images != []:
                async with AsyncSessionLocal() as session:
                    chats = await ProjectDAL(session).get_image_prompt_chats(project_id)

                storage_provider = StorageProvider()

                # TODO: loop through images (instead of just the s3 keys)
                image_items = []
                for image in images:
                    if (
                        image.storage_key not in current_img_s3_keys
                        and image.storage_key != None
                    ):
                        img_url = storage_provider.generate_get_url(image.storage_key)
                        image_items.append(WSImageItem(id=image.id, url=img_url))
                        current_img_s3_keys.append(image.storage_key)

                if image_items != []:
                    await websocket.send_json(
                        WSImageEditsResponse(
                            images=image_items, chats=chats.chats
                        ).model_dump(mode="json")
                    )

            messages = await stream.consume_msg("consumer1", new_only=True, n_msgs=1)
            if len(messages) == 0:
                await asyncio.sleep(2)
            else:
                print("got a message")
                for msg in messages:
                    action = msg.action
                    if action.project_id == project_id and action.type == "image":
                        storage_provider = StorageProvider()
                        image_id = action.image_id

                        async with AsyncSessionLocal() as session:
                            image = await ImageDAL(session).get_image_by_id(image_id)

                        image_url = None
                        is_partial = True
                        if image and image.storage_key != None:
                            is_partial = action.is_partial
                            image_url = storage_provider.generate_get_url(
                                image.storage_key
                            )

                        async with AsyncSessionLocal() as session:
                            chats = await ProjectDAL(session).get_image_prompt_chats(project_id)
                        await websocket.send_json(
                            WSImageEditsResponse(
                                images=[
                                    WSImageItem(
                                        id=image_id,
                                        url=image_url,
                                        is_partial=is_partial,
                                    )
                                ],
                                chats=chats.chats,
                            ).model_dump(mode="json")
                        )
                        await stream.ack_msg(msg.id)
                    else:
                        print(f"got a message that won't be send for project_id={project_id} images {action}")
    except WebSocketDisconnect:
        print("Client disconnected, WebSocket closed")

async def get_mesh_item(storage_provider: StorageProvider, mesh_id: str) -> Optional[WSMeshItem]:
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
                actions = await project_action_dal.get_actions_by_asset(asset_id=mesh_id, asset_type=AssetStage.mesh)
                mesh_action = None
                for action in actions:
                    if (action.action_type == "generate_mesh") or (action.action_type == "regenerate_mesh"):
                        mesh_action = action
                        break
                
                mesh_quality = action.parameters.get("quality", None)
                
                all_actions_in_version = await project_action_dal.get_all_actions_in_project_version(version_id=mesh_action.project_version_id)
                sorted_actions: List[ProjectAction] = sorted(all_actions_in_version, key=lambda action: action.created_at)
                # figure out how many meshes being generated are before this one in the queue
                num_of_meshes_before = 0
                for action in sorted_actions:
                    if action.action_type == "generate_mesh":
                        num_of_meshes_before += 1
                        if action.id == mesh_action.id:
                            break
            
            if (mesh_quality == None):
                estimated_total_time = 30
            else:
                estimated_total_time = num_of_meshes_before * expected_mesh_gen_time(mesh_quality)
            expected_time = mesh.created_at + timedelta(seconds=estimated_total_time)
        
        mesh_item = WSMeshItem(mesh_id=mesh.id, status=mesh.status, created_at=mesh.created_at, parent_mesh_id=mesh.parent_mesh_id, expected_completion_date=expected_time)
    
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

async def get_texture_item(storage_provider: StorageProvider, texture_id: str) -> WSTextureItem:
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
                actions = await project_action_dal.get_actions_by_asset(asset_id=texture_id, asset_type=AssetStage.texture)
                texture_action = None
                for action in actions:
                    if (action.action_type == "generate_texture"):
                        texture_action = action
                        break
                
                texture_quality = action.parameters['texture_quality']
            
            estimated_total_time = expected_texture_gen_time(texture_quality)
            expected_time = texture.created_at + timedelta(seconds=estimated_total_time)

        texture_item = WSTextureItem(texture_id=texture.id,  status=texture.status, created_at=texture.created_at, expected_completion_date=expected_time)
    
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
    project_version_id, storage_provider: StorageProvider, 
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
        project_version = await project_version_dal.get_version_by_id(project_version_id)
        assets = project_version.assets
        
        mesh_ids = [asset.asset_id for asset in assets if asset.asset_type == AssetStage.mesh]
        
        for mesh_id in mesh_ids:
            mesh = await mesh_dal.get_mesh_by_id(mesh_id)
            
            if (mesh != None and mesh.parent_mesh_id != None):
                parent_mesh_ids.append(mesh.parent_mesh_id)
            
            mesh_item = await get_mesh_item(storage_provider, mesh_id)
            if mesh_item != None:
                mesh_items[mesh_id] = mesh_item
                mesh_id_to_image_id[mesh_id] = mesh.image_id
        
        texture_ids = [asset.asset_id for asset in assets if asset.asset_type == AssetStage.texture]
        
        for texture_id in texture_ids:
            texture = await texture_dal.get_texture_by_id(texture_id)
            if texture is None:
                breakpoint()
            texture_item = await get_texture_item(storage_provider, texture_id)
            
            mesh_item = mesh_items[texture.mesh_id]
            
            already_textured_meshes_ids.add(texture.mesh_id)
            model_items.append(WSModelItem(
                texture=texture_item, 
                image_id=texture.image_id, 
                mesh=mesh_item, 
            ))
        
    for mesh_id in mesh_items.keys():
        if mesh_id not in already_textured_meshes_ids:
            mesh_item = mesh_items[mesh_id]
            model_items.append(WSModelItem(
                mesh=mesh_item, 
                image_id=mesh_id_to_image_id[mesh_id], 
                texture=None, 
            ))
    
    # filter out parent meshes
    model_items = [item for item in model_items if item.mesh.mesh_id not in parent_mesh_ids]

    return model_items


@dataclass(frozen=True)
class MeshTextureIDPair:
    mesh_id: str
    texture_id: Optional[str] = None


async def get_all_models_items(storage_provider: StorageProvider, added_meshes: Set[MeshTextureIDPair], version_id: str) -> Tuple[List[WSModelItem], Set]:
    model_items = await get_model_items(version_id, storage_provider)
    new_model_items = []
    for model_item in model_items:
        if (model_item.texture is not None):
            mesh_texture_pair = MeshTextureIDPair(mesh_id=model_item.mesh.mesh_id, texture_id=model_item.texture.texture_id)
        else:
            mesh_texture_pair = MeshTextureIDPair(mesh_id=model_item.mesh.mesh_id)
            
        if mesh_texture_pair not in added_meshes:
            new_model_items.append(model_item)
            added_meshes.add(mesh_texture_pair)

    return new_model_items, added_meshes

@router.websocket("/ws/projects/{project_id}/mesh")
async def mesh_updates(
    websocket: WebSocket,
    project_id: str,
):
    async with AsyncSessionLocal() as session:
        current_user = await authenticate_ws(websocket, UserDAL(session))
    async with AsyncSessionLocal() as session:
        project = await ProjectDAL(session).get_project_by_id(project_id)
    if current_user.id != project.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    stream = RedisStream("completed-jobs", group_name="mesh")
    await stream.setup_group(new_only=False)
    
    storage_provider = StorageProvider()

    first_run = True

    try:
        # TODO: need better way to keep track of the current meshes and textures
        added_meshes = set()
        async with AsyncSessionLocal() as session:
            current_branch = await ProjectDAL(session).get_main_branch(project_id)
        
        while True:
            # getting what's in the database
            new_model_items, added_meshes = await get_all_models_items(storage_provider, added_meshes, current_branch.head_version_id)

            if new_model_items != [] or first_run:
                await websocket.send_json(
                    WSModelResponse(models=new_model_items).model_dump(mode="json")
                )
                first_run = False

            # now check the stream for new messages
            messages = await stream.consume_msg("consumer1", new_only=True, n_msgs=1)
            if len(messages) == 0:
                await asyncio.sleep(2)
            else:
                for msg in messages:
                    action = msg.action
                    if action.project_id == project_id:
                        print(f"got a message: {action}")
                        if (
                            (action.function_name == "generate_mesh" or action.function_name == "regenerate_from_latents" or action.function_name == "simplify_mesh")
                            and action.type == "mesh"
                        ):
                            model_items = []
                            for mesh_id in action.mesh_ids:
                                async with AsyncSessionLocal() as session:
                                    image = await MeshDAL(session).get_mesh_by_id(mesh_id)
                                    image_id = image.image_id
                                model_items.append(WSModelItem(
                                    mesh=await get_mesh_item(storage_provider, mesh_id),
                                    image_id=image_id
                                ))
                                
                            await websocket.send_json(
                                WSModelResponse(models=model_items).model_dump(
                                    mode="json"
                                )
                            )
                            await stream.ack_msg(msg.id)
                        elif (
                            action.function_name == "generate_texture"
                            and action.type == "textured_mesh"
                        ):
                            storage_provider = StorageProvider()

                            try:
                                model_item = WSModelItem(
                                    mesh=await get_mesh_item(storage_provider, action.params['mesh_id']),
                                    texture=await get_texture_item(storage_provider, action.texture_id),
                                    image_id=action.params['image_id']
                                )
                            except Exception as e:
                                print(e)
                                breakpoint()
                            await websocket.send_json(
                                WSModelResponse(models=[model_item]).model_dump(
                                    mode="json"
                                )
                            )
                            await stream.ack_msg(msg.id)
                        else:
                            print("did not send message")

    except WebSocketDisconnect:
        print("Client disconnected, WebSocket closed")