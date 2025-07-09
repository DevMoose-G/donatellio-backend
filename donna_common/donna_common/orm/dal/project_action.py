from typing import List
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_common.orm.base import AssetStage
from donna_common.orm.main import get_db
from donna_common.orm.models.project import Project
from donna_common.orm.models.project_action import ProjectAction


class ProjectActionDAL:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, action: ProjectAction):
        self.session.add(action)
        await self.session.commit()
        await self.session.refresh(action)
        return
    
    async def create_action(self, version_id: str, author_id: str, asset_type: AssetStage, asset_id: str, action_type: str, parameters: dict) -> ProjectAction:
        action_id = str(uuid4())
        action = ProjectAction(
            id=action_id, asset_id=asset_id, project_version_id=version_id, 
            asset_stage=asset_type, author_id=author_id, action_type=action_type, parameters=parameters
        )
        self.session.add(action)
        await self.session.commit()
        await self.session.refresh(action)
        return action
    
    async def get_all_actions_in_project_version(self, version_id: str) -> List[ProjectAction]:
        stmt = select(ProjectAction).where(ProjectAction.project_version_id == version_id)
        return await self.session.scalars(stmt)
    
    async def get_actions_by_asset(self, asset_id: str, asset_type: AssetStage) -> List[ProjectAction]:
        stmt = select(ProjectAction) \
         .where((ProjectAction.asset_id == asset_id) & (ProjectAction.asset_stage == asset_type.value)).order_by(ProjectAction.created_at.desc())
        scalars = await self.session.scalars(stmt)
        return scalars.all()