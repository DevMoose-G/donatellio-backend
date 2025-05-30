from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timezone
from sqlalchemy.orm import relationship

from donatellio.orm.base import Base

class User(Base):
    __tablename__ = "users" 
    id = Column(String(128), primary_key=True)
    username = Column(String(128), nullable=False)
    email = Column(String(128), nullable=False)
    password = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    subscription_tier = Column(String(32), nullable=False, default="free")
    credit_balance = Column(Integer, nullable=False, default=0)
    
    projects = relationship("Project", back_populates="owner")
    transactions = relationship("CreditTransaction", back_populates="user")
    