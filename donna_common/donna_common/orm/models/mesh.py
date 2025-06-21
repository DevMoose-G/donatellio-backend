from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base


class Mesh(Base):
    __tablename__ = "meshes"

    id = Column(String(128), primary_key=True)
    project_id = Column(
        String(128), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    image_id = Column(
        String(128), ForeignKey("images.id", ondelete="CASCADE"), nullable=False
    )  # images?
    storage_key = Column(String(1024), nullable=True)
    latents_storage_key = Column(String(1024), nullable=True)
    static_render_storage_key = Column(String(1024), nullable=True)

    format_storage_keys = Column(MutableDict.as_mutable(JSONB), nullable=True)

    status = Column(String(32), nullable=False, default="PENDING")
    
    parent_mesh_id = Column(
        String(128), ForeignKey("meshes.id", ondelete="CASCADE"), nullable=True
    )

    seed = Column(Integer, nullable=True)
    octree_resolution = Column(
        String(8), nullable=True
    )  # either 256, 384, 512 (maybe others?)
    num_inference_steps = Column(
        Integer, nullable=True
    )  # more steps = smoother, detailed shapes

    face_count = Column(Integer, nullable=True)  # 5k-100k faces
    # need to separate face_count from user_set_face_count

    guidance_scale = Column(Float, nullable=True)  # 1-15, higher=listen to image more
    mc_level = Column(Float, nullable=True)
    label = Column(String(512), nullable=True)
    caption = Column(String(1024), nullable=True)

    gpu_provider_response = Column(
        String(1024), nullable=True
    )  # Runpod, etc message after inference

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

    project = relationship("Project", back_populates="meshes", passive_deletes=True)
    image = relationship("Image", back_populates="meshes", passive_deletes=True)
    
    parent_mesh = relationship(
        "Mesh", remote_side=[id], foreign_keys=[parent_mesh_id], lazy="selectin"
    )

    textures = relationship(
        "Texture", back_populates="mesh", lazy="selectin", cascade="all, delete-orphan"
    )
