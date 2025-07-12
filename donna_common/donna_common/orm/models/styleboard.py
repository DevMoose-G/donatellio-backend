from datetime import datetime, timezone
from typing import List

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship, Mapped

from donna_common.orm.base import Base

class StyleBoard(Base):
    __tablename__ = "styleboards"

    id: Mapped[int] = Column("id", String, primary_key=True)
    name: Mapped[str] = Column("name", String, nullable=False)
    description: Mapped[str] = Column("description", String(2048), nullable=True)
    user_id: Mapped[str] = Column("user_id", String, ForeignKey("users.id"), nullable=False)

    assets: Mapped[dict] = Column("assets", JSONB, nullable=True)
    public: Mapped[bool] = Column("public", Boolean, nullable=False, default=False)

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

    projects = relationship(
        "Project", back_populates="styleboard", lazy="selectin", cascade="all, delete-orphan"
    )

    owner = relationship("User", back_populates="styleboards", lazy="selectin")