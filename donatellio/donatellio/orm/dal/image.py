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
    
    async def create_image(self, image) -> Image:
        self.session.add(image)
        await self.session.commit()
        await self.session.refresh(image)
        return image
    
    async def update_image(self, image) -> Image:
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