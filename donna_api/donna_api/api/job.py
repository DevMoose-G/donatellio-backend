from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from rq.job import JobStatus

from donna_api.auth import get_current_user
from donna_common.redis.rq import RedisQueue
from donna_common.redis.types import JobUpdate

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/job")


@router.get("/{job_id}", status_code=200)
async def get_job(job_id: str, current_user=Depends(get_current_user)):
    job_update = RedisQueue().get_job_update(job_id)
    return job_update


class GetJobUpdates(BaseModel):
    updates: List[JobUpdate]


@router.get("/mesh/{mesh_id}", status_code=200)
async def get_all_pending_jobs_for_mesh(mesh_id: str, status: Optional[str] = None, current_user=Depends(get_current_user)):
    updates = RedisQueue().get_job_updates_by_mesh_id(mesh_id)
    print(f"Number of updates {len(updates)}")
    filtered_updates = updates
    statuses = []
    if (status != None):
        if status.lower() == "failed":
            statuses.append(JobStatus.FAILED)
        elif status.lower() == "finished":
            statuses.append(JobStatus.FINISHED)
        elif status.lower() == "pending":
            statuses.append(JobStatus.STARTED)
            statuses.append(JobStatus.QUEUED)
        elif status.lower() == "started":
            statuses.append(JobStatus.STARTED)
        filtered_updates = [update for update in filtered_updates if update.status in statuses]
    return GetJobUpdates(updates=filtered_updates)

@router.get("/texture/{texture_id}", status_code=200)
async def get_all_pending_jobs_for_texture(texture_id: str, status: Optional[str] = None, current_user=Depends(get_current_user)):
    updates = RedisQueue().get_job_updates_by_texture_id(texture_id)
    print(f"Number of updates {len(updates)}")
    filtered_updates = updates
    statuses = []
    if (status != None):
        if status.lower() == "failed":
            statuses.append(JobStatus.FAILED)
        elif status.lower() == "finished":
            statuses.append(JobStatus.FINISHED)
        elif status.lower() == "pending":
            statuses.append(JobStatus.STARTED)
            statuses.append(JobStatus.QUEUED)
        elif status.lower() == "started":
            statuses.append(JobStatus.STARTED)
        filtered_updates = [update for update in filtered_updates if update.status in statuses]
    return GetJobUpdates(updates=filtered_updates)


@router.get("/image/{image_id}", status_code=200)
async def get_all_pending_jobs_for_image(image_id: str, status: Optional[str] = None, current_user=Depends(get_current_user)):
    updates = RedisQueue().get_job_updates_by_image_id(image_id)
    print(f"Number of updates {len(updates)}")
    # non_failed_jobs = [
    #     update for update in updates if update.status != JobStatus.FAILED
    # ]
    filtered_updates = updates
    statuses = []
    if (status != None):
        if status.lower() == "failed":
            statuses.append(JobStatus.FAILED)
        elif status.lower() == "finished":
            statuses.append(JobStatus.FINISHED)
        elif status.lower() == "pending":
            statuses.append(JobStatus.STARTED)
            statuses.append(JobStatus.QUEUED)
        else:
            # TODO: add other statuses
            raise Exception("Invalid status")
        filtered_updates = [update for update in filtered_updates if update.status in statuses]
    return GetJobUpdates(updates=filtered_updates)
