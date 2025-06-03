from typing import List
import uuid
from fastapi import Depends
from sqlalchemy import select
from donatellio.orm.models.credit_transaction import CreditTransaction
from donatellio.orm.main import AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession

class CreditTransactionDAL:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_credit_transactions_by_user_id(self, user_id: int) -> List[CreditTransaction]:
        transactions = await self.session.execute(select(CreditTransaction).where(CreditTransaction.user_id == user_id))
        return transactions.scalars().all()
    
    async def get_all_credit_transactions(self) -> List[CreditTransaction]:
        transactions = await self.session.execute(select(CreditTransaction))
        return transactions.scalars().all()
    
    async def create_credit_transaction(self, user_id: int, delta: int, reason: str) -> CreditTransaction:
        credit_transaction = CreditTransaction(user_id=user_id, delta=delta, reason=reason)
        if credit_transaction.id is None:
            credit_transaction.id = str(uuid.uuid4())
        self.session.add(credit_transaction)
        await self.session.commit()
        await self.session.refresh(credit_transaction)
        return credit_transaction
    
    async def delete_credit_transaction(self, credit_transaction: CreditTransaction) -> None:
        self.session.delete(credit_transaction)
        await self.session.commit()
        return
    
    

async def get_credit_transaction_dal(db: AsyncSession = Depends(get_db)) -> CreditTransactionDAL:
    return CreditTransactionDAL(db)