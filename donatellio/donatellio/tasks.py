import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from donatellio.orm.main import AsyncSessionLocal
from donatellio.models import InferenceJob
from donatellio.providers.factory import get_provider

logger = logging.getLogger(__name__)


def run_custom_inference(job_id: str, image: str, payload: dict, provider_name: str):
    """
    RQ task entrypoint: wraps the async inference workflow.
    """
    asyncio.run(_run(job_id, image, payload, provider_name))


async def _run(job_id: str, image: str, payload: dict, provider_name: str):
    """
    Orchestrates GPU spin-up, inference, persistence, and teardown.
    Updates job status in Postgres throughout.
    """
    try:
        # 1. Mark job as running
        async with AsyncSessionLocal() as session:
            job = await session.get(InferenceJob, job_id)
            job.status = "running"
            await session.commit()

        # 2. Spin up GPU instance
        provider = get_provider(provider_name)
        instance_id = provider.start_instance(image)
        provider.wait_until_ready(instance_id)

        # 3. Perform inference
        response = provider.run_inference(instance_id, payload)

        # 4. Tear down GPU instance
        provider.stop_instance(instance_id)

        # 5. Persist successful response
        async with AsyncSessionLocal() as session:
            job = await session.get(InferenceJob, job_id)
            job.response = response
            job.status = "completed"
            await session.commit()

    except Exception as e:
        logger.exception(f"Custom inference failed for job {job_id}")
        # Persist failure state
        async with AsyncSessionLocal() as session:
            job = await session.get(InferenceJob, job_id)
            job.response = {"error": str(e)}
            job.status = "failed"
            await session.commit()
