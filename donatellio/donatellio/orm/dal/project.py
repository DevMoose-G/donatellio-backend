from typing import List
from fastapi import Depends
from sqlalchemy import select
from donatellio.api.types import ItemImagePromptChat, ResponseImagePromptChat
from donatellio.orm.models.project import Project
from donatellio.orm.models.image import Image
from donatellio.orm.main import AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession

class ProjectDAL:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_project_by_id(self, project_id) -> Project:
        return await self.session.get(Project, project_id)
    
    async def get_project_by(self, filter) -> Project:
        projects = await self.session.execute(
            select(Project).where(filter)
        )
        return projects.scalars().first()
    
    async def get_image_prompt_chats(self, project_id: str) -> ResponseImagePromptChat:
        project = self.get_project_by_id(project_id)
        image_prompts = []
        for image in project.images:
            image_prompts.append(ItemImagePromptChat(image.prompt, image.created_at, image.original_image_url))
        
        image_prompts.sort(key=lambda x: x.created_at)

        return ResponseImagePromptChat(chats=image_prompts)
    
    async def get_all_projects_by(self, filter) -> List[Project]:
        projects = await self.session.execute(
            select(Project).where(filter)
        )
        return projects.scalars().all()
    
    async def create_project(self, project) -> Project:
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project
    
    async def update_project(self, project) -> Project:
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project
    
    async def delete_project(self, project) -> None:
        self.session.delete(project)
        await self.session.commit()
    
async def get_project_dal(db: AsyncSession = Depends(get_db)) -> ProjectDAL:
    return ProjectDAL(db)