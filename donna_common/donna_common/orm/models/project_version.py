from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, and_
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base
from donna_common.orm.models.project_version_asset import ProjectVersionAsset


class ProjectVersion(Base):
    __tablename__ = "project_versions"
    
    id: str = Column(
        String(128),
        primary_key=True,
    )
    version_number: int = Column(
        Integer,
        nullable=False,
    )
    project_id: str = Column(
        String(128),
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    
    parent_version_id = Column(
        String(128),
        ForeignKey("project_versions.id", ondelete="CASCADE"),
        nullable=True,
    )
    
    message = Column(String(1024), nullable=True)
    
    author_id = Column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    
    
    project = relationship(
        "Project", back_populates="versions", lazy="selectin", passive_deletes=True
    )
    author = relationship("User", back_populates="project_versions", lazy="selectin")
    parent_version = relationship(
        "ProjectVersion",
        remote_side=[id],
        foreign_keys=[parent_version_id],
        lazy="selectin",
    )
    
    project_actions = relationship(
        "ProjectAction", back_populates="project_version", lazy="selectin", cascade="all, delete-orphan"
    )
    assets = relationship(
        "ProjectVersionAsset", back_populates="project_version", lazy="selectin", passive_deletes=True, cascade="all, delete-orphan",
    )

    meshes_assets = relationship("ProjectVersionAsset", primaryjoin=and_(ProjectVersionAsset.project_version_id == id, ProjectVersionAsset.asset_type == "mesh"), viewonly=True, lazy="selectin")
    mesh_ids = association_proxy(
        "meshes_assets", "asset_id"
    )
    
    texture_assets = relationship("ProjectVersionAsset", primaryjoin=and_(ProjectVersionAsset.project_version_id == id, ProjectVersionAsset.asset_type == "texture"), viewonly=True, lazy="selectin")
    texture_ids = association_proxy(
        "texture_assets", "asset_id"
    )
    
    image_assets = relationship("ProjectVersionAsset", primaryjoin=and_(ProjectVersionAsset.project_version_id == id, ProjectVersionAsset.asset_type == "image"), viewonly=True, lazy="selectin")
    image_ids = association_proxy(
        "image_assets", "asset_id"
    )