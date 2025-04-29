import asyncio
from hmac import HMAC
import json
import uuid

from fastapi import FastAPI, Depends, HTTPException, WebSocket
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

import requests

from donatellio.hashing import get_password_hash
from donatellio.orm.models.user import User
from donatellio.orm.dal.image import ImageDAL, get_image_dal
from donatellio.orm.dal.user import UserDAL, get_user_dal
from donatellio.redisstream import RedisMessage, RedisPayload, RedisStream

from donatellio.orm.main import AsyncSessionLocal, get_db
from donatellio.models import InferenceJob
from donatellio.tasks import run_custom_inference

from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

# Initialize FastAPI
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # CRA’s default
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

class CreateImageRequest(BaseModel):
    prompt: str
    n: int
    size: str
    quality: str

class EditImageRequest(BaseModel):
    original_image_url: str
    job_id: str
    prompt: str
    n: int
    size: str
    quality: str

class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str

def sign_payload(payload):
    # signature = HMAC(secret, body, SHA256)
    pass

# Serve all files under ./static at the /static URL path
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/register")
async def register(user: CreateUserRequest, db: AsyncSession = Depends(get_db)):
    db_user = await db.execute(
        select(User).where((User.username == user.username) | (User.email == user.email))
        # db.query(User).filter(
        #     (User.username == user.username) | (User.email == user.email)
        # )
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

@app.websocket("/ws/jobs/{job_id}")
async def job_updates(websocket: WebSocket, job_id: str):
    await websocket.accept()
    stream = RedisStream("completed-jobs")
    await stream.setup_group(new_only=False)
    while True:
        response = await stream.consume_msg("consumer1", new_only=True, n_msgs=1)
        if len(response.messages) == 0:
            await asyncio.sleep(2)
            continue
        msg = response.messages[0]
        payload = json.loads(msg.json.payload)
        if msg.json.job_id == job_id:
            if msg.json.function_name == "generate_image":
                await websocket.send_json(payload)
                await stream.ack_msg(msg.id)
                break
    
    await websocket.close()

@app.post("/image/create", status_code=202)
async def create_image(
    req: CreateImageRequest,
    image_dal: ImageDAL = Depends(get_image_dal)
):
    """
    Proxy endpoint for OpenAI ChatCompletion.
    Saves request+response to Postgres.
    """
    job_id = str(uuid.uuid4())
    # Persist to DB
    # job = InferenceJob(
    #     id=job_id,
    #     payload=req.model_dump(),
    #     status="queued"
    # )
    # db.add(job)
    # await db.commit()

    stream = RedisStream("image-jobs")
    await stream.setup_group(new_only=False)

    msg_id = await stream.send_msg(RedisPayload(job_id, "generate_image", req.model_dump()))

    return {"job_id": job_id}


@app.post("/image/edit", status_code=202)
async def edit_image(
    req: EditImageRequest,
    image_dal: ImageDAL = Depends(get_image_dal)
):
    """
    Proxy endpoint for OpenAI ChatCompletion.
    Saves request+response to Postgres.
    """
    # Persist to DB
    # job = InferenceJob(
    #     id=job_id,
    #     payload=req.model_dump(),
    #     status="queued"
    # )
    # db.add(job)
    # await db.commit()

    stream = RedisStream("image-jobs")
    await stream.setup_group(new_only=False)

    msg_id = await stream.send_msg(RedisPayload(req.job_id, "edit_image", req.model_dump()))

    return {"job_id": req.job_id}