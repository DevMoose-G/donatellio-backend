from typing import List
from fastapi import Depends
from sqlalchemy import select
from donatellio.api.types import ItemImagePromptChat, ResponseImagePromptChat
from donatellio.orm.models.mesh import Mesh
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
        project = await self.get_project_by_id(project_id)
        image_prompts = []
        for image in project.images:
            image_prompts.append(ItemImagePromptChat(prompt=image.prompt, created_at=image.created_at, original_image_id=image.original_image_id))
        
        image_prompts.sort(key=lambda x: x.created_at)

        return ResponseImagePromptChat(chats=image_prompts)

    async def get_image_s3_keys(self, project_id: str) -> List[str]:
        project = await self.get_project_by_id(project_id)
        image_s3_keys = await project.image_s3_keys
        
        return image_s3_keys
    
    async def get_images(self, project_id: str) -> List[Image]:
        project = await self.get_project_by_id(project_id)
        return project.images
    
    async def get_meshes(self, project_id: str) -> List[Mesh]:
        project = await self.get_project_by_id(project_id)
        return project.meshes

    async def get_uploaded_meshes(self, project_id: str) -> List[Mesh]:
        project = await self.get_project_by_id(project_id)
        return [mesh for mesh in project.meshes if mesh.storage_key != None]    
    
    async def get_all_projects_by(self, filter) -> List[Project]:
        projects = await self.session.execute(
            select(Project).where(filter)
        )
        return projects.scalars().all()
    
    async def get_all_projects(self) -> List[Project]:
        projects = await self.session.execute(select(Project))
        return projects.scalars().all()
    
    async def create_project(self, id: str, name: str, user_id: str) -> Project:
        project = Project(id=id, name=name, user_id=user_id)
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project
    
    async def update_project(self, id: str, name: str = None, user_id: str = None) -> Project:
        project = await self.get_project_by_id(id)
        if project is None:
            raise RuntimeError(400, detail="Invalid Project")
        
        if name is not None:
            project.name = name
        if user_id is not None:
            project.user_id = user_id
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project
    
    async def delete_project(self, project) -> None:
        self.session.delete(project)
        await self.session.commit()
    
async def get_project_dal(db: AsyncSession = Depends(get_db)) -> ProjectDAL:
    return ProjectDAL(db)