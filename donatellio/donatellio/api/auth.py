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

@router.post("/register")
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

@router.post("/login")
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
