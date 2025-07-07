from typing import List, Optional

from fastapi import Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_common.orm.dal.credit_transaction import get_credit_transaction_dal
from donna_common.orm.main import get_db
from donna_common.orm.models.user import User


class CreditResponse(BaseModel):
    success: bool
    error_msg: Optional[str]
    balance: Optional[int]


class UserDAL:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_by_id(self, user_id) -> User:
        return await self.session.get(User, user_id)

    async def get_all_users_by(self, filter) -> List[User]:
        db_users = await self.session.execute(select(User).where(filter))
        return db_users.scalars().all()

    async def get_user_by(self, filter) -> User:
        db_users = await self.session.execute(select(User).where(filter))
        return db_users.scalars().first()

    async def get_user_by_email(self, email) -> User:
        db_users = await self.session.execute(select(User).where((User.email == email)))
        return db_users.scalars().first()

    async def create_user(self, user) -> User:
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_user(self, id: str, **kwargs) -> User:
        user = await self.session.get(User, id)
        for key, value in kwargs.items():
            setattr(user, key, value)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete_user(self, user) -> None:
        self.session.delete(user)
        await self.session.commit()
        return

    async def charge_credit(
        self, user: User, amount: int, reason: str
    ) -> CreditResponse:
        if amount < 0:
            raise Exception("Amount must be positive")

        if user.credit_balance < amount:
            return CreditResponse(
                success=False, error_msg="Not enough credits", balance=user.credit_balance
            )

        updated_user = await self.update_user(
            user.id, credit_balance=user.credit_balance - amount
        )
        # record credit transaction
        credit_dal = await get_credit_transaction_dal(self.session)
        await credit_dal.create_credit_transaction(
            user_id=user.id, delta=-amount, reason=reason
        )

        return CreditResponse(
            success=True, error_msg=None, balance=updated_user.credit_balance
        )


async def get_user_dal(db: AsyncSession = Depends(get_db)):
    return UserDAL(db)
