from typing import List
import uuid
import runpod
from donatellio.orm.dal.texture import TextureDAL
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
        self.geometry_endpoint_id = "1l903cupb6er9d"
        self.texture_endpoint_id = "3svqlzp0hepfvh"
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
    
    async def __wake_up(self, endpoint_id: str):
        async with aiohttp.ClientSession() as runpod_session:
            input_payload = {}
            endpoint = AsyncioEndpoint(endpoint_id, runpod_session)
            await endpoint.run(input_payload)
    
    async def wake_up_geometry(self):
        await self.__wake_up(self.geometry_endpoint_id)
    
    async def wake_up_texture(self):
        await self.__wake_up(self.texture_endpoint_id)
    
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
        max_polygon_count: int
    ):
        await self.wake_up_texture()
        
        # generate presigned url
        storage_provider = StorageProvider()
        
        mesh_mapping = {}
        for i in range(n_meshes):
            mesh_id = str(uuid.uuid4())
            presigned_url = storage_provider.generate_put_url_for_mesh(mesh_id)
            mesh_mapping[mesh_id] = presigned_url
        
        async with aiohttp.ClientSession() as runpod_session:

            # create mesh in database w/ status='PENDING'
            async with AsyncSessionLocal() as session:
                image = await ImageDAL(session).get_image_by_id(image_id)
                project = await ProjectDAL(session).get_project_by_id(project_id)
                assert image is not None
                assert project is not None
            
            storage_provider = StorageProvider()
            image_url = storage_provider.generate_get_url(image.storage_key)
            
            quality_dict = {}
            if quality == "LOW":
                quality_dict = {"n_inference_steps": 30, "octree_resolution": 256}
            elif quality == "MEDIUM":
                quality_dict = {"n_inference_steps": 50, "octree_resolution": 384}
            elif quality == "HIGH":
                quality_dict = {"n_inference_steps": 70, "octree_resolution": 512}
            
            input_payload = {
                "image_url": image_url, 
                "mesh_presigned_urls_mapping": mesh_mapping,
                "n_meshes": n_meshes,
                "seed": seed,
                "labels": labels,
                "max_facenum": max_polygon_count
            }
            input_payload.update(quality_dict)
            input_payload = {k: v for k, v in input_payload.items() if v is not None}

            endpoint = AsyncioEndpoint(self.geometry_endpoint_id, runpod_session)
            job: AsyncioJob = await endpoint.run(input_payload)

            # Polling job status
            status = await job.status()
            while status == "IN_QUEUE":
                status = await job.status()
                print(f"Current job status: {status}")
                await asyncio.sleep(3)
            async for output in job.stream():
                mesh_id = output['mesh_id']
                presigned_url = output['presigned_url']
                parsed_url = urlparse(presigned_url)
                async with AsyncSessionLocal() as session:

                    await MeshDAL(session).create_mesh(
                        id=mesh_id, 
                        project_id=project.id, 
                        image_id=image.id, 
                        storage_key=parsed_url.path[1:], 
                        status="COMPLETED", 
                        gpu_provider_response=str(output)
                    )
        return list(mesh_mapping.keys())
    
    async def generate_texture_on_mesh(
        self, 
        project_id: str, 
        image_id: str,
        mesh_id: str,
        prompt: str,
        texture_quality: str, # normal, precise, or stylized
        seed: int,
    ):
        # generate presigned url
        storage_provider = StorageProvider()
        
        texture_id = str(uuid.uuid4())
        presigned_url = storage_provider.generate_put_url_for_mesh(texture_id)
        
        async with aiohttp.ClientSession() as runpod_session:

            # create mesh in database w/ status='PENDING'
            async with AsyncSessionLocal() as session:
                image = await ImageDAL(session).get_image_by_id(image_id)
                mesh = await MeshDAL(session).get_mesh_by_id(mesh_id)
                project = await ProjectDAL(session).get_project_by_id(project_id)
                assert image is not None
                assert project is not None
            
            storage_provider = StorageProvider()
            image_url = storage_provider.generate_get_url(image.storage_key)
            mesh_url = storage_provider.generate_get_url(mesh.storage_key)
            
            quality_dict = {}
            if texture_quality == "normal":
                quality_dict = {"n_inference_steps": 30, "guidance_scale": 3.0}
            elif texture_quality == "precise":
                quality_dict = {"n_inference_steps": 55, "guidance_scale": 3.0}
            elif texture_quality == "stylized":
                quality_dict = {"n_inference_steps": 50, "guidance_scale": 5.0, "lora_scale": 1.5, "reference_conditioning_scale": 1.5}
            
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
                presigned_url = output['presigned_url']
                parsed_url = urlparse(presigned_url)
                async with AsyncSessionLocal() as session:

                    await TextureDAL(session).create_texture(
                        id=texture_id, 
                        project_id=project.id,
                        image_id=image.id, 
                        mesh_id=mesh_id,
                        storage_key=parsed_url.path[1:], 
                        status="COMPLETED", 
                        gpu_provider_response=str(output)
                    )
        return texture_id