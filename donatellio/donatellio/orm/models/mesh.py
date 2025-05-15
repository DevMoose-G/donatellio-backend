from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, DateTime
from datetime import datetime, timezone
from sqlalchemy.orm import relationship

from donatellio.orm.base import Base

class Mesh(Base):
    __tablename__ = "meshes"

    id = Column(String(128), primary_key=True)
    project_id = Column(String(128), ForeignKey("projects.id"), nullable=False)
    image_id = Column(String(128), ForeignKey("images.id"), nullable=False) # images?
    url = Column(String(1024), nullable=False)

    seed = Column(Integer, nullable=False)
    octree_resolution = Column(String(8), nullable=False, default="256") # either 256, 384, 512 (maybe others?)
    num_inference_steps = Column(Integer, nullable=False, default=30) # more steps = smoother, detailed shapes
    face_count = Column(Integer, nullable=False, default=40000) # 5k-100k faces
    texture = Column(Boolean, nullable=False, default=True) # texture or not
    guidance_scale = Column(Float, nullable=False, default=5.5) # 1-15, higher=listen to image more
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    project = relationship("Project", back_populates="meshes")
