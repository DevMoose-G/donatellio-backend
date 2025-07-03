from typing import List
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_common.orm.main import get_db
from donna_common.orm.models.project import Project
from donna_common.orm.models.project_version import ProjectVersion


class ProjectVersionDAL:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_all_versions(self, project_id: str) -> List[ProjectVersion]:
        stmt = select(ProjectVersion).where(ProjectVersion.project_id == project_id)
        exec = await self.session.execute(stmt)
        return exec.scalars().all()
    
    async def get_version_by_id(self, version_id: str) -> ProjectVersion:
        return await self.session.get(ProjectVersion, version_id)
    
    async def create_version(self, project_id: str, author_id: str, version_number: int, parent_version_id: str=None, message: str="") -> ProjectVersion:
        version_id = str(uuid4())
        version = ProjectVersion(project_id=project_id, id=version_id, message=message, author_id=author_id, version_number=version_number, parent_version_id=parent_version_id)
        self.session.add(version)
        await self.session.commit()
        await self.session.refresh(version)
        return version
    
    async def hard_delete_version(self, version_id: str) -> None:
        version = await self.get_version_by_id(version_id=version_id)
        for assets in version.assets:
            await self.session.delete(assets)
        await self.session.delete(version)
        await self.session.commit()

    
async def get_project_version_dal(session: AsyncSession = Depends(get_db)) -> ProjectVersionDAL:
    return ProjectVersionDAL(session)