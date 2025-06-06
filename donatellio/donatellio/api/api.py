import asyncio
from datetime import datetime
from hmac import HMAC
import json
from typing import List, Optional
import uuid

from fastapi import APIRouter, FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession
import requests

from donatellio.api.types import AssetDisplay, BaseResponse, GetAssetsResponse, GetProjectsResponse, ItemImagePromptChat, ProjectDisplay, RequestCalculateMeshGenCost, RequestCalculateTextureGenCost, RequestCheckElaboratingQuestions, RequestCreateImage, RequestCreateMesh, RequestCreateTexture, RequestCreateUser, RequestEditImage, RequestGetElaboratingQuestions, RequestLoginUser, ResponseCalculateMeshGenCost, WSImageEditsResponse, WSImageItem, WSMeshItem, WSMeshResponse
from donatellio.orm.dal.credit_transaction import CreditTransactionDAL, get_credit_transaction_dal
from donatellio.workers.image import check_elaborating_questions, get_elaborating_questions
from donatellio.providers.storage import StorageProvider, extract_s3_key
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
from donatellio.api.auth import get_current_user, router as auth_router
from donatellio.api.collections import router as collections_router
from donatellio.api.user import router as user_router
from donatellio.api.image import router as image_router
load_dotenv()    # reads .env from cwd

router = APIRouter(prefix="/api")

router.include_router(collections_router)
router.include_router(user_router)
router.include_router(image_router)

# add a project  info endpoint or just include it in websockets?

@router.get("/market/assets", status_code=200)
async def get_market_assets(limit: int, project_dal: ProjectDAL = Depends(get_project_dal), current_user: User = Depends(get_current_user)) -> GetAssetsResponse:
    projects = [project for project in await project_dal.get_all_projects_by(filter=((Project.user_id != current_user.id) & (Project.public))) if project.meshes != []]
    assets = []
    for i in range(min(limit, len(projects))):
        project = projects[i]
        asset_display = await project_dal.get_asset_display(project)
        if asset_display != None: # skip unfinished projects
            assets.append(asset_display)
    return GetAssetsResponse(assets=assets, count=len(assets))
    
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

@router.post("/mesh/{project_id}/mesh_cost", status_code=200)
async def api_calculate_mesh_gen_cost(
    req: RequestCalculateMeshGenCost,
    project_id: str,
    current_user: User = Depends(get_current_user)
) -> ResponseCalculateMeshGenCost:
    cost = calculate_mesh_gen_cost(req.n_meshes, req.quality, req.labels)
    return JSONResponse(status_code=200, content={"cost": cost})

@router.post("/mesh/{project_id}/texture_cost", status_code=200)
async def api_calculate_mesh_gen_cost(
    req: RequestCalculateTextureGenCost,
    project_id: str,
    current_user: User = Depends(get_current_user)
) -> ResponseCalculateMeshGenCost:
    cost = calculate_texture_gen_cost(req.prompt, req.texture_quality)
    return JSONResponse(status_code=200, content={"cost": cost})

@router.post("/mesh/{project_id}/create", status_code=202)
async def create_mesh(
    req: RequestCreateMesh,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    current_user: User = Depends(get_current_user)
):
    # TODO: should i have a check here if the user is the owner of the project
    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)
    
    mesh_cost = calculate_mesh_gen_cost(req.n_meshes, req.quality, req.labels)
    response = await user_dal.charge_credit(current_user, mesh_cost, "user_action:generate_mesh")
    if response.success == False:
        return BaseResponse(success=False, message="Not enough credits")

    msg_id = await stream.send_msg(RedisPayload(project_id, "generate_mesh", {** req.model_dump()}))

    return {"image_id": req.image_id, "project_id": project_id}

@router.post("/mesh/{project_id}/texture", status_code=202)
async def create_texture(
    req: RequestCreateTexture,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    current_user: User = Depends(get_current_user)
):
    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)
    
    texture_cost = calculate_texture_gen_cost(req.prompt, req.texture_quality)
    response = await user_dal.charge_credit(current_user, texture_cost, "user_action:generate_texture")
    if response.success == False:
        return BaseResponse(success=False, message="Not enough credits")

    msg_id = await stream.send_msg(RedisPayload(project_id, "generate_texture", {** req.model_dump()}))

    return {"image_id": req.image_id, "project_id": project_id}

@router.delete("/project/{project_id}", status_code=200)
async def delete_project(
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user)
):
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        return BaseResponse(success=False, message="You don't have permission to delete this project")
    await project_dal.hard_delete_project(project.id)
    # new_proj = await project_dal.session.refresh(project)
    # breakpoint()
    return {"success": True}