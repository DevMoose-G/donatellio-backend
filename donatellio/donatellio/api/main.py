import asyncio
from hmac import HMAC
import json
from typing import Optional
import uuid

from fastapi import FastAPI, Depends, HTTPException, WebSocket
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession
import requests

from donatellio.api.types import RequestCreateImage, RequestCreateUser, RequestEditImage, RequestGetElaboratingQuestions, RequestLoginUser, WSImageEditsResponse, WSMeshResponse
from donatellio.orm import ImageDAL, get_image_dal, ProjectDAL, get_project_dal, Project, UserDAL, get_user_dal
from donatellio.utils.hashing import get_password_hash
from donatellio.orm.models.user import User
from donatellio.redisstream import RedisMessage, RedisPayload, RedisStream

from donatellio.orm.main import AsyncSessionLocal, get_db

from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from dotenv import load_dotenv
load_dotenv()    # reads .env from cwd

# Initialize FastAPI
app = FastAPI()

# allow local react to interact with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # CRA’s default
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Serve all files under ./static at the /static URL path
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/register")
async def register(user: RequestCreateUser, db: AsyncSession = Depends(get_db)):
    db_user = await db.execute(
        select(User).where((User.username == user.username) | (User.email == user.email))
    )
    db_user = db_user.scalars().first()
    if db_user:
        raise HTTPException(status_code=400, detail="User already exists")
    hashed_pw = get_password_hash(user.password)
    new_user = User(id=str(uuid.uuid4()), email=user.email, password=hashed_pw, username=user.username)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"msg": "User created", "user_id": new_user.id}

@app.post("/login")
async def login(request: RequestLoginUser, user_dal: UserDAL = Depends(get_user_dal)):
    db_user = await user_dal.get_user_by(filter=(User.username == request.username))
    if db_user is None:
        db_user = await user_dal.get_user_by(filter=(User.email == request.email))

    if db_user is None:
        raise HTTPException(status_code=400, detail="User does not exist.")
    
    hashed_pw = get_password_hash(request.password)
    if hashed_pw != db_user.password:
        raise HTTPException(status_code=400, detail="Invalid password.")

    return {"user_id": db_user.id}

# is it good to have one socket per project and have the frontend filter if it is image or text?
@app.websocket("/ws/projects/{project_id}/image")
async def image_updates(websocket: WebSocket, project_id: str, project_dal: ProjectDAL = Depends(get_project_dal)):
    await websocket.accept()
    stream = RedisStream("completed-jobs", group_name="image")
    await stream.setup_group(new_only=False)
    await asyncio.sleep(2)
    while True:

        images = await project_dal.get_images(project_id)
        if images != []:
            chats = await project_dal.get_image_prompt_chats(project_id)
            image_urls = await project_dal.get_image_urls(project_id)
            await websocket.send_json(WSImageEditsResponse(image_urls=image_urls, chats=chats.chats).model_dump(mode="json"))

        response = await stream.consume_msg("consumer1", new_only=True, n_msgs=1)
        if len(response.messages) == 0:
            await asyncio.sleep(2)
        else:
            msg = response.messages[0]
            payload = json.loads(msg.json.payload)
            if msg.json.project_id == project_id:
                if msg.json.function_name == "generate_image":
                    await websocket.send_json(payload)
                    await stream.ack_msg(msg.id)
        
        
            # break
    
    await websocket.close()

@app.websocket("/ws/projects/{project_id}/mesh")
async def mesh_updates(websocket: WebSocket, project_id: str, project_dal: ProjectDAL = Depends(get_project_dal)):
    await websocket.accept()
    stream = RedisStream("completed-jobs", group_name="mesh")
    await stream.setup_group(new_only=False)
    await asyncio.sleep(2)
    while True:

        meshes = await project_dal.get_meshes(project_id)
        if meshes != []:
            mesh_urls = await project_dal.get_image_urls(project_id)
            await websocket.send_json(WSMeshResponse(mesh_urls=mesh_urls).model_dump(mode="json"))

        response = await stream.consume_msg("consumer1", new_only=True, n_msgs=1)
        if len(response.messages) == 0:
            await asyncio.sleep(2)
        else:
            msg = response.messages[0]
            payload = json.loads(msg.json.payload)
            if msg.json.project_id == project_id:
                if msg.json.function_name == "generate_mesh":
                    await websocket.send_json(WSMeshResponse(mesh_urls=[payload["url"]]).model_dump(mode="json"))
                    await stream.ack_msg(msg.id)
        
        
            # break
    
    await websocket.close()

@app.post("/image/create", status_code=202)
async def create_image(
    req: RequestCreateImage,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
):
    project_id = str(uuid.uuid4())
    image_id = str(uuid.uuid4())

    stream = RedisStream("image-jobs")
    await stream.setup_group(new_only=False)

    user = await user_dal.get_user_by(filter=(User.username == "MuseG")) # temp
    await project_dal.create_project(id=project_id, name="test", user_id=user.id)

    await image_dal.create_image(id=image_id, prompt=req.prompt, project_id=project_id, url="")

    msg_id = await stream.send_msg(RedisPayload(image_id, "generate_image", {** req.model_dump(), "project_id": project_id, "image_id": image_id}))

    return {"image_id": image_id, "project_id": project_id}

# @app.get("/image/{project_id}/edits", status_code=202)
# async def get_image_edits(
#     project_id: str,
#     project_dal: ProjectDAL = Depends(get_project_dal)
# ):
#     chats = await project_dal.get_image_prompt_chats(project_id)
#     image_urls = await project_dal.get_image_urls(project_id)
#     return {
#         "chats": chats.chats,
#         "image_urls": image_urls
#     }

@app.post("/image/{project_id}/edit/", status_code=202)
async def edit_image(
    req: RequestEditImage,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
):
    stream = RedisStream("image-jobs")
    image_id = str(uuid.uuid4())
    await stream.setup_group(new_only=False)

    project = await project_dal.get_project_by_id(req.project_id)
    if project is None:
        raise HTTPException(400, detail="Invalid Project")

    msg_id = await stream.send_msg(RedisPayload(image_id, "edit_image", {**req.model_dump(), "project_id": req.project_id, "image_id": image_id}))

    await image_dal.create_image(id=image_id, prompt=req.prompt, project_id=project_id, url="", original_image_url=req.original_image_url)
 
    return {"project_id": req.project_id}

@app.get("/image/{project_id}/chats", status_code=200)
async def get_image_chat_history(
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal)
):
    response = await project_dal.get_image_prompt_chats(project_id)
    return response

@app.get("/model/{project_id}/view", status_code=200)
async def get_model_info(
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal)
):
    response = await project_dal.get_image_prompt_chats(project_id)
    return response

@app.get("/image/elaborate", status_code=200)
async def get_elaborating_questions(
    req: RequestGetElaboratingQuestions,
    project_dal: ProjectDAL = Depends(get_project_dal)
):
    stream = RedisStream("image-jobs")
    await stream.setup_group(new_only=False)

    project = await project_dal.get_project_by_id(req.project_id)
    if project is None:
        raise HTTPException(400, detail="Invalid Project")
    
    # TODO: cache this in redis to reduce openai calls

    # await stream.send_msg(RedisPayload(req.project_id, "edit_image", req.model_dump()))

    # return {"project_id": req.project_id}