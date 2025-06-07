from sqlalchemy import Column, ForeignKey, String, Table

from donna_common.orm.base import Base

# 2.1 Association Table for many-to-many
project_collections = Table(
    "project_collections",
    Base.metadata,
    Column(
        "project_id",
        String(128),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "collection_id",
        String(128),
        ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
