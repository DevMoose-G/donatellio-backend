import asyncio
from dataclasses import dataclass
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
from donna_common.orm import ImageDAL, ProjectDAL
from donna_common.orm.base import AssetStage
from donna_common.orm.dal.mesh import MeshDAL
from donna_common.orm.dal.project import get_project_dal
from donna_common.orm.dal.project_branch import ProjectBranchDAL, get_project_branch_dal
from donna_common.orm.dal.project_version import ProjectVersionDAL, get_project_version_dal
from donna_common.orm.dal.texture import TextureDAL
from donna_common.orm.dal.user import UserDAL, get_user_dal
from donna_common.orm.main import AsyncSessionLocal
from donna_common.orm.models.project import Project
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
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
):
    try:
        current_user = await authenticate_ws(websocket, user_dal)

        project = await project_dal.get_project_by((Project.id == project_id))
        if current_user.id != project.user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        stream = RedisStream("completed-jobs", group_name="image")
        await stream.setup_group(new_only=False)
        current_img_s3_keys = []
        while True:
            async with AsyncSessionLocal() as session:
                project_dal = ProjectDAL(session)
                images = await project_dal.get_images(project_id)

            if images != []:
                async with AsyncSessionLocal() as session:
                    project_dal = ProjectDAL(session)
                    chats = await project_dal.get_image_prompt_chats(project_id)

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
                            image_dal = ImageDAL(session)
                            image = await image_dal.get_image_by_id(image_id)

                        image_url = None
                        is_partial = False
                        if image and image.storage_key != None:
                            is_partial = action.is_partial
                            image_url = storage_provider.generate_get_url(
                                image.storage_key
                            )

                        chats = await project_dal.get_image_prompt_chats(project_id)
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
    except WebSocketDisconnect:
        # TODO: disconnect all sqlalchemy sessions
        print("Client disconnected, WebSocket closed")

    # await websocket.close()

async def get_mesh_item(storage_provider: StorageProvider, mesh_id: str) -> Optional[WSMeshItem]:
    mesh_storage_key = None
    mesh_image_storage_key = None
    mesh_item = None
    async with AsyncSessionLocal() as session:
        mesh_dal = MeshDAL(session)
        
        mesh = await mesh_dal.get_mesh_by_id(mesh_id)
        if mesh is None:
            print("Mesh not found")
            return
        mesh_storage_key = mesh.storage_key

        other_format_item = await mesh_dal.get_output_formats(mesh.id)
        mesh_image_storage_key = mesh.static_render_storage_key
        
        mesh_item = WSMeshItem(mesh_id=mesh.id, other_formats=other_format_item, status=mesh.status)
    
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

        other_format_item = await texture_dal.get_output_formats(texture.id)
        texture_image_storage_key = texture.static_render_storage_key
        
        texture_item = WSTextureItem(texture_id=texture.id, other_formats=other_format_item, status=texture.status)
    
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
            
            if (mesh == None):
                breakpoint()
            
            if (mesh.parent_mesh_id != None):
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


async def get_texture_items(
    texture_ids: List[str], storage_provider: StorageProvider
) -> List[WSMeshItem]:
    textured_items: List[WSMeshItem] = []
    texture_image_storage_keys = {}
    texture_storage_keys = {}
    mesh_storage_keys = {}
    async with AsyncSessionLocal() as session:
        texture_dal = TextureDAL(session)
        mesh_dal = MeshDAL(session)
        for texture_id in texture_ids:
            texture = await texture_dal.get_texture_by_id(texture_id)
            mesh = await mesh_dal.get_mesh_by_id(texture.mesh_id)
            texture_storage_keys[texture.id] = texture.storage_key
            mesh_storage_keys[texture.id] = mesh.storage_key
            other_format_item = await texture_dal.get_output_formats(texture.id)

            texture_image_storage_keys[texture.id] = texture.static_render_storage_key

            textured_items.append(
                WSMeshItem(
                    mesh_id=texture.mesh_id,
                    texture_id=texture.id,
                    image_id=texture.image_id,
                    other_formats=other_format_item,
                    status=texture.status,
                )
            )

    # better way to do this b/c not good to keep postgres session open while getting urls
    # now get texture urls & texture image urls
    for texture_id in texture_ids:
        texture_image_storage_key = texture_image_storage_keys.get(texture_id)
        texture_storage_key = texture_storage_keys.get(texture_id)
        mesh_storage_key = mesh_storage_keys.get(texture_id)
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
        mesh_url = (
            storage_provider.generate_get_url(mesh_storage_key)
            if mesh_storage_key
            else None
        )

        for textured_item in textured_items:
            if textured_item.texture_id == texture_id:
                textured_item.textured_url = texture_url
                textured_item.textured_image_url = texture_image_url
                textured_item.mesh_url = mesh_url
                break

    return textured_items

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
    user_dal: UserDAL = Depends(get_user_dal),
    project_dal: ProjectDAL = Depends(get_project_dal),
):
    current_user = await authenticate_ws(websocket, user_dal)
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    stream = RedisStream("completed-jobs", group_name="mesh")
    await stream.setup_group(new_only=False)
    
    storage_provider = StorageProvider()

    try:
        # TODO: need better way to keep track of the current meshes and textures
        added_meshes = set()
        current_branch = await project_dal.get_main_branch(project_id)
        
        
        while True:
            # getting what's in the database
            new_model_items, added_meshes = await get_all_models_items(storage_provider, added_meshes, current_branch.head_version_id)

            if new_model_items != []:
                await websocket.send_json(
                    WSModelResponse(models=new_model_items).model_dump(mode="json")
                )

            # now check the stream for new messages
            messages = await stream.consume_msg("consumer1", new_only=True, n_msgs=1)
            if len(messages) == 0:
                await asyncio.sleep(2)
            else:
                for msg in messages:
                    action = msg.action
                    if action.project_id == project_id:
                        # need to also do it for textured mesh textured_mesh
                        if (
                            action.function_name == "generate_mesh"
                            and action.type == "mesh"
                        ):

                            model_items = []
                            for mesh_id in action.mesh_ids:
                                try:
                                    model_items.append(WSModelItem(
                                        mesh=await get_mesh_item(storage_provider, mesh_id),
                                        image_id=action.params['image_id']
                                    ))
                                except Exception as e:
                                    print(e)
                                    breakpoint()
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
                            await get_texture_items(
                                [action.texture_id], storage_provider
                            )
                            await websocket.send_json(
                                WSModelResponse(models=[model_item]).model_dump(
                                    mode="json"
                                )
                            )
                            await stream.ack_msg(msg.id)

    except WebSocketDisconnect:
        print("Client disconnected, WebSocket closed")