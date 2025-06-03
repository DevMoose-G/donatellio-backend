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
load_dotenv()    # reads .env from cwd

router = APIRouter(prefix="/api")

@router.get("/market/assets", status_code=200)
async def get_market_assets(limit: int, project_dal: ProjectDAL = Depends(get_project_dal), current_user: User = Depends(get_current_user)) -> GetAssetsResponse:
    projects = [project for project in await project_dal.get_all_projects_by(filter=(Project.user_id != current_user.id)) if project.meshes != []]
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

@router.get("/user/projects", status_code=200)
async def get_users_projects(limit: int, project_dal: ProjectDAL = Depends(get_project_dal), current_user: User = Depends(get_current_user)) -> GetProjectsResponse:
    projects = [project for project in await project_dal.get_all_projects_by(filter=(Project.user_id == current_user.id)) if project.textures == []] 
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

@router.get("/user/assets", status_code=200)
async def get_users_assets(limit: int, project_dal: ProjectDAL = Depends(get_project_dal), current_user: User = Depends(get_current_user)) -> GetAssetsResponse:
    
    projects = [project for project in await project_dal.get_all_projects_by(filter=(Project.user_id == current_user.id)) if project.textures != []] 
    assets = []
    for i in range(min(limit, len(projects))):
        project = projects[i]
        storage_provider = StorageProvider()

        uploaded_textures = await project_dal.get_uploaded_textures(project_id=project.id)
        if uploaded_textures == []:
            continue
        url = storage_provider.generate_get_url(uploaded_textures[-1].storage_key)
        assets.append(AssetDisplay(project_id=project.id, url=url, user_name="MuseG"))
    return GetAssetsResponse(assets=assets, count=len(assets))

class NotificationSettings(BaseModel):
    low_credits: bool
    monthly_credits: bool
    product_updates: bool
    promotions: bool

class GetSettingsResponse(BaseModel):
    username: str
    light_mode: bool
    notifications: NotificationSettings

@router.get("/user/settings", status_code=200)
async def get_user_settings(
    current_user: User = Depends(get_current_user)
) -> GetSettingsResponse:
    notifications = NotificationSettings(low_credits=current_user.notification_low_credits, monthly_credits=current_user.notification_monthly_credits, product_updates=current_user.notification_product_updates, promotions=current_user.notification_promotions)
    return GetSettingsResponse(username=current_user.username, light_mode=current_user.light_mode, notifications=notifications)

class RequestUpdateSettings(BaseModel):
    username: Optional[str] = None
    light_mode: Optional[bool] = None
    notifications: Optional[NotificationSettings] = None

@router.post("/user/settings", status_code=200)
async def update_user_settings(
    req: RequestUpdateSettings,
    user_dal: UserDAL = Depends(get_user_dal),
    current_user: User = Depends(get_current_user)
) -> None:
    if req.username != None:
        await user_dal.update_user(current_user.id, username=req.username)
    if req.light_mode != None:
        await user_dal.update_user(current_user.id, light_mode=req.light_mode)
    if req.notifications != None:
        await user_dal.update_user(
            current_user.id, 
            notification_low_credits=req.notifications.low_credits, 
            notification_monthly_credits=req.notifications.monthly_credits, 
            notification_product_updates=req.notifications.product_updates, 
            notification_promotions=req.notifications.promotions
        )
    current_user = await user_dal.get_user_by_id(current_user.id)
    notifications = NotificationSettings(low_credits=current_user.notification_low_credits, monthly_credits=current_user.notification_monthly_credits, product_updates=current_user.notification_product_updates, promotions=current_user.notification_promotions)
    return GetSettingsResponse(username=current_user.username, light_mode=current_user.light_mode, notifications=notifications)

class GetUserInfoResponse(BaseModel):
    username: str
    subscription_tier: str
    credit_balance: int
    n_projects: int

@router.get("/user/info", status_code=200)
async def get_user_info(
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user)
) -> GetUserInfoResponse:
    # TODO: should it be all projects or only projects with completed textures
    projects = await project_dal.get_all_projects_by(filter=(Project.user_id == current_user.id))
    return GetUserInfoResponse(username=current_user.username, subscription_tier=current_user.subscription_tier, credit_balance=current_user.credit_balance, n_projects=len(projects))

class ItemCreditTransaction(BaseModel):
    description: str
    amount: int
    created_at: datetime

class ResponseCreditTransactions(BaseModel):
    success: bool
    transactions: List[ItemCreditTransaction]

@router.get("/user/transactions", status_code=200)
async def get_user_transactions(
    credit_transaction_dal: CreditTransactionDAL = Depends(get_credit_transaction_dal),
    current_user: User = Depends(get_current_user)
) -> ResponseCreditTransactions:
    transactions = await credit_transaction_dal.get_credit_transactions_by_user_id(current_user.id)
    
    return ResponseCreditTransactions(
        success=True,
        transactions=[ItemCreditTransaction(description=transaction.reason, amount=transaction.delta, created_at=transaction.created_at) for transaction in transactions]
    )
    
class ResponseImage(BaseResponse):
    image_id: str
    project_id: str

@router.post("/image/create", status_code=202)
async def create_image(
    req: RequestCreateImage,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user)
):
    project_id = str(uuid.uuid4())
    image_id = str(uuid.uuid4())

    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)

    response = await user_dal.charge_credit(current_user, 2, "user_action:generate_image")
    if response.success == False:
        return BaseResponse(success=False, message="Not enough credits")
    
    await project_dal.create_project(id=project_id, name="test", user_id=current_user.id)

    await image_dal.create_image(id=image_id, prompt=req.prompt, project_id=project_id)

    msg_id = await stream.send_msg(RedisPayload(project_id, "generate_image", {** req.model_dump(), "project_id": project_id, "image_id": image_id}))

    return JSONResponse(status_code=202, content={"success": True, "image_id": image_id, "project_id": project_id})

@router.post("/image/{project_id}/edit", status_code=202)
async def edit_image(
    req: RequestEditImage,
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user)
):
    stream = RedisStream("requested-jobs")
    image_id = str(uuid.uuid4())
    await stream.setup_group(new_only=False)
    
    response = await user_dal.charge_credit(current_user, 2, "user_action:edit_image")
    if response.success == False:
        return BaseResponse(success=False, message="Not enough credits")

    project = await project_dal.get_project_by_id(req.project_id)
    if project is None:
        return JSONResponse(status_code=400, content={"success": False, "message": "Project doesn't exist"})

    msg_id = await stream.send_msg(RedisPayload(project_id, "edit_image", {**req.model_dump(), "project_id": req.project_id, "image_id": image_id}))

    await image_dal.create_image(id=image_id, prompt=req.prompt, project_id=project_id, original_image_id=req.original_image_id)
    
    return JSONResponse(status_code=202, content={"success": True, "project_id": req.project_id, "image_id": image_id})

@router.get("/image/{project_id}/chats", status_code=200)
async def get_image_chat_history(
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user)
):
    # TODO: should i have a check here if the user is the owner of the project
    project = await project_dal.get_project_by_id(project_id)
    if project is None:
        return JSONResponse(status_code=400, content={"success": False, "message": "Project doesn't exist"})
    response = await project_dal.get_image_prompt_chats(project_id)
    return response

@router.get("/image/presign", status_code=202)
async def get_presigned_url_for_image(
    project_dal: ProjectDAL = Depends(get_project_dal),
    user_dal: UserDAL = Depends(get_user_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user)
):
    storage_provider = StorageProvider()
    image_id = str(uuid.uuid4())
    presigned_url = storage_provider.generate_put_url_for_image(image_id)
    return JSONResponse(status_code=202, content={"presigned_url": presigned_url, "image_id": image_id})

class RequestUploadImage(BaseModel):
    image_id: str
    presigned_url: str

@router.post("/image/upload", status_code=202)
async def upload_image(
    request: RequestUploadImage,
    project_dal: ProjectDAL = Depends(get_project_dal),
    image_dal: ImageDAL = Depends(get_image_dal),
    current_user: User = Depends(get_current_user)
) -> ResponseImage:
    project_id = str(uuid.uuid4())
    project = await project_dal.create_project(id=project_id, name="", user_id=current_user.id)
    storage_key = extract_s3_key(request.presigned_url)
    image = await image_dal.create_image(id=request.image_id, prompt="", project_id=project.id, storage_key=storage_key)
    return ResponseImage(image_id=image.id, project_id=project.id, success=True)

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

@router.post("/image/elaborate", status_code=200)
async def gen_elaborating_questions(
    req: RequestGetElaboratingQuestions,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user)
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

@router.post("/image/check_elaborate", status_code=200)
async def post_check_elaborating_questions(
    req: RequestCheckElaboratingQuestions,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user)
):
    questions = check_elaborating_questions(current_prompt=req.prompt, elaborating_questions=req.elaborating_questions)
    
    # free users only get the initial 3 questions
    if len(questions) <= 1 and len(req.prompt) < 512 and current_user.subscription_tier != "free":
        questions = get_elaborating_questions(None, req.prompt, None)
    return {"questions": questions}