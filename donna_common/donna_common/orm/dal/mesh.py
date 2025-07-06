from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_api.types import MeshFormat
from donna_common.orm.main import get_db
from donna_common.orm.models.mesh import Mesh
from donna_common.providers.storage import StorageProvider


class MeshDAL:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_mesh_by_id(self, mesh_id) -> Mesh:
        return await self.session.get(Mesh, mesh_id)

    async def create_mesh(self, id: str, **kwargs):
        mesh = Mesh(id=id, **kwargs)
        self.session.add(mesh)
        await self.session.commit()
        await self.session.refresh(mesh)
        return mesh

    async def update_mesh(self, id: str, **kwargs):
        mesh = await self.get_mesh_by_id(id)
        if mesh is None:
            raise RuntimeError("Mesh not found")
        for key, value in kwargs.items():
            if key == "octree_resolution" and type(value) != str:
                raise RuntimeError("Octree resolution must be a string")
            if key == "gpu_provider_response" and len(value) > 1024:
                print("GPU provider response too long, truncating")
                value = value[:1020]
            if hasattr(mesh, key) and value is not None:
                setattr(mesh, key, value)
        self.session.add(mesh)
        await self.session.commit()
        await self.session.refresh(mesh)
        return mesh

    async def delete_mesh(self, mesh) -> None:
        await self.session.delete(mesh)
        await self.session.commit()
        return

    async def get_meshes_by(self, filter):
        results = await self.session.execute(select(Mesh).where(filter))
        return results.scalars().all()


async def get_mesh_dal(db: AsyncSession = Depends(get_db)):
    return MeshDAL(db)
