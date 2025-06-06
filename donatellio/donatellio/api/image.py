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
from donatellio.orm.dal.collection import CollectionDAL, get_collection_dal
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

router = APIRouter(prefix="/image")

class ResponseImage(BaseResponse):
    image_id: str
    project_id: str

@router.post("/create", status_code=202)
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

@router.post("/{project_id}/edit", status_code=202)
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

@router.get("/{project_id}/chats", status_code=200)
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

@router.get("/presign", status_code=202)
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

@router.post("/upload", status_code=202)
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


@router.post("/elaborate", status_code=200)
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

@router.post("/check_elaborate", status_code=200)
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