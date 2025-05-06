from sqlalchemy import Column, ForeignKey, Integer, String, DateTime
from datetime import datetime, timezone
from sqlalchemy.orm import relationship

from donatellio.orm.base import Base

class Image(Base):
    __tablename__ = "images"

    id = Column(String(128), primary_key=True)
    prompt = Column(String(1024), nullable=False)
    project_id = Column(String(128), ForeignKey("projects.id"), nullable=False)
    url = Column(String(1024), nullable=False)
    original_image_url = Column(String(1024), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # should keep track of openai parameters

    project = relationship("Project", back_populates="images")
