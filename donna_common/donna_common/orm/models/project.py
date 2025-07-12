from datetime import datetime, timezone
from typing import List

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import Mapped, relationship

from donna_common.orm.base import Base
from donna_common.orm.models.image import Image


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(128), primary_key=True)
    name = Column(String(128), nullable=False)
    user_id = Column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
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

    public = Column(Boolean, nullable=False, default=False, server_default="False")
    styleboard_id = Column(String(128), ForeignKey("styleboards.id"), nullable=True)

    owner = relationship("User", back_populates="projects", lazy="selectin")
    images: Mapped[List[Image]] = relationship(
        "Image", back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    meshes = relationship(
        "Mesh", back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    textures = relationship(
        "Texture",
        back_populates="project",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    assoc_collections = relationship(
        "ProjectCollection",
        back_populates="project",
        lazy="selectin",
        passive_deletes=True,
        cascade="all, delete-orphan",
    )
    collections = association_proxy("assoc_collections", "collection")

    branches = relationship(
        "ProjectBranch",
        back_populates="project",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    versions = relationship(
        "ProjectVersion",
        back_populates="project",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    styleboard = relationship(
        "StyleBoard",
        back_populates="projects",
        lazy="selectin",
    )

    @property
    async def image_s3_keys(self):
        images = sorted(self.images, key=lambda x: x.created_at)
        return [image.storage_key for image in images if image.storage_key != None]

    @property
    async def mesh_s3_keys(self):
        meshes = sorted(self.meshes, key=lambda x: x.created_at)
        return [mesh.storage_key for mesh in meshes if mesh.storage_key != None]
