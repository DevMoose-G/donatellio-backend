import asyncio
from hmac import HMAC
import json
from typing import List, Optional
import uuid

from fastapi import APIRouter, FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession
import requests

from donatellio.api.types import AssetDisplay, GetAssetsResponse, GetProjectsResponse, ItemImagePromptChat, RequestCheckElaboratingQuestions, RequestCreateImage, RequestCreateMesh, RequestCreateTexture, RequestCreateUser, RequestEditImage, RequestGetElaboratingQuestions, RequestLoginUser, WSImageEditsResponse, WSImageItem, WSMeshItem, WSMeshResponse
from donatellio.workers.image import check_elaborating_questions, get_elaborating_questions
from donatellio.providers.storage import StorageProvider
from donatellio.orm.dal.mesh import MeshDAL, get_mesh_dal
from donatellio.orm import ImageDAL, get_image_dal, ProjectDAL, get_project_dal, Project, UserDAL, get_user_dal
from donatellio.utils.hashing import get_password_hash
from donatellio.orm.models.user import User
from donatellio.redisstream import RedisMessage, RedisPayload, RedisStream

from donatellio.orm.main import AsyncSessionLocal, get_db

from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from dotenv import load_dotenv

router = APIRouter()

# is it good to have one socket per project and have the frontend filter if it is image or text?
@router.websocket("/ws/projects/{project_id}/image")
async def image_updates(websocket: WebSocket, project_id: str, project_dal: ProjectDAL = Depends(get_project_dal), image_dal: ImageDAL = Depends(get_image_dal)):
    await websocket.accept()
    stream = RedisStream("completed-jobs", group_name="image")
    await stream.setup_group(new_only=False)
    await asyncio.sleep(2)
    current_img_s3_keys = []
    while True:
        images = await project_dal.get_images(project_id)
        if images != []:
            chats = await project_dal.get_image_prompt_chats(project_id)

            storage_provider = StorageProvider()

            # TODO: loop through images (instead of just the s3 keys)
            image_items = []
            for image in images:
                if image.storage_key not in current_img_s3_keys and image.storage_key != None:
                    img_url = storage_provider.generate_get_url(image.storage_key)
                    image_items.append(WSImageItem(id=image.id, url=img_url))
                    current_img_s3_keys.append(image.storage_key)

            if image_items != []:
                await websocket.send_json(WSImageEditsResponse(images=image_items, chats=chats.chats).model_dump(mode="json"))

        response = await stream.consume_msg("consumer1", new_only=True, n_msgs=1)
        if len(response.messages) == 0:
            await asyncio.sleep(2)
        else:
            msg = response.messages[0]
            payload = json.loads(msg.json.payload)
            if msg.json.project_id == project_id:
                if msg.json.function_name == "generate_image":
                    storage_provider = StorageProvider()
                    image_id = payload["image_id"]
                    image = await image_dal.get_image_by_id(image_id)
                    image_url = storage_provider.generate_get_url(image.storage_key)
                    await websocket.send_json(WSImageEditsResponse(images=[{"id":image_id, "url": image_url}]).model_dump(mode="json"))
                    await stream.ack_msg(msg.id)

@router.websocket("/ws/projects/{project_id}/mesh")
async def mesh_updates(websocket: WebSocket, project_id: str, mesh_dal: MeshDAL = Depends(get_mesh_dal), project_dal: ProjectDAL = Depends(get_project_dal)):
    await websocket.accept()
    stream = RedisStream("completed-jobs", group_name="mesh")
    await stream.setup_group(new_only=False)
    try:
        current_texture_s3_keys = []
        current_mesh_s3_keys = []
        while True:
            # assert project_dal.get_project_by_id(project_id) != None
            meshes = await project_dal.get_meshes(project_id)
            textures = await project_dal.get_textures(project_id)
            
            texture_items = []
            if textures != []:
                storage_provider = StorageProvider()
                for texture in textures:
                    if texture.storage_key not in current_texture_s3_keys and texture.storage_key != None:
                        texture_url = storage_provider.generate_get_url(texture.storage_key)
                        texture_items.append(WSMeshItem(id=texture.id, url=texture_url, image_id=texture.image_id))
                        current_texture_s3_keys.append(texture.storage_key)

            if texture_items != []:
                await websocket.send_json(WSMeshResponse(meshes=texture_items).model_dump(mode="json"))
            elif meshes != [] and current_texture_s3_keys == []:
                mesh_items = []
                storage_provider = StorageProvider()
                for mesh in meshes:
                    if mesh.storage_key not in current_mesh_s3_keys and mesh.storage_key != None:
                        mesh_url = storage_provider.generate_get_url(mesh.storage_key)
                        mesh_items.append(WSMeshItem(id=mesh.id, url=mesh_url, image_id=mesh.image_id))
                        current_mesh_s3_keys.append(mesh.storage_key)

                if mesh_items != []:
                    await websocket.send_json(WSMeshResponse(meshes=mesh_items).model_dump(mode="json"))

            response = await stream.consume_msg("consumer1", new_only=True, n_msgs=1)
            if len(response.messages) == 0:
                await asyncio.sleep(2)
            else:
                msg = response.messages[0]
                payload = json.loads(msg.json.payload)
                if msg.json.project_id == project_id:
                    if msg.json.function_name == "generate_mesh":
                        storage_provider = StorageProvider()
                        mesh_ids = payload["mesh_ids"]
                        
                        mesh_urls = []
                        for mesh_id in mesh_ids:
                            mesh = await mesh_dal.get_mesh_by_id(mesh_id)
                            mesh_urls.append(storage_provider.generate_get_url(mesh.storage_key))
                        await websocket.send_json(WSMeshResponse(mesh_urls=mesh_urls).model_dump(mode="json"))
                        await stream.ack_msg(msg.id)
            
            # break
    except WebSocketDisconnect:
        print("Client disconnected, WebSocket closed")
    
    await websocket.close()
