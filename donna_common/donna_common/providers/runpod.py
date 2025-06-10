import asyncio
import uuid
from typing import List
from urllib.parse import urlparse

import aiohttp
import runpod
from pydantic import BaseModel
from runpod import AsyncioEndpoint, AsyncioJob

from donna_common.orm.dal.image import ImageDAL
from donna_common.orm.dal.mesh import MeshDAL
from donna_common.orm.dal.project import ProjectDAL
from donna_common.orm.dal.texture import TextureDAL
from donna_common.orm.main import AsyncSessionLocal
from donna_common.providers.storage import StorageProvider
from donna_common.settings import settings


class JobsStatus(BaseModel):
    completed: int
    failed: int
    inProgress: int
    inQueue: int
    retried: int


class WorkersStatus(BaseModel):
    idle: int
    initializing: int
    ready: int
    running: int
    throttled: int


class EndpointHealth(BaseModel):
    jobs: JobsStatus
    workers: WorkersStatus


class RunpodProvider:
    def __init__(self):
        runpod.api_key = settings.runpod_api_key
        self.endpoint_id = "sp98vhbopbrqtt"
        self.geometry_endpoint_id = "1l903cupb6er9d"
        self.texture_endpoint_id = "3svqlzp0hepfvh"
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )  # For Windows users.

    async def generate_mesh(
        self, project_id: str, image_id: str, mesh_id: str, presigned_url: str
    ):
        async with aiohttp.ClientSession() as runpod_session:
            # create mesh in database w/ status='PENDING'
            async with AsyncSessionLocal() as session:
                image = await ImageDAL(session).get_image_by_id(image_id)
                project = await ProjectDAL(session).get_project_by_id(project_id)
                assert image is not None
                assert project is not None
                await MeshDAL(session).create_mesh(
                    id=mesh_id, project_id=project.id, image_id=image.id
                )

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
                        await MeshDAL(session).update_mesh(
                            id=mesh_id,
                            storage_key=parsed_url.path[1:],
                            status="COMPLETED",
                            gpu_provider_response=str(output),
                        )

                    print("Job output:", output)
                    break  # Exit the loop once the job is completed.
                elif status in ["FAILED"]:
                    output = await job.output()
                    print("Job failed or encountered an error.")
                    await MeshDAL(session).update_mesh(
                        id=mesh_id, status="FAILED", gpu_provider_response=str(output)
                    )
                    break
                else:
                    print("Job in queue or processing. Waiting 3 seconds...")
                    await asyncio.sleep(3)

    async def __wake_up(self, endpoint_id: str):
        async with aiohttp.ClientSession() as runpod_session:
            input_payload = {}
            endpoint = AsyncioEndpoint(endpoint_id, runpod_session)
            await endpoint.run(input_payload)

    async def wake_up_geometry(self):
        health = await self.health(self.geometry_endpoint_id)
        # don't send request if there are jobs in queue
        if health.jobs.inQueue > 0:
            return
        await self.__wake_up(self.geometry_endpoint_id)

    async def wake_up_texture(self):
        health = await self.health(self.texture_endpoint_id)
        # don't send request if there are jobs in queue
        if health.jobs.inQueue > 0:
            return
        await self.__wake_up(self.texture_endpoint_id)

    async def health(self, endpoint_id: str) -> EndpointHealth:
        async with aiohttp.ClientSession() as runpod_session:
            endpoint = AsyncioEndpoint(endpoint_id, runpod_session)
            url = f"{runpod.endpoint_url_base}/{endpoint_id}/health"

            async with runpod_session.get(url, headers=endpoint.headers) as resp:
                health_dict = await resp.json()

            return EndpointHealth(**health_dict)

    # TODO: test if streaming works
    async def generate_untextured_mesh(
        self,
        project_id: str,
        image_id: str,
        mesh_model: str,
        n_meshes: int,
        quality: str,
        seed: int,
        labels: List[str],
        max_polygon_count: int,
    ):
        async with AsyncSessionLocal() as session:
            image = await ImageDAL(session).get_image_by_id(image_id)
            project = await ProjectDAL(session).get_project_by_id(project_id)
            assert image is not None
            assert project is not None

        await self.wake_up_texture()

        # generate presigned url
        storage_provider = StorageProvider()

        mesh_mapping = {}
        for i in range(n_meshes):
            mesh_id = str(uuid.uuid4())
            # create mesh in database w/ status='PENDING'
            async with AsyncSessionLocal() as session:
                await MeshDAL(session).create_mesh(
                    id=mesh_id,
                    project_id=project.id,
                    image_id=image.id,
                    storage_key=None,
                    status="PENDING",
                    gpu_provider_response="",
                )
            # generate the presigned url to send to runpod
            presigned_url = storage_provider.generate_put_url_for_mesh(mesh_id)
            mesh_mapping[mesh_id] = presigned_url

        async with aiohttp.ClientSession() as runpod_session:
            storage_provider = StorageProvider()
            image_url = storage_provider.generate_get_url(image.storage_key)

            quality_dict = {}
            if quality == "low":
                quality_dict = {"n_inference_steps": 30, "octree_resolution": 256}
            elif quality == "medium":
                quality_dict = {"n_inference_steps": 50, "octree_resolution": 384}
            elif quality == "high":
                quality_dict = {"n_inference_steps": 70, "octree_resolution": 512}

            input_payload = {
                "image_url": image_url,
                "mesh_presigned_urls_mapping": mesh_mapping,
                "n_meshes": n_meshes,
                "seed": seed,
                "labels": labels,
                "max_facenum": max_polygon_count,
            }
            input_payload.update(quality_dict)
            input_payload = {k: v for k, v in input_payload.items() if v is not None}

            async with AsyncSessionLocal() as session:
                await MeshDAL(session).update_mesh(
                    id=mesh_id,
                    project_id=project.id,
                    image_id=image.id,
                    seed=seed,
                    octree_resolution=str(quality_dict["octree_resolution"]),
                    num_inference_steps=quality_dict["n_inference_steps"],
                    face_count=max_polygon_count,
                    label=",".join(labels) if len(labels) > 0 else None,
                    # TODO: have to add these to frontend
                    guidance_scale=5.5,
                    mc_level=0.0,
                    caption=None,
                )

            endpoint = AsyncioEndpoint(self.geometry_endpoint_id, runpod_session)
            job: AsyncioJob = await endpoint.run(input_payload)

            # Polling job status
            status = await job.status()
            while status == "IN_QUEUE":
                status = await job.status()
                print(f"Current job status: {status}")
                await asyncio.sleep(3)
            async for output in job.stream():
                mesh_id = output["mesh_id"]
                presigned_url = output["presigned_url"]
                parsed_url = urlparse(presigned_url)
                async with AsyncSessionLocal() as session:
                    await MeshDAL(session).update_mesh(
                        id=mesh_id,
                        storage_key=parsed_url.path[1:],
                        status="COMPLETED",
                        gpu_provider_response=str(output),
                    )
        return list(mesh_mapping.keys())

    async def generate_texture_on_mesh(
        self,
        project_id: str,
        image_id: str,
        mesh_id: str,
        prompt: str,
        texture_quality: str,  # normal, precise, or stylized
        seed: int,
    ):
        texture_id = str(uuid.uuid4())
        # create mesh in database w/ status='PENDING'
        async with AsyncSessionLocal() as session:
            image = await ImageDAL(session).get_image_by_id(image_id)
            mesh = await MeshDAL(session).get_mesh_by_id(mesh_id)
            project = await ProjectDAL(session).get_project_by_id(project_id)
            assert image is not None
            assert project is not None
            assert mesh is not None

            await TextureDAL(session).create_texture(
                id=texture_id,
                project_id=project.id,
                image_id=image.id,
                mesh_id=mesh.id,
                storage_key=None,
                status="PENDING",
                gpu_provider_response="",
            )

        # generate presigned url
        storage_provider = StorageProvider()

        presigned_url = storage_provider.generate_put_url_for_mesh(texture_id)

        async with aiohttp.ClientSession() as runpod_session:
            image_url = storage_provider.generate_get_url(image.storage_key)
            mesh_url = storage_provider.generate_get_url(mesh.storage_key)

            quality_dict = {}
            if texture_quality == "normal":
                quality_dict = {"n_inference_steps": 30, "guidance_scale": 3.0}
            elif texture_quality == "precise":
                quality_dict = {"n_inference_steps": 55, "guidance_scale": 3.0}
            elif texture_quality == "stylized":
                quality_dict = {
                    "n_inference_steps": 50,
                    "guidance_scale": 5.0,
                    "lora_scale": 1.5,
                    "reference_conditioning_scale": 1.5,
                }

            input_payload = {
                "image_url": image_url,
                "texture_id": texture_id,
                "presigned_url": presigned_url,
                "mesh_url": mesh_url,
                "text": prompt,
                "seed": seed,
            }
            input_payload.update(quality_dict)
            input_payload = {k: v for k, v in input_payload.items() if v is not None}

            endpoint = AsyncioEndpoint(self.texture_endpoint_id, runpod_session)
            job: AsyncioJob = await endpoint.run(input_payload)

            # Polling job status
            status = await job.status()
            while status == "IN_QUEUE":
                status = await job.status()
                print(f"Current job status: {status}")
                await asyncio.sleep(3)
            async for output in job.stream():
                presigned_url = output["presigned_url"]
                parsed_url = urlparse(presigned_url)
                async with AsyncSessionLocal() as session:
                    await TextureDAL(session).update_texture(
                        id=texture_id,
                        project_id=project.id,
                        image_id=image.id,
                        mesh_id=mesh_id,
                        storage_key=parsed_url.path[1:],
                        status="COMPLETED",
                        gpu_provider_response=str(output),
                        n_inference_steps=quality_dict["n_inference_steps"],
                        guidance_scale=quality_dict["guidance_scale"],
                        seed=seed,
                        lora_scale=quality_dict.get("lora_scale", 1.0),
                        reference_conditioning_scale=quality_dict.get(
                            "reference_conditioning_scale", 1.0
                        ),
                    )
        return texture_id
