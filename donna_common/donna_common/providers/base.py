from abc import abstractmethod
from typing import List

from pydantic import BaseModel


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
    ):
        pass
