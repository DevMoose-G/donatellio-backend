from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timezone
from sqlalchemy.orm import relationship

from donatellio.orm.main import Base

class User(Base):
    __tablename__ = "users" 
    id = Column(String(128), primary_key=True)
    username = Column(String(128), nullable=False)
    email = Column(String(128), nullable=False)
    password = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    projects = relationship("Project", back_populates="owner")