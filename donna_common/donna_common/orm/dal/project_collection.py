from typing import List

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_common.orm.main import get_db
from donna_common.orm.models.project import Project
from donna_common.orm.models.project_collection import ProjectCollection


class ProjectCollectionDAL:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_project_collection_bridge(
        self, project_id, collection_id
    ) -> ProjectCollection:
        result = await self.session.execute(
            select(ProjectCollection)
            .where(ProjectCollection.project_id == project_id)
            .where(ProjectCollection.collection_id == collection_id)
        )
        return result.scalars().one()

    async def create_project_collection_bridge(self, project_id, collection_id):
        project_collection = ProjectCollection(
            project_id=project_id, collection_id=collection_id
        )
        self.session.add(project_collection)
        await self.session.commit()
        await self.session.refresh(project_collection)
        return project_collection

    async def delete_project_collection_bridge(self, project_id, collection_id):
        project_collection = await self.get_project_collection_bridge(
            project_id, collection_id
        )
        await self.session.delete(project_collection)
        await self.session.commit()
        return

    async def get_projects_from_collection(self, collection_id) -> List[Project]:
        result = await self.session.execute(
            select(ProjectCollection).where(
                ProjectCollection.collection_id == collection_id
            )
        )
        pc_bridges = result.scalars().all()
        projects = []
        for project_collection in pc_bridges:
            projects.append(project_collection.project)
        return projects

    async def get_project_collection_bridges_by_project(
        self, project_id
    ) -> List[ProjectCollection]:
        result = await self.session.execute(
            select(ProjectCollection).where(ProjectCollection.project_id == project_id)
        )
        return result.scalars().all()


async def get_project_collection_dal(
    db: AsyncSession = Depends(get_db),
) -> ProjectCollectionDAL:
    return ProjectCollectionDAL(db)
