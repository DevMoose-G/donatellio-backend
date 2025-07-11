from datetime import datetime, timezone
from typing import List

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship, Mapped

from donna_common.orm.base import Base

# TODO: need association tables with images, meshes, and textures
styleboard_image_assoc = Table(
    'styleboard_image_assoc',
    Base.metadata,
    Column('styleboard_id', String, ForeignKey('styleboards.id'), primary_key=True),
    Column('image_id', String, ForeignKey('images.id'), primary_key=True)
)

styleboard_mesh_assoc = Table(
    'styleboard_mesh_assoc',
    Base.metadata,
    Column('styleboard_id', String, ForeignKey('styleboards.id'), primary_key=True),
    Column('mesh_id', String, ForeignKey('meshes.id'), primary_key=True)
)

styleboard_texture_assoc = Table(
    'styleboard_texture_assoc',
    Base.metadata,
    Column('styleboard_id', String, ForeignKey('styleboards.id'), primary_key=True),
    Column('texture_id', String, ForeignKey('textures.id'), primary_key=True)
)

class StyleBoard(Base):
    __tablename__ = "styleboards"

    id: Mapped[int] = Column("id", String, primary_key=True)
    name: Mapped[str] = Column("name", String, nullable=False)
    description: Mapped[str] = Column("description", String(2048), nullable=False)

    images = relationship(
        "Image",
        secondary=styleboard_image_assoc,
        back_populates="styleboards",
        passive_deletes=True
    )

    meshes = relationship(
        "Mesh",
        secondary=styleboard_mesh_assoc,
        back_populates="styleboards",
        passive_deletes=True
    )

    textures = relationship(
        "Texture",
        secondary=styleboard_texture_assoc,
        back_populates="styleboards",
        passive_deletes=True
    )

    created_at: Mapped[datetime] = Column("created_at", DateTime, nullable=False)
    updated_at: Mapped[datetime] = Column("updated_at", DateTime, nullable=False)