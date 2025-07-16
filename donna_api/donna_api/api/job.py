from typing import Optional
import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.types import (
    RequestCheckElaboratingQuestions,
    RequestCreateImage,
    RequestEditImage,
    RequestGetElaboratingQuestions,
    WSImageItem,
)
from donna_api.utils import image_cost
from donna_common.orm import (
    ImageDAL,
    ProjectDAL,
    UserDAL,
    get_image_dal,
    get_project_dal,
    get_user_dal,
)
from donna_common.orm.dal.project_branch import ProjectBranchDAL, get_project_branch_dal
from donna_common.orm.dal.styleboard import StyleBoardDAL, get_styleboard_dal
from donna_common.orm.models.user import User
from donna_common.providers.openai import OpenAIProvider
from donna_common.providers.storage import StorageProvider, extract_s3_key
from donna_common.redis.redisstream import RedisStream, redis
from donna_common.redis.types import ImageAction, JobUpdate

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/job")

@router.get("/{job_id}", status_code=200)
async def get_job(job_id: str):
    job_update_str = redis.get(f"job:{job_id}")
    if not job_update_str:
        return JSONResponse(
            status_code=404,
            content={"error_msg": "Job not found"}
        )
    job_update = JobUpdate.model_validate_json(
        job_update_str.decode("utf-8")
    )
    return JSONResponse(content=job_update.model_dump())

@router.get("/mesh/{mesh_id}", status_code=200)
async def get_all_job_for_mesh(mesh_id: str):
    stream = RedisStream("requested-jobs")
    await stream.setup_group(new_only=False)
    messages = await stream.get_jobs_by_mesh_id(mesh_id)
    if not messages:
        return JSONResponse(
            status_code=404,
            content={"error_msg": "No jobs found for this mesh"}
        )
    raise NotImplementedError("This endpoint is not implemented yet")