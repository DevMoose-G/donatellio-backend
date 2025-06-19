from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from donna_common.orm.main import get_db
from donna_common.orm.models.image import Image


class ImageDAL:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_image_by_id(self, image_id) -> Image:
        return await self.session.get(Image, image_id)

    async def get_image_by_url(self, url) -> Image:
        return await self.session.query(Image).filter(Image.url == url).first()

    async def create_image(
        self,
        id: str,
        prompt: str,
        project_id: str,
        storage_key: str = None,
        parent_image_id: str | None = None,
    ) -> Image:
        image = Image(
            id=id,
            prompt=prompt,
            project_id=project_id,
            storage_key=storage_key,
            parent_image_id=parent_image_id,
        )
        self.session.add(image)
        await self.session.commit()
        await self.session.refresh(image)
        return image

    async def update_image(self, id: str, **kwargs) -> Image:
        image = await self.get_image_by_id(id)
        if image is None:
            raise RuntimeError("Image not found")
        for key, value in kwargs.items():
            if hasattr(image, key) and value is not None:
                setattr(image, key, value)
        self.session.add(image)
        await self.session.commit()
        await self.session.refresh(image)
        return image

    async def delete_image(self, image) -> None:
        self.session.delete(image)
        await self.session.commit()
        return


async def get_image_dal(db: AsyncSession = Depends(get_db)) -> ImageDAL:
    return ImageDAL(db)
