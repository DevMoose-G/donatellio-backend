from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base

# 2.1 Association Table for many-to-many


class ProjectCollection(Base):
    __tablename__ = "project_collections"

    project_id: str = Column(
        String(128),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    collection_id: str = Column(
        "collection_id",
        String(128),
        ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True,
    )

    project = relationship(
        "Project",
        back_populates="assoc_collections",
        lazy="selectin",
        passive_deletes=True,
    )
    collection = relationship(
        "Collection",
        back_populates="assoc_projects",
        lazy="selectin",
        passive_deletes=True,
    )
