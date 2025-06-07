import uuid
from typing import List

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_common.orm.main import get_db
from donna_common.orm.models.collection import Collection
from donna_common.orm.models.project import Project

# from donna_common.orm.models.project_collection import ProjectCollections
from donna_common.orm.models.project_collection import project_collections


class CollectionDAL:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_top_level_collections(self, user_id) -> List[Collection]:
        result = await self.session.execute(
            select(Collection).where(
                (Collection.parent_id == None) & (Collection.user_id == user_id)
            )
        )
        return result.scalars().all()

    async def get_children_collections(self, collection_id) -> List[Collection]:
        result = await self.session.execute(
            select(Collection).where(Collection.parent_id == collection_id)
        )
        return result.scalars().all()

    async def get_projects_from_collection(self, collection_id) -> List[Project]:
        result = await self.session.execute(
            select(Project)
            .join(project_collections, Project.id == project_collections.c.project_id)
            .where(project_collections.c.collection_id == collection_id)
            # select(Project).join(ProjectCollections, Project.id == ProjectCollections.project_id).where(ProjectCollections.collection_id == collection_id)
        )
        return result.scalars().all()

    async def get_collection_by_id(self, collection_id) -> Collection:
        return await self.session.get(Collection, collection_id)

    async def create_collection(
        self, name: str, user_id: str, parent_id: str = None, public: bool = False
    ) -> Collection:
        # TODO: generate the uuid inside the create function for all dals
        collection = Collection(
            id=str(uuid.uuid4()),
            name=name,
            user_id=user_id,
            parent_id=parent_id,
            public=public,
        )
        self.session.add(collection)
        await self.session.commit()
        await self.session.refresh(collection)
        return collection

    async def update_collection(self, id: str, **kwargs) -> Collection:
        collection = await self.get_collection_by_id(id)
        if collection is None:
            raise RuntimeError("Collection not found")
        for key, value in kwargs.items():
            if hasattr(collection, key) and value is not None:
                setattr(collection, key, value)
        self.session.add(collection)
        await self.session.commit()
        await self.session.refresh(collection)
        return collection

    async def delete_collection(self, collection_id) -> None:
        collection = await self.get_collection_by_id(collection_id)
        if collection is None:
            raise RuntimeError("Collection not found")
        self.session.delete(collection)
        await self.session.commit()

    # async def move_project_to_collection(self, project_id: str, collection_id: str):
    #     coll


async def get_collection_dal(db: AsyncSession = Depends(get_db)) -> CollectionDAL:
    return CollectionDAL(db)
