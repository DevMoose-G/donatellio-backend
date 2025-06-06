from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, DateTime
from datetime import datetime, timezone
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from donatellio.orm.base import Base

class Texture(Base):
    __tablename__ = "textures"

    id = Column(String(128), primary_key=True)
    project_id = Column(String(128), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    image_id = Column(String(128), ForeignKey("images.id"), nullable=False)
    mesh_id = Column(String(128), ForeignKey("meshes.id"), nullable=False)
    storage_key = Column(String(1024), nullable=True)
    static_render_storage_key = Column(String(1024), nullable=True)
    
    format_storage_keys = Column(MutableDict.as_mutable(JSONB), nullable=True)

    status = Column(String(32), nullable=False, default="PENDING")
    
    prompt = Column(String(1024), nullable=True)
    n_inference_steps = Column(Integer, nullable=False, default=50)
    guidance_scale = Column(Float, nullable=False, default=3.0)
    seed = Column(Integer, nullable=True)
    lora_scale = Column(Float, nullable=False, default=1.0)
    reference_conditioning_scale = Column(Float, nullable=False, default=1.0) # Weight for image/geometry conditioning
    
    gpu_provider_response = Column(String(1024), nullable=True) # Runpod, etc message after inference
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    project = relationship("Project", back_populates="textures", passive_deletes=True)
    mesh = relationship("Mesh", back_populates="textures", passive_deletes=True)