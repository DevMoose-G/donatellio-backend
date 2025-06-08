import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from donna_api.types import (
    MeshFormat,
    WSImageEditsResponse,
    WSImageItem,
    WSMeshItem,
    WSMeshResponse,
)
from donna_common.orm import ImageDAL, ProjectDAL
from donna_common.orm.dal.mesh import MeshDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.providers.storage import StorageProvider
from donna_common.redis.redisstream import RedisStream

router = APIRouter()


@router.websocket("/ws/projects/{project_id}/image")
async def image_updates(
    websocket: WebSocket,
    project_id: str,
    # current_user: User = Depends(get_current_user_from_ws)
):
    # project = await project_dal.get_project_by((Project.id == project_id))
    # if current_user.id != project.user_id:
    #     raise HTTPException(status_code=401, detail="Not authenticated")

    await websocket.accept()
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
                    is_partial = action.is_partial

                    async with AsyncSessionLocal() as session:
                        image_dal = ImageDAL(session)
                        image = await image_dal.get_image_by_id(image_id)
                    if image.storage_key == None:
                        continue
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


@router.websocket("/ws/projects/{project_id}/mesh")
async def mesh_updates(
    websocket: WebSocket,
    project_id: str,
    #    current_user: User = Depends(get_current_user_from_ws)
):
    # if current_user.id != project_dal.get_project(project_id).user_id:
    #     raise HTTPException(status_code=401, detail="Not authenticated")

    await websocket.accept()
    stream = RedisStream("completed-jobs", group_name="mesh")
    await stream.setup_group(new_only=False)
    try:
        current_texture_s3_keys = []
        current_mesh_s3_keys = []
        added_meshes = set()
        while True:
            async with AsyncSessionLocal() as session:
                project_dal = ProjectDAL(session)
                meshes = await project_dal.get_meshes(project_id)
                textures = await project_dal.get_textures(project_id)

            texture_items = []
            mesh_items = []
            if textures != []:
                storage_provider = StorageProvider()
                for texture in textures:
                    if (
                        texture.storage_key not in current_texture_s3_keys
                        and texture.storage_key != None
                    ):
                        texture_url = storage_provider.generate_get_url(
                            texture.storage_key
                        )

                        other_format_item = MeshFormat()
                        other_formats = texture.format_storage_keys
                        if other_formats != None:
                            for format, key in other_formats.items():
                                if key != None:
                                    other_format_url = (
                                        storage_provider.generate_get_url(key)
                                    )
                                    other_format_item.__setattr__(
                                        f"{format}_url", other_format_url
                                    )

                        # get the image urls
                        textured_image_url = (
                            storage_provider.generate_get_url(
                                texture.static_render_storage_key
                            )
                            if texture.static_render_storage_key
                            else None
                        )
                        matched_mesh = None
                        for mesh in meshes:
                            if mesh.id == texture.mesh_id:
                                matched_mesh = mesh
                        mesh_image_url = (
                            storage_provider.generate_get_url(
                                matched_mesh.static_render_storage_key
                            )
                            if matched_mesh.static_render_storage_key
                            else None
                        )

                        texture_items.append(
                            WSMeshItem(
                                texture_id=texture.id,
                                mesh_id=texture.mesh_id,
                                url=texture_url,
                                image_id=texture.image_id,
                                other_formats=other_format_item,
                                status=texture.status,
                                textured_image_url=textured_image_url,
                                mesh_image_url=mesh_image_url,
                            )
                        )
                        added_meshes.add(texture.mesh_id)
                        current_texture_s3_keys.append(texture.storage_key)

            if meshes != []:
                storage_provider = StorageProvider()
                for mesh in meshes:
                    if (
                        mesh.storage_key not in current_mesh_s3_keys
                        and mesh.storage_key != None
                        and mesh.id not in added_meshes
                    ):
                        mesh_url = (
                            storage_provider.generate_get_url(mesh.storage_key)
                            if mesh.storage_key != ""
                            else None
                        )

                        other_format_item = MeshFormat()
                        other_formats = mesh.format_storage_keys
                        if other_formats != None:
                            for format, key in other_formats.items():
                                if key != None:
                                    other_format_url = (
                                        storage_provider.generate_get_url(key)
                                    )
                                    other_format_item.__setattr__(
                                        f"{format}_url", other_format_url
                                    )

                        # get the image urls
                        mesh_image_url = (
                            storage_provider.generate_get_url(
                                mesh.static_render_storage_key
                            )
                            if mesh.static_render_storage_key
                            else None
                        )

                        mesh_items.append(
                            WSMeshItem(
                                mesh_id=mesh.id,
                                url=mesh_url,
                                image_id=mesh.image_id,
                                other_formats=other_format_item,
                                status=mesh.status,
                                mesh_image_url=mesh_image_url,
                            )
                        )
                        current_mesh_s3_keys.append(mesh.storage_key)

            all_meshes = texture_items + mesh_items
            if all_meshes != []:
                await websocket.send_json(
                    WSMeshResponse(meshes=all_meshes).model_dump(mode="json")
                )

            messages = await stream.consume_msg("consumer1", new_only=True, n_msgs=1)
            if len(messages) == 0:
                await asyncio.sleep(2)
            else:
                for msg in messages:
                    action = msg.action
                    if action.project_id == project_id:
                        if (
                            action.function_name == "generate_mesh"
                            and action.type == "mesh"
                        ):
                            storage_provider = StorageProvider()
                            mesh_ids = action.mesh_ids

                            mesh_items = []
                            async with AsyncSessionLocal() as session:
                                mesh_dal = MeshDAL(session)
                                for mesh_id in mesh_ids:
                                    mesh = await mesh_dal.get_mesh_by_id(mesh_id)
                                    mesh_url = storage_provider.generate_get_url(
                                        mesh.storage_key
                                    )

                                    # TODO: move this to mesh_dal?
                                    other_format_item = MeshFormat()
                                    other_formats = mesh.format_storage_keys
                                    if other_formats != None:
                                        for format, key in other_formats.items():
                                            if key != None:
                                                other_format_url = (
                                                    storage_provider.generate_get_url(
                                                        key
                                                    )
                                                )
                                                other_format_item.__setattr__(
                                                    f"{format}_url", other_format_url
                                                )

                                    # get the image urls
                                    mesh_image_url = (
                                        storage_provider.generate_get_url(
                                            mesh.static_render_storage_key
                                        )
                                        if mesh.static_render_storage_key
                                        else None
                                    )

                                    mesh_items.append(
                                        WSMeshItem(
                                            mesh_id=mesh.id,
                                            url=mesh_url,
                                            image_id=mesh.image_id,
                                            other_formats=other_format_item,
                                            status=mesh.status,
                                            mesh_image_url=mesh_image_url,
                                        )
                                    )
                            await websocket.send_json(
                                WSMeshResponse(meshes=mesh_items).model_dump(
                                    mode="json"
                                )
                            )
                            await stream.ack_msg(action.id)

            # break
    except WebSocketDisconnect:
        print("Client disconnected, WebSocket closed")

    await websocket.close()
