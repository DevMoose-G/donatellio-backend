from typing import List, Optional
import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from rq.job import JobStatus

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
from donna_common.redis.rq import RedisQueue
from donna_common.redis.types import ImageAction, JobUpdate

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/job")

@router.get("/{job_id}", status_code=200)
async def get_job(job_id: str):
    job_update = RedisQueue().get_job_update(job_id)
    return job_update

class GetJobUpdates(BaseModel):
    updates: List[JobUpdate]

@router.get("/mesh/{mesh_id}", status_code=200)
async def get_all_pending_jobs_for_mesh(mesh_id: str):
    updates = RedisQueue().get_job_updates_by_mesh_id(mesh_id)
    print(f"Number of updates {len(updates)}")
    non_failed_jobs = [update for update in updates if update.status != JobStatus.FAILED]
    return GetJobUpdates(
        updates=non_failed_jobs
    )

@router.get("/image/{image_id}", status_code=200)
async def get_all_pending_jobs_for_image(image_id: str):
    updates = RedisQueue().get_job_updates_by_image_id(image_id)
    print(f"Number of updates {len(updates)}")
    non_failed_jobs = [update for update in updates if update.status != JobStatus.FAILED]
    return GetJobUpdates(
        updates=non_failed_jobs
    )
