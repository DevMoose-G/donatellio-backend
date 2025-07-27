from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base


class Image(Base):
    __tablename__ = "images"

    id = Column(String(128), primary_key=True)
    prompt = Column(String(4096), nullable=False)
    project_id = Column(
        String(128), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    storage_key = Column(String(1024), nullable=True)

    parent_image_id = Column(
        String(128), ForeignKey("images.id", ondelete="CASCADE"), nullable=True
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

    multiview_image_dir = Column(String(1024), nullable=True)

    external_id = Column(
        String(128), nullable=True
    )  # for now, just openai's image generation id (for multi-turn editing)

    error = Column(String(2048), nullable=True)

    thumbnail_image_storage_key = Column(String(1024), nullable=True)

    # TODO: should keep track of openai/replicate parameters

    project = relationship(
        "Project", back_populates="images", lazy="selectin", passive_deletes=True
    )
    meshes = relationship(
        "Mesh", back_populates="image", lazy="selectin", cascade="all, delete-orphan"
    )
    textures = relationship(
        "Texture", back_populates="image", lazy="selectin", cascade="all, delete-orphan"
    )

    parent_image = relationship(
        "Image", remote_side=[id], foreign_keys=[parent_image_id], lazy="selectin"
    )
