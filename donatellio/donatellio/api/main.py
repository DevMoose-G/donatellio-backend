import asyncio
from hmac import HMAC
import json
from typing import List, Optional
import uuid

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession
import requests

from donatellio.api.types import AssetDisplay, GetAssetsResponse, GetProjectsResponse, ItemImagePromptChat, ProjectDisplay, RequestCalculateMeshGenCost, RequestCalculateTextureGenCost, RequestCheckElaboratingQuestions, RequestCreateImage, RequestCreateMesh, RequestCreateTexture, RequestCreateUser, RequestEditImage, RequestGetElaboratingQuestions, RequestLoginUser, ResponseCalculateMeshGenCost, WSImageEditsResponse, WSImageItem, WSMeshItem, WSMeshResponse
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
from donatellio.api.websocket import router as websocket_router
from donatellio.api.auth import router as auth_router
load_dotenv()    # reads .env from cwd

# Initialize FastAPI
app = FastAPI()

app.include_router(websocket_router)
app.include_router(auth_router)

# allow local react to interact with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # CRA’s default
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Serve all files under ./static at the /static URL path
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/market/assets", status_code=200)
async def get_market_assets(limit: int, project_dal: ProjectDAL = Depends(get_project_dal), user_dal: UserDAL = Depends(get_user_dal)) -> GetAssetsResponse:
    user = await user_dal.get_user_by(filter=(User.username == "MuseG"))
    projects = [project for project in await project_dal.get_all_projects_by(filter=(Project.user_id != user.id)) if project.meshes != []]
    assets = []
    for i in range(min(limit, len(projects))):
        project = projects[i]
        storage_provider = StorageProvider()
        uploaded_textures = await project_dal.get_uploaded_textures(project_id=project.id)
        if uploaded_textures == []:
            continue
        url = storage_provider.generate_get_url(uploaded_textures[-1].storage_key)
        assets.append(AssetDisplay(project_id=project.id, url=url, user_name=project.owner.username))
    return GetAssetsResponse(assets=assets, count=len(assets))

@app.get("/user/projects", status_code=200)
async def get_users_projects(limit: int, project_dal: ProjectDAL = Depends(get_project_dal), user_dal: UserDAL = Depends(get_user_dal)) -> GetProjectsResponse:
    user = await user_dal.get_user_by(filter=(User.username == "MuseG")) # temp
    projects = [project for project in await project_dal.get_all_projects_by(filter=(Project.user_id == user.id))] 
    assets = []
    for i in range(min(limit, len(projects))):
        project = projects[i]
        storage_provider = StorageProvider()

        if project.meshes == []:
            uploaded_images = await project_dal.get_uploaded_images(project_id=project.id)
            if uploaded_images == []:
                continue    
            url = storage_provider.generate_get_url(uploaded_images[-1].storage_key)
            assets.append(ProjectDisplay(project_id=project.id, url=url, user_name="MuseG", current_state="image"))
        elif project.textures == []: # don't display textured meshes (considered complete)
            uploaded_meshes = await project_dal.get_uploaded_meshes(project_id=project.id)
            if uploaded_meshes == []:
                continue
            url = storage_provider.generate_get_url(uploaded_meshes[-1].storage_key)
            assets.append(ProjectDisplay(project_id=project.id, url=url, user_name="MuseG", current_state="mesh"))
    
    return GetProjectsResponse(projects=assets, count=len(assets))

@app.get("/user/assets", status_code=200)
async def get_users_assets(limit: int, project_dal: ProjectDAL = Depends(get_project_dal), user_dal: UserDAL = Depends(get_user_dal)) -> GetAssetsResponse:
    user = await user_dal.get_user_by(filter=(User.username == "MuseG")) # temp
    projects = [project for project in await project_dal.get_all_projects_by(filter=(Project.user_id == user.id))] 
    assets = []
    for i in range(min(limit, len(projects))):
        project = projects[i]
        storage_provider = StorageProvider()

        if project.textures == []:
            # url = storage_provider.generate_get_url(project.images[-1].storage_key)
            continue
        else:
            uploaded_textures = await project_dal.get_uploaded_textures(project_id=project.id)
            if uploaded_textures == []:
                continue    
            url = storage_provider.generate_get_url(uploaded_textures[-1].storage_key)
        assets.append(AssetDisplay(project_id=project.id, url=url, user_name="MuseG"))
    return GetAssetsResponse(assets=assets, count=len(assets))

class GetUserInfoResponse(BaseModel):
    username: str
    subscription_tier: str
    credit_balance: int
    n_projects: int

@app.get("/user/info", status_code=200)
async def get_user_info(
    user_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
) -> GetUserInfoResponse:
    user = await user_dal.get_user_by(filter=(User.id == user_id))
    # TODO: should it be all projects or only projects with completed textures
    projects = await project_dal.get_all_projects_by(filter=(Project.user_id == user_id))
    return GetUserInfoResponse(username=user.username, subscription_tier=user.subscription_tier, credit_balance=user.credit_balance, n_projects=len(projects))

@app.post("/image/create", status_code=202)
async def create_image(
    req: RequestCreateImage,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
):
    project_id = str(uuid.uuid4())
    image_id = str(uuid.uuid4())

    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)

    user = await user_dal.get_user_by(filter=(User.username == "MuseG")) # temp
    response = await user_dal.charge_credit(user, 2, "user_action:generate_image")
    if response.success == False:
        return JSONResponse(status_code=400, content={"success": False, "message": "Not enough credits"})
    
    await project_dal.create_project(id=project_id, name="test", user_id=user.id)

    await image_dal.create_image(id=image_id, prompt=req.prompt, project_id=project_id)

    msg_id = await stream.send_msg(RedisPayload(project_id, "generate_image", {** req.model_dump(), "project_id": project_id, "image_id": image_id}))

    return JSONResponse(status_code=202, content={"success": True, "image_id": image_id, "project_id": project_id})

@app.post("/image/{project_id}/edit", status_code=202)
async def edit_image(
    req: RequestEditImage,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
):
    stream = RedisStream("requested-jobs")
    image_id = str(uuid.uuid4())
    await stream.setup_group(new_only=False)
    
    user = await user_dal.get_user_by(filter=(User.username == "MuseG")) # temp
    response = await user_dal.charge_credit(user, 2, "user_action:edit_image")
    if response.success == False:
        return JSONResponse(status_code=400, content={"success": False, "message": "Not enough credits"})

    project = await project_dal.get_project_by_id(req.project_id)
    if project is None:
        return JSONResponse(status_code=400, content={"success": False, "message": "Project doesn't exist"})

    msg_id = await stream.send_msg(RedisPayload(project_id, "edit_image", {**req.model_dump(), "project_id": req.project_id, "image_id": image_id}))

    await image_dal.create_image(id=image_id, prompt=req.prompt, project_id=project_id, original_image_id=req.original_image_id)
    
    return JSONResponse(status_code=202, content={"success": True, "project_id": req.project_id, "image_id": image_id})

@app.get("/image/{project_id}/chats", status_code=200)
async def get_image_chat_history(
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal)
):
    response = await project_dal.get_image_prompt_chats(project_id)
    return response

mesh_quality_multiplier = {
    "low": 1,
    "medium": 2,
    "high": 3
}

texture_quality_multiplier = {
    "normal": 2,
    "precise": 4,
    "stylized": 4
}

def calculate_mesh_gen_cost(n_meshes, quality, labels):
    quality_multiplier = mesh_quality_multiplier[quality]
    cost = (n_meshes * quality_multiplier) + len(labels)
    return cost

def calculate_texture_gen_cost(prompt, texture_quality):
    quality_multiplier = texture_quality_multiplier[texture_quality]
    cost = quality_multiplier
    return cost

@app.post("/mesh/{project_id}/mesh_cost", status_code=200)
async def api_calculate_mesh_gen_cost(
    req: RequestCalculateMeshGenCost,
    project_id: str
) -> ResponseCalculateMeshGenCost:
    cost = calculate_mesh_gen_cost(req.n_meshes, req.quality, req.labels)
    return JSONResponse(status_code=200, content={"cost": cost})

@app.post("/mesh/{project_id}/texture_cost", status_code=200)
async def api_calculate_mesh_gen_cost(
    req: RequestCalculateTextureGenCost,
    project_id: str
) -> ResponseCalculateMeshGenCost:
    cost = calculate_texture_gen_cost(req.prompt, req.texture_quality)
    return JSONResponse(status_code=200, content={"cost": cost})

@app.post("/mesh/{project_id}/create", status_code=202)
async def create_mesh(
    req: RequestCreateMesh,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
):
    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)

    user = await user_dal.get_user_by(filter=(User.username == "MuseG")) # temp
    
    mesh_cost = calculate_mesh_gen_cost(req.n_meshes, req.quality, req.labels)
    response = await user_dal.charge_credit(user, mesh_cost, "user_action:generate_mesh")
    if response.success == False:
        return JSONResponse(status_code=400, content={"success": False, "message": "Not enough credits"})

    msg_id = await stream.send_msg(RedisPayload(project_id, "generate_mesh", {** req.model_dump()}))

    return {"image_id": req.image_id, "project_id": project_id}

@app.post("/mesh/{project_id}/texture", status_code=202)
async def create_texture(
    req: RequestCreateTexture,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
):
    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)

    user = await user_dal.get_user_by(filter=(User.username == "MuseG")) # temp
    
    texture_cost = calculate_texture_gen_cost(req.prompt, req.texture_quality)
    response = await user_dal.charge_credit(user, texture_cost, "user_action:generate_texture")
    if response.success == False:
        return JSONResponse(status_code=400, content={"success": False, "message": "Not enough credits"})

    msg_id = await stream.send_msg(RedisPayload(project_id, "generate_texture", {** req.model_dump()}))

    return {"image_id": req.image_id, "project_id": project_id}

@app.post("/image/elaborate", status_code=200)
async def gen_elaborating_questions(
    req: RequestGetElaboratingQuestions,
    project_dal: ProjectDAL = Depends(get_project_dal)
):
    
    # stream = RedisStream("requested-jobs")
    # await stream.setup_group(new_only=False)

    # project = await project_dal.get_project_by_id(req.project_id)
    # if project is None:
    #     raise HTTPException(400, detail="Invalid Project")
    
    # TODO: cache this in redis to reduce openai calls
    questions = get_elaborating_questions(project_id=req.project_id, current_prompt=req.prompt, image_id=req.image_id)
    
    return {"questions": questions}

    # await stream.send_msg(RedisPayload(req.project_id, "edit_image", req.model_dump()))

    # return {"project_id": req.project_id}

@app.post("/image/check_elaborate", status_code=200)
async def post_check_elaborating_questions(
    req: RequestCheckElaboratingQuestions,
    project_dal: ProjectDAL = Depends(get_project_dal)
):
    questions = check_elaborating_questions(current_prompt=req.prompt, elaborating_questions=req.elaborating_questions)
    
    if len(questions) <= 1 and len(req.prompt) < 256:
        questions = get_elaborating_questions(None, req.prompt, None)
    return {"questions": questions}