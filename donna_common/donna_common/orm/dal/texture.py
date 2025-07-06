from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_api.types import MeshFormat
from donna_common.orm.main import get_db
from donna_common.orm.models.texture import Texture
from donna_common.providers.storage import StorageProvider


class TextureDAL:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_texture_by_id(self, texture_id):
        return await self.session.get(Texture, texture_id)

    async def create_texture(self, id: str, **kwargs):
        texture = Texture(id=id, **kwargs)
        self.session.add(texture)
        await self.session.commit()
        await self.session.refresh(texture)
        return texture

    async def update_texture(self, id: str, **kwargs):
        texture = await self.get_texture_by_id(id)
        if texture is None:
            raise RuntimeError("Texture not found")
        for key, value in kwargs.items():
            if key == "gpu_provider_response" and len(value) > 1024:
                print("GPU provider response too long, truncating")
                value = value[:1020]
            if hasattr(texture, key) and value is not None:
                setattr(texture, key, value)
        self.session.add(texture)
        await self.session.commit()
        await self.session.refresh(texture)
        return texture

    async def delete_texture(self, texture) -> None:
        self.session.delete(texture)
        await self.session.commit()
        return

    async def get_textures_by(self, filter):
        results = await self.session.execute(select(Texture).where(filter))
        return results.scalars().all()


async def get_texture_dal(db: AsyncSession = Depends(get_db)):
    return TextureDAL(db)
