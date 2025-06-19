from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base


class Texture(Base):
    __tablename__ = "textures"

    id = Column(String(128), primary_key=True)
    project_id = Column(
        String(128), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    image_id = Column(
        String(128), ForeignKey("images.id", ondelete="CASCADE"), nullable=False
    )
    mesh_id = Column(
        String(128), ForeignKey("meshes.id", ondelete="CASCADE"), nullable=False
    )
    storage_key = Column(String(1024), nullable=True)
    static_render_storage_key = Column(String(1024), nullable=True)

    format_storage_keys = Column(MutableDict.as_mutable(JSONB), nullable=True)

    status = Column(String(32), nullable=False, default="PENDING")

    prompt = Column(String(1024), nullable=True)
    n_inference_steps = Column(Integer, nullable=True)
    guidance_scale = Column(Float, nullable=True)
    seed = Column(Integer, nullable=True)
    lora_scale = Column(Float, nullable=True)
    reference_conditioning_scale = Column(
        Float, nullable=True
    )  # Weight for image/geometry conditioning

    gpu_provider_response = Column(
        String(1024), nullable=True
    )  # Runpod, etc message after inference

    parent_texture_id = Column(
        String(128), ForeignKey("textures.id", ondelete="CASCADE"), nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project = relationship("Project", back_populates="textures", passive_deletes=True)
    mesh = relationship("Mesh", back_populates="textures", passive_deletes=True)
    image = relationship("Image", back_populates="textures", passive_deletes=True)

    parent_texture = relationship("Texture", remote_side=id, foreign_keys=[parent_texture_id])
