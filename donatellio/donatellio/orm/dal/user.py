from fastapi import Depends
from donatellio.orm.models.user import User
from donatellio.orm.main import AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession

class UserDAL:
    def __init__(self, session):
        self.session = AsyncSessionLocal()
    
    async def get_user(self, user_id):
        return await self.session.get(User, user_id)
    
    async def get_user_by_email(self, email):
        return await self.session.query(User).filter(User.email == email).first()
    
    async def create_user(self, user):
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
    
    async def update_user(self, user):
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
    
    async def delete_user(self, user):
        self.session.delete(user)
        await self.session.commit()
        return
    
async def get_user_dal(db: AsyncSession = Depends(get_db)):
    return UserDAL(db)