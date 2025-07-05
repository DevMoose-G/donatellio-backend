import asyncio
import json
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
        # asyncio.set_event_loop_policy(
        #     asyncio.WindowsSelectorEventLoopPolicy()
        # )  # For Windows users.


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

    async def regenerate_mesh_from_latents(
        self,
        project_id: str,
        old_mesh_id: str,
        mesh_id: str,
        mc_level: float,
        octree_resolution: int,
        max_facenum: int=None,
        do_shade_smooth: bool = True,
        n_meshes: int = 1,
    ) -> str:
        # TODO: regen mesh from latents
        async with AsyncSessionLocal() as session:
            project = await ProjectDAL(session).get_project_by_id(project_id)
            assert project is not None

        await self.wake_up_texture()

        # generate presigned url
        storage_provider = StorageProvider()

        # set mesh params
        input_payload = {
            "start_from_latents": True,
            "n_meshes": n_meshes,
            "mc_level": mc_level,
            "octree_resolution": octree_resolution,
            "max_facenum": max_facenum,
            "do_shade_smooth": do_shade_smooth
        }

        mesh_mapping = {}
        async with AsyncSessionLocal() as session:
            await MeshDAL(session).update_mesh(
                id=mesh_id,
                octree_resolution=str(input_payload["octree_resolution"]),
                face_count=max_facenum,
                mc_level=mc_level,
                do_shade_smooth=do_shade_smooth,
                status="PENDING",
            )
        
        # generate the presigned url to send to runpod
        old_mesh = await MeshDAL(session).get_mesh_by_id(old_mesh_id)
        if old_mesh.latents_storage_key is None:
            print("latents_storage_key is None")
            breakpoint()
            return
        old_mesh_latents_url = storage_provider.generate_get_url(old_mesh.latents_storage_key)
        presigned_url = storage_provider.generate_put_url_for_mesh(mesh_id)
        mesh_mapping[mesh_id] = [old_mesh_latents_url, presigned_url]

        input_payload["mesh_presigned_urls_mapping"] = mesh_mapping

        async with aiohttp.ClientSession() as runpod_session:
            input_payload = {k: v for k, v in input_payload.items() if v is not None}

            endpoint = AsyncioEndpoint(self.geometry_endpoint_id, runpod_session)
            job: AsyncioJob = await endpoint.run(input_payload)

            # Polling job status
            status = await job.status()
            while status == "IN_QUEUE":
                status = await job.status()
                print(f"Current job status: {status}")
                await asyncio.sleep(3)
            try:
                async for output in job.stream():
                    presigned_url = output["mesh_presigned_url"]
                    n_faces = output['face_count']
                    parsed_url = urlparse(presigned_url)
                    storage_key = parsed_url.path[1:]
                    async with AsyncSessionLocal() as session:
                        await MeshDAL(session).update_mesh(
                            id=mesh_id,
                            storage_key=storage_key,
                            active=True,
                            status="COMPLETED",
                            face_count=n_faces,
                            gpu_provider_response=str(output)[-1000:],
                        )
            except Exception as e:
                breakpoint()
                async with AsyncSessionLocal() as session:
                    for mesh_id in mesh_mapping.keys():
                        await MeshDAL(session).update_mesh(
                            id=mesh_id,
                            status="FAILED",
                            gpu_provider_response=str(e)[-1000:],
                        )
                raise e
        return list(mesh_mapping.keys())[0]

    # TODO: test if streaming works
    async def generate_untextured_mesh(
        self,
        project_id: str,
        image_id: str,
        mesh_ids: List[str],
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

        image_url = storage_provider.generate_get_url(image.storage_key)

        # set mesh params
        quality_dict = {}
        if quality == "low":
            quality_dict = {"n_inference_steps": 30, "octree_resolution": 256}
        elif quality == "medium":
            quality_dict = {"n_inference_steps": 50, "octree_resolution": 384}
        elif quality == "high":
            quality_dict = {"n_inference_steps": 70, "octree_resolution": 512}

        input_payload = {
            "start_from_latents": False,
            "image_url": image_url,
            "n_meshes": n_meshes,
            "seed": seed,
            "labels": labels,
            "max_facenum": max_polygon_count,
        }
        input_payload.update(quality_dict)

        labels = [label.lower() for label in labels]

        dict_labels = {}
        # for some reason, symmetry can't be in an array
        if "symmetric" in labels:
            dict_labels["symmetry"] = "x"
        elif "asymmetric" in labels:
            dict_labels["symmetry"] = "asymmetry"
        
        if "sharp" in labels:
            dict_labels["geometry_type"] = ["sharp"]
        elif "normal" in labels:
            dict_labels["geometry_type"] = ["normal"]
        elif "smooth" in labels:
            dict_labels["geometry_type"] = ["smooth"]

        if "t-pose" in labels:
            dict_labels["pose"] = ["t-pose"]
        elif "a-pose" in labels:
            dict_labels["pose"] = ["a-pose"]
        input_payload["label"] = dict_labels

        mesh_mapping = {}
        for mesh_id in mesh_ids:
            # create mesh in database w/ status='PENDING'
            async with AsyncSessionLocal() as session:
                await MeshDAL(session).update_mesh(
                    id=mesh_id,
                    seed=seed,
                    octree_resolution=str(input_payload["octree_resolution"]),
                    num_inference_steps=input_payload["n_inference_steps"],
                    face_count=max_polygon_count,
                    label=json.dumps(dict_labels),
                    # TODO: have to add these to frontend
                    guidance_scale=5.5,
                    mc_level=0.0,
                    caption=None,
                )
            # generate the presigned url to send to runpod
            presigned_url = storage_provider.generate_put_url_for_mesh(mesh_id)
            latents_presigned_url = storage_provider.generate_put_url_for_latents(mesh_id)
            mesh_mapping[mesh_id] = [latents_presigned_url, presigned_url]

        input_payload["mesh_presigned_urls_mapping"] = mesh_mapping

        async with aiohttp.ClientSession() as runpod_session:
            input_payload = {k: v for k, v in input_payload.items() if v is not None}

            endpoint = AsyncioEndpoint(self.geometry_endpoint_id, runpod_session)
            job: AsyncioJob = await endpoint.run(input_payload)
            print("Runpod Job started")

            # Polling job status
            status = await job.status()
            while status == "IN_QUEUE":
                status = await job.status()
                print(f"Current job status: {status}")
                if status == "FAILED":
                    async with AsyncSessionLocal() as session:
                        for mesh_id in mesh_mapping.keys():
                            await MeshDAL(session).update_mesh(
                                id=mesh_id,
                                status="FAILED",
                                gpu_provider_response="Error during mesh generation",
                            )
                    print("Runpod Job failed")
                    break
                await asyncio.sleep(3)
            try:
                async for output in job.stream():
                    mesh_id = output["mesh_id"]
                    presigned_url = output["mesh_presigned_url"]
                    latents_presigned_url = output['latents_presigned_url']
                    
                    n_faces = output['face_count']
                    parsed_mesh_url = urlparse(presigned_url)
                    parsed_latents_url = urlparse(latents_presigned_url)
                    async with AsyncSessionLocal() as session:
                        await MeshDAL(session).update_mesh(
                            id=mesh_id,
                            storage_key=parsed_mesh_url.path[1:],
                            latents_storage_key=parsed_latents_url.path[1:],
                            status="COMPLETED",
                            face_count=n_faces,
                            gpu_provider_response=str(output)[-1000:],
                        )
            except:
                breakpoint()
                async with AsyncSessionLocal() as session:
                    for mesh_id in mesh_mapping.keys():
                        await MeshDAL(session).update_mesh(
                            id=mesh_id,
                            status="FAILED",
                            gpu_provider_response="Error during mesh generation",
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
        texture_id: str,
    ):
        # create mesh in database w/ status='PENDING'
        async with AsyncSessionLocal() as session:
            image = await ImageDAL(session).get_image_by_id(image_id)
            mesh = await MeshDAL(session).get_mesh_by_id(mesh_id)
            project = await ProjectDAL(session).get_project_by_id(project_id)
            assert image is not None
            assert project is not None
            assert mesh is not None

            # await TextureDAL(session).update_texture(
            #     id=texture_id,
            #     project_id=project.id,
            #     image_id=image.id,
            #     mesh_id=mesh.id,
            #     storage_key=None,
            #     status="PENDING",
            #     gpu_provider_response="",
            # )

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
