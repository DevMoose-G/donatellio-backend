import runpod
from donatellio.providers.storage import StorageProvider
from donatellio.orm.dal.image import ImageDAL
from donatellio.orm.dal.project import ProjectDAL
from donatellio.orm.dal.mesh import MeshDAL
from donatellio.orm.main import AsyncSessionLocal
from donatellio.orm.models.image import Image
from donatellio.orm.models.project import Project
from donatellio.settings import settings
import asyncio
import aiohttp
import os
from runpod import AsyncioEndpoint, AsyncioJob
from urllib.parse import urlparse

class RunpodProvider:
    def __init__(self):
        runpod.api_key = settings.runpod_api_key
        self.endpoint_id = "sp98vhbopbrqtt"
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # For Windows users.

    async def generate_mesh(self, project_id: str, image_id: str, mesh_id: str, presigned_url: str):
        async with aiohttp.ClientSession() as runpod_session:

            # create mesh in database w/ status='PENDING'
            async with AsyncSessionLocal() as session:
                image = await ImageDAL(session).get_image_by_id(image_id)
                project = await ProjectDAL(session).get_project_by_id(project_id)
                assert image is not None
                assert project is not None
                await MeshDAL(session).create_mesh(id=mesh_id, project_id=project.id, image_id=image.id)
            
            storage_provider = StorageProvider()
            image_url = storage_provider.generate_get_url(image.storage_key)
            input_payload = {"image_url": image_url, "presigned_urls": [presigned_url]}
            endpoint = AsyncioEndpoint(self.endpoint_id, runpod_session)
            job: AsyncioJob = await endpoint.run(input_payload)

            # Polling job status
            while True:
                status = await job.status()
                print(f"Current job status: {status}")
                if status == "COMPLETED":
                    output = await job.output()
                    parsed_url = urlparse(presigned_url)

                    async with AsyncSessionLocal() as session:
                        await MeshDAL(session).update_mesh(id=mesh_id, storage_key=parsed_url.path[1:], status="COMPLETED", gpu_provider_response=str(output))

                    print("Job output:", output)
                    break  # Exit the loop once the job is completed.
                elif status in ["FAILED"]:
                    output = await job.output()
                    print("Job failed or encountered an error.")
                    await MeshDAL(session).update_mesh(id=mesh_id, status="FAILED", gpu_provider_response=str(output))
                    break
                else:
                    print("Job in queue or processing. Waiting 3 seconds...")
                    await asyncio.sleep(3) 