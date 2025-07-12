from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_api.types import MeshFormat
from donna_common.orm.main import get_db
from donna_common.orm.models.styleboard import StyleBoard
from donna_common.providers.storage import StorageProvider


class StyleBoardDAL:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_styleboard_by_id(self, styleboard_id):
        return await self.session.get(StyleBoard, styleboard_id)

    async def create_styleboard(self, id: str, **kwargs):
        styleboard = StyleBoard(id=id, **kwargs)
        self.session.add(styleboard)
        await self.session.commit()
        await self.session.refresh(styleboard)
        return styleboard

    async def delete_styleboard(self, styleboard: StyleBoard) -> None:
        self.session.delete(styleboard)
        await self.session.commit()
        return
    
    async def update_styleboard(self, id: str, **kwargs):
        styleboard = await self.get_styleboard_by_id(id)
        if styleboard is None:
            raise RuntimeError("Styleboard not found")
        for key, value in kwargs.items():
            if hasattr(styleboard, key) and value is not None:
                setattr(styleboard, key, value)
        self.session.add(styleboard)
        await self.session.commit()
        await self.session.refresh(styleboard)
        return
    
    async def add_image(self, styleboard_id: str, image_storage_key):
        styleboard = await self.get_styleboard_by_id(styleboard_id)
        asset_dict = styleboard.assets
        if asset_dict is None:
            asset_dict = {
                "images": []
            }
        asset_dict["images"].append({"storage_key": image_storage_key})
        storyboard = await self.update_styleboard(id=styleboard_id, assets=asset_dict)
        return storyboard
    
    # async def add_project(self, styleboard_id: str, project_id: str):
    #     styleboard = await self.get_styleboard_by_id(styleboard_id)
    #     # styleboard.projects.append(project_id)
    #     self.session.add(styleboard)
    #     await self.session.commit()
    #     await self.session.refresh(styleboard)
    #     return


async def get_styleboard_dal(db: AsyncSession = Depends(get_db)):
    return StyleBoardDAL(db)
