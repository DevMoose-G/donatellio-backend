from fastapi import Depends
from donatellio.orm.models.image import Image
from donatellio.orm.main import AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession

class ImageDAL:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_image_by_id(self, image_id) -> Image:
        return await self.session.get(Image, image_id)
    
    async def get_image_by_url(self, url) -> Image:
        return await self.session.query(Image).filter(Image.url == url).first()
    
    async def create_image(self, id: str, prompt: str, project_id: str, url: str, original_image_url: str | None = None) -> Image:
        image = Image(id=id, prompt=prompt, project_id=project_id, url=url, original_image_url=original_image_url)
        self.session.add(image)
        await self.session.commit()
        await self.session.refresh(image)
        return image
    
    async def update_image(
        self,
        id: str,
        **kwargs
    ) -> Image:
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