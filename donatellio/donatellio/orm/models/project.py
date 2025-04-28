from sqlalchemy import Column, ForeignKey, Integer, String, DateTime
from datetime import datetime, timezone
from sqlalchemy.orm import relationship

from donatellio.orm.main import Base

class Project(Base):
    __tablename__ = "projects" 
    
    id = Column(String(128), primary_key=True)
    prompt = Column(String(1024), nullable=False)
    user_id = Column(String(128), ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="projects")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=False)