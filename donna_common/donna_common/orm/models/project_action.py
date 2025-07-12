from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base, asset_stage_enum


class ProjectAction(Base):
    __tablename__ = "project_actions"

    id = Column(String(128), primary_key=True)
    project_version_id = Column(
        String(128),
        ForeignKey("project_versions.id", ondelete="CASCADE"),
        nullable=False,
    )

    asset_stage = Column(asset_stage_enum, nullable=False)
    asset_id = Column(String(128), nullable=False)

    action_type = Column(String(128), nullable=False)
    parameters = Column(JSONB, nullable=False, default=dict)

    author_id = Column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    author = relationship("User", back_populates="project_actions", lazy="selectin")
    project_version = relationship(
        "ProjectVersion", back_populates="project_actions", lazy="selectin"
    )
