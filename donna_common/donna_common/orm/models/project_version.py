from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base


class ProjectVersion(Base):
    __tablename__ = "project_versions"
    
    id: str = Column(
        String(128),
        primary_key=True,
    )
    version_number: int = Column(
        Integer,
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
    
    image_id = Column(
        String(128),
        ForeignKey("images.id", ondelete="CASCADE"),
        nullable=True,
    )
    
    mesh_id = Column(
        String(128),
        ForeignKey("meshes.id", ondelete="CASCADE"),
        nullable=True,
    )
    
    texture_id = Column(
        String(128),
        ForeignKey("textures.id", ondelete="CASCADE"),
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