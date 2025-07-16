from abc import abstractmethod
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
from donna_common.redis.types import MeshAction
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

class BaseProvider:

    @abstractmethod
    async def wake_up_geometry(self):
        pass

    @abstractmethod
    async def wake_up_texture(self):
        pass

    @abstractmethod
    async def wake_up_retopology(self):
        pass

    @abstractmethod
    async def health(self, endpoint_id: str) -> EndpointHealth:
        pass

    @abstractmethod
    async def simplify_mesh(
        self, mesh_id: str, new_mesh_id: str, simplify_ratio: float = None
    ):
        pass

    @abstractmethod
    async def regenerate_mesh_from_latents(
        self,
        project_id: str,
        old_mesh_id: str,
        mesh_id: str,
        mc_level: float,
        octree_resolution: int,
        max_facenum: int = None,
        do_shade_smooth: bool = True,
        n_meshes: int = 1,
    ) -> str:
        pass

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
        completed_meshes_stream,
    ):
        pass

    async def generate_texture_on_mesh(
        self,
        project_id: str,
        image_id: str,
        mesh_id: str,
        prompt: str,
        texture_quality: str,  # normal, precise, or stylized
        seed: int,
        texture_id: str,
        # completed_meshes_stream,
    ):
        pass
