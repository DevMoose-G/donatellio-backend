from rq import Queue
from redis import Redis
from rq.job import Job
from pydantic import BaseModel

from donna_common.redis.types import BaseAction, JobUpdate
from donna_common.settings import settings

from typing import Callable


class RedisQueue:
    def __init__(self):
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
        self.queue = Queue("jobs", connection=self.redis)
    
    def queue_action(self, func_callback: str, **kwargs) -> str:
        """
        Queue an action to be processed by the worker.
        Returns the job ID.
        """
        job = self.queue.enqueue(func_callback, **kwargs)
        job.meta.update({
            "message": "Job has been queued"
        })
        job.save_meta()
        return job.id
    
    def get_job_update(self, job_id: str) -> JobUpdate:
        job = Job.fetch(job_id, connection=self.redis)
        return JobUpdate(
            job_id=job_id,
            status=job.get_status(),
            message=job.meta.get("message", "No message")
        )