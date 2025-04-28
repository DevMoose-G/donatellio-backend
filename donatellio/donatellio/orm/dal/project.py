from fastapi import Depends
from donatellio.orm.models.project import Project
from donatellio.orm.models.image import Image
from donatellio.orm.main import AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession

class ProjectDAL:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_project(self, project_id):
        return await self.session.get(Project, project_id)
    
    async def get_project_by_prompt(self, prompt):
        return await self.session.query(Project).filter(Project.prompt == prompt).first()
    
    async def create_project(self, project):
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project
    
    async def update_project(self, project):
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project
    
    async def delete_project(self, project):
        self.session.delete(project)
        await self.session.commit()
        return
    
async def get_project_dal(db: AsyncSession = Depends(get_db)):
    return ProjectDAL(db)