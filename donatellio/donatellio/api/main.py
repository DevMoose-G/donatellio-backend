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
from donatellio.api.auth import get_current_user, router as auth_router
from donatellio.api.api import router as api_router
load_dotenv()    # reads .env from cwd

# Initialize FastAPI
app = FastAPI()

app.include_router(websocket_router)
app.include_router(auth_router)
app.include_router(api_router)

# allow local react to interact with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # CRA’s default
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Serve all files under ./static at the /static URL path
app.mount("/static", StaticFiles(directory="static"), name="static")
