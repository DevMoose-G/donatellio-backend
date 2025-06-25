from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base


class ProjectBranch(Base):
    __tablename__ = "project_branches"
    
    id: str = Column(
        String(128),
        primary_key=True
    )
    name: str = Column(
        String(256)
    )
    project_id: str = Column(
        String(128),
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    head_version_id: str = Column(
        String(128),
        ForeignKey("project_versions.id"),
        nullable=False,
    )
    
    created_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    
    project = relationship(
        "Project", back_populates="branches", lazy="selectin", passive_deletes=True
    )
    
    