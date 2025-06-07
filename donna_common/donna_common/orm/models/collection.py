from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base
from donna_common.orm.models.project_collection import project_collections


class Collection(Base):
    __tablename__ = "collections"

    id = Column(String(128), primary_key=True)
    name = Column(String(128), nullable=False)
    user_id = Column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    parent_id = Column(
        String(128), ForeignKey("collections.id", ondelete="CASCADE"), nullable=True
    )

    parent = relationship(
        "Collection",
        remote_side=[id],
        back_populates="children",
    )

    children = relationship(
        "Collection",
        back_populates="parent",
        cascade="all, delete-orphan",
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

    owner = relationship("User", back_populates="collections", lazy="selectin")
    projects = relationship("Project", back_populates="collections", lazy="selectin")

    # Many-to-many: which projects belong to this collection
    projects = relationship(
        "Project",
        secondary=project_collections,
        back_populates="collections",
        lazy="selectin",  # check if this takes a long time to load
    )
