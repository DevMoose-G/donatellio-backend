from typing import List
from fastapi import Depends
from sqlalchemy import select
from donatellio.orm.models.user import User
from donatellio.orm.main import AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession

class UserDAL:
    def __init__(self, session):
        self.session = AsyncSessionLocal()
    
    async def get_user_by_id(self, user_id) -> User:
        return await self.session.get(User, user_id)
    
    async def get_all_users_by(self, filter) -> List[User]:
        db_users = await self.session.execute(
            select(User).where(filter)
        )
        return db_users.scalars().all()
    
    async def get_user_by(self, filter) -> User:
        db_users = await self.session.execute(
            select(User).where(filter)
        )
        return db_users.scalars().first()
    
    async def get_user_by_email(self, email) -> User:
        db_users = await self.session.execute(
            select(User).where((User.email == email))
        )
        return db_users.scalars().first()
    
    async def create_user(self, user) -> User:
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
    
    async def update_user(self, user) -> User:
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
    
    async def delete_user(self, user) -> None:
        self.session.delete(user)
        await self.session.commit()
        return
    
async def get_user_dal(db: AsyncSession = Depends(get_db)):
    return UserDAL(db)