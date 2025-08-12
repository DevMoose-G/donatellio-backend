import time
from datetime import datetime
from typing import List

from redis import Redis
from rq import Queue, requeue_job, get_current_job, Retry
import rq
from rq.job import Job

from rq.timeouts import JobTimeoutException
from rq.registry import FailedJobRegistry

from donna_common.redis.types import JobUpdate
from donna_common.settings import settings

# Define a failure callback to catch timeouts
def handle_failure(job, connection, exc_type, exc_value, tb):
    if exc_type is JobTimeoutException:
        # Requeue the timed-out job at the tail
        requeue_job(job.id, connection)

class RedisQueue:
    def __init__(self):
        self.redis = Redis.from_url(settings.redis_url)
        self.queue = Queue("jobs", connection=self.redis, default_timeout=900)  # 15 minutes


    def queue_action(self, func_callback: str, expected_at: datetime, **kwargs) -> str:
        """
        Queue an action to be processed by the worker.
        Returns the job ID.
        """
        # expires in 1 day
        job = self.queue.enqueue(
            func_callback, **kwargs, result_ttl=86400,
            retry=Retry(max=3, interval=[60, 120, 300]), # up to 3 retries with backoff
            on_failure=handle_failure
        )
        job.meta.update({"message": "Job has been queued", "expected_at": expected_at})
        job.save_meta()
        return job.id

        # redis_conn.zremrangebyrank(f"jobs_by_mesh:{mesh_id}", 0, -1000)
        # # keep only the 1,000 most recent jobs

    def queue_mesh_action(
        self, func_callback: str, expected_at: datetime, mesh_id: str, message: str, **kwargs
    ) -> str:
        job_id = self.queue_action(
            func_callback=func_callback,
            expected_at=expected_at,
            mesh_id=mesh_id,
            **kwargs,
        )
        self.update_job(job_id, message)
        self.redis.zadd(f"jobs_by_mesh_id:{mesh_id}", {job_id: time.time()})
        return job_id

    def queue_image_action(
        self, func_callback: str, expected_at: datetime, image_id: str, message: str, **kwargs
    ) -> str:
        job_id = self.queue_action(
            func_callback=func_callback,
            expected_at=expected_at,
            image_id=image_id,
            **kwargs,
        )
        self.update_job(job_id, message)
        self.redis.zadd(f"jobs_by_image_id:{image_id}", {job_id: time.time()})
        return job_id

    def queue_texture_action(
        self, func_callback: str, expected_at: datetime, texture_id: str, message: str, **kwargs
    ) -> str:
        job_id = self.queue_action(
            func_callback=func_callback,
            expected_at=expected_at,
            texture_id=texture_id,
            **kwargs,
        )
        self.update_job(job_id, message)
        self.redis.zadd(f"jobs_by_texture_id:{texture_id}", {job_id: time.time()})
        return job_id

    def get_job_update(self, job_id: str) -> JobUpdate:
        job = Job.fetch(job_id, connection=self.redis)
        return JobUpdate(
            job_id=job_id,
            status=job.get_status(),
            message=job.meta.get("message", "No message"),
            expected_at=job.meta.get("expected_at", None),
        )

    def update_current_job(self, message: str):
        job = get_current_job()
        job.meta.update({"message": message})
        job.save_meta()
    
    def update_job(self, job_id: str, message: str):
        job = Job.fetch(job_id, connection=self.redis)
        job.meta.update({"message": message})
        job.save_meta()

    def get_job_updates_by_mesh_id(
        self, mesh_id: str, limit: int = 10
    ) -> List[JobUpdate]:
        job_updates = []
        for job_id in self.redis.zrevrange(f"jobs_by_mesh_id:{mesh_id}", 0, limit - 1):
            try:
                job_updates.append(self.get_job_update(job_id.decode("utf-8")))
            except rq.exceptions.NoSuchJobError:
                self.redis.zrem(f"jobs_by_mesh_id:{mesh_id}", job_id)
        return job_updates

    def get_job_updates_by_image_id(
        self, image_id: str, limit: int = 10
    ) -> List[JobUpdate]:
        job_updates = []
        for job_id in self.redis.zrevrange(
            f"jobs_by_image_id:{image_id}", 0, limit - 1
        ):
            job_updates.append(self.get_job_update(job_id.decode("utf-8")))
        return job_updates

    def get_job_updates_by_texture_id(
        self, texture_id, limit: int = 10
    ) -> List[JobUpdate]:
        job_updates = []
        for job_id in self.redis.zrevrange(
            f"jobs_by_texture_id:{texture_id}", 0, limit - 1
        ):
            try:
                job_updates.append(self.get_job_update(job_id.decode("utf-8")))
            except rq.exceptions.NoSuchJobError:
                self.redis.zrem(f"jobs_by_texture_id:{texture_id}", job_id)
        
        return job_updates