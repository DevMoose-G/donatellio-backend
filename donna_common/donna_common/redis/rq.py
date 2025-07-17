from datetime import datetime, timedelta, timezone
import time
from rq import Queue
from redis import Redis
from rq.job import Job
from pydantic import BaseModel

from donna_common.redis.types import BaseAction, JobUpdate
from donna_common.settings import settings

from typing import Callable, List


class RedisQueue:
    def __init__(self):
        self.redis = Redis.from_url(settings.redis_url)
        self.queue = Queue("jobs", connection=self.redis)
    
    def queue_action(self, func_callback: str, expected_at: datetime, **kwargs) -> str:
        """
        Queue an action to be processed by the worker.
        Returns the job ID.
        """
        # expires in 1 day
        job = self.queue.enqueue(func_callback, **kwargs, result_ttl=86400, job_timeout=900)
        job.meta.update({
            "message": "Job has been queued",
            "expected_at": expected_at
        })
        job.save_meta()
        return job.id
    
        # redis_conn.zremrangebyrank(f"jobs_by_mesh:{mesh_id}", 0, -1000)  
        # # keep only the 1,000 most recent jobs
    
    def queue_mesh_action(self, func_callback: str, expected_at: datetime, mesh_id: str, **kwargs) -> str:
        job_id = self.queue_action(
            func_callback=func_callback,
            expected_at=expected_at,
            mesh_id=mesh_id,
            **kwargs
        )
        self.redis.zadd(f"jobs_by_mesh_id:{mesh_id}", { job_id: time.time() })
        return job_id
    
    def queue_image_action(self, func_callback: str, expected_at: datetime, image_id: str, **kwargs) -> str:
        job_id = self.queue_action(
            func_callback=func_callback,
            expected_at=expected_at,
            image_id=image_id,
            **kwargs
        )
        self.redis.zadd(f"jobs_by_image_id:{image_id}", { job_id: time.time() })
        return job_id
    
    def queue_texture_action(self, func_callback: str, expected_at: datetime, texture_id: str, **kwargs) -> str:
        job_id = self.queue_action(
            func_callback=func_callback,
            expected_at=expected_at,
            texture_id=texture_id,
            **kwargs
        )
        self.redis.zadd(f"jobs_by_texture_id:{texture_id}", { job_id: time.time() })
        return job_id
    
    def get_job_update(self, job_id: str) -> JobUpdate:
        job = Job.fetch(job_id, connection=self.redis)
        return JobUpdate(
            job_id=job_id,
            status=job.get_status(),
            message=job.meta.get("message", "No message"),
            expected_at=job.meta.get("expected_at", None)
        )
    
    def update_job(self, job_id: str, message: str):
        job = Job.fetch(job_id, connection=self.redis)
        job.meta.update({"message": message})
        job.save_meta()
    
    def get_job_updates_by_mesh_id(self, mesh_id: str, limit: int = 10) -> List[JobUpdate]:
        job_updates = []
        for job_id in self.redis.zrevrange(f"jobs_by_mesh_id:{mesh_id}", 0, limit - 1):
            job_updates.append(self.get_job_update(job_id.decode("utf-8")))
        return job_updates
    
    def get_job_updates_by_image_id(self, image_id: str, limit: int = 10) -> List[JobUpdate]:
        job_updates = []
        for job_id in self.redis.zrevrange(f"jobs_by_image_id:{image_id}", 0, limit - 1):
            job_updates.append(self.get_job_update(job_id.decode("utf-8")))
        return job_updates