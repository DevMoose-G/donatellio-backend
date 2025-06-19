import asyncio
from typing import List

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from donna_api.auth import authenticate_jwt
from donna_api.types import (
    MeshFormat,
    WSImageEditsResponse,
    WSImageItem,
    WSMeshItem,
    WSMeshResponse,
)
from donna_common.orm import ImageDAL, ProjectDAL
from donna_common.orm.dal.mesh import MeshDAL
from donna_common.orm.dal.project import get_project_dal
from donna_common.orm.dal.texture import TextureDAL, get_texture_dal
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
                            image_url = storage_provider.generate_get_url(image.storage_key)

                        chats = await project_dal.get_image_prompt_chats(project_id)
                        await websocket.send_json(
                            WSImageEditsResponse(
                                images=[
                                    WSImageItem(
                                        id=image_id, url=image_url, is_partial=is_partial
                                    )
                                ],
                                chats=chats.chats,
                            ).model_dump(mode="json")
                        )
                        await stream.ack_msg(msg.id)
    except WebSocketDisconnect:
        # TODO: disconnect all sqlalchemy sessions
        print("Client disconnected, WebSocket closed")
        
    await websocket.close()

async def get_mesh_items(mesh_ids: List[str], storage_provider: StorageProvider) -> List[WSMeshItem]:

    mesh_items = []
    mesh_image_storage_keys = {}
    mesh_storage_keys = {}
    async with AsyncSessionLocal() as session:
        mesh_dal = MeshDAL(session)
        for mesh_id in mesh_ids:
            mesh = await mesh_dal.get_mesh_by_id(mesh_id)
            mesh_storage_keys[mesh.id] = mesh.storage_key

            other_format_item = await mesh_dal.get_output_formats(mesh.id)
            mesh_image_storage_keys[mesh.id] = mesh.static_render_storage_key

            mesh_items.append(
                WSMeshItem(
                    mesh_id=mesh.id,
                    image_id=mesh.image_id,
                    other_formats=other_format_item,
                    status=mesh.status,
                )
            )
    
    # now get mesh urls & mesh image urls
    for mesh_id in mesh_ids:
        mesh_image_storage_key = mesh_image_storage_keys.get(mesh_id)
        mesh_storage_key = mesh_storage_keys.get(mesh_id)
        mesh_url = (
            storage_provider.generate_get_url(
                mesh_storage_key
            )
            if mesh_storage_key
            else None
        )
        mesh_image_url = (
            storage_provider.generate_get_url(
                mesh_image_storage_key
            )
            if mesh_image_storage_key
            else None
        )
        
        for mesh_item in mesh_items:
            if mesh_item.mesh_id == mesh_id:
                mesh_item.url = mesh_url
                mesh_item.mesh_image_url = mesh_image_url
                break
        
        
    return mesh_items

async def get_texture_items(texture_ids: List[str], storage_provider: StorageProvider) -> List[WSMeshItem]:
    textured_items: List[WSMeshItem] = []
    texture_image_storage_keys = {}
    texture_storage_keys = {}
    async with AsyncSessionLocal() as session:
        texture_dal = TextureDAL(session)
        for texture_id in texture_ids:
            texture = await texture_dal.get_texture_by_id(texture_id)
            texture_storage_keys[texture.id] = texture.storage_key

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
    
    # now get texture urls & texture image urls
    for texture_id in texture_ids:
        texture_image_storage_key = texture_image_storage_keys.get(texture_id)
        texture_storage_key = texture_storage_keys.get(texture_id)
        texture_url = (
            storage_provider.generate_get_url(
                texture_storage_key
            )
            if texture_storage_key
            else None
        )
        texture_image_url = (
            storage_provider.generate_get_url(
                texture_image_storage_key
            )
            if texture_image_storage_key
            else None
        )
        
        for textured_item in textured_items:
            if textured_item.texture_id == texture_id:
                textured_item.url = texture_url
                textured_item.textured_image_url = texture_image_url
                break

    return textured_items

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
    
    try:
        # TODO: need better way to keep track of the current meshes and textures
        added_meshes = set()
        while True:
            async with AsyncSessionLocal() as session:
                project_dal = ProjectDAL(session)
                meshes = await project_dal.get_meshes(project_id)
                textures = await project_dal.get_textures(project_id)

            # getting what's in the database
            texture_items = []
            mesh_items = []
            if textures != []:
                storage_provider = StorageProvider()
                texture_ids = [
                    texture.id for texture in textures if (texture.mesh_id not in added_meshes)
                ]
                texture_items = await get_texture_items(texture_ids, storage_provider)
                for texture in texture_items:
                    added_meshes.add(texture.mesh_id)

            # breakpoint()
            if meshes != []:
                storage_provider = StorageProvider()
                mesh_ids = [mesh.id for mesh in meshes if (mesh.id not in added_meshes)]
                mesh_items = await get_mesh_items(mesh_ids, storage_provider)
                for mesh in mesh_items:
                    added_meshes.add(mesh.mesh_id)

            all_meshes = texture_items + mesh_items
            if all_meshes != []:
                await websocket.send_json(
                    WSMeshResponse(meshes=all_meshes).model_dump(mode="json")
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
                            storage_provider = StorageProvider()

                            mesh_items = await get_mesh_items(
                                action.mesh_ids, storage_provider
                            )
                            await websocket.send_json(
                                WSMeshResponse(meshes=mesh_items).model_dump(
                                    mode="json"
                                )
                            )
                            await stream.ack_msg(msg.id)
                        elif (
                            action.function_name == "generate_texture"
                            and action.type == "textured_mesh"
                        ):
                            storage_provider = StorageProvider()

                            mesh_items = await get_texture_items(
                                [action.texture_id], storage_provider
                            )
                            await websocket.send_json(
                                WSMeshResponse(meshes=mesh_items).model_dump(
                                    mode="json"
                                )
                            )
                            await stream.ack_msg(msg.id)

            # break
    except WebSocketDisconnect:
        print("Client disconnected, WebSocket closed")

    await websocket.close()
