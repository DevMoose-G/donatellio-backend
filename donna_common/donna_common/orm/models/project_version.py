from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
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
        "Project", back_populates="versions", lazy="selectin"
    )
    author = relationship("User", back_populates="project_versions", lazy="selectin")
    parent_version = relationship(
        "ProjectVersion",
        remote_side=[id],
        foreign_keys=[parent_version_id],
        lazy="selectin",
    )
    
    project_actions = relationship(
        "ProjectAction", back_populates="project_version", lazy="selectin"
    )
    assets = relationship(
        "ProjectVersionAsset", back_populates="project_version", lazy="selectin"
    )
    # untested
    textures = association_proxy("assets", "asset_id", creator=lambda id: ProjectVersionAsset(asset_type="texture", asset_id=id))
    meshes = association_proxy("assets", "asset_id", creator=lambda id: ProjectVersionAsset(asset_type="mesh", asset_id=id))
    images = association_proxy("assets", "asset_id", creator=lambda id: ProjectVersionAsset(asset_type="image", asset_id=id))