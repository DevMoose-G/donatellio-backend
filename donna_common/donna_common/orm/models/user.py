from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base
from sqlalchemy.dialects.postgresql import JSONB


class User(Base):
    __tablename__ = "users"
    id = Column(String(128), primary_key=True)
    username = Column(String(128), nullable=False)
    email = Column(String(128), nullable=False)
    password = Column(String(128), nullable=False)
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

    stripe_customer_id = Column(String(128), nullable=True)
    google_auth_id = Column(String(128), nullable=True)
    is_verified = Column(Boolean, nullable=False, default=False)

    credit_balance = Column(Integer, nullable=False, default=0)

    profile_image_storage_key = Column(String(1024), nullable=True)

    notification_low_credits = Column(
        Boolean, nullable=False, default=True, server_default="True"
    )
    notification_monthly_credits = Column(
        Boolean, nullable=False, default=True, server_default="True"
    )
    notification_product_updates = Column(
        Boolean, nullable=False, default=True, server_default="True"
    )
    notification_promotions = Column(
        Boolean, nullable=False, default=True, server_default="True"
    )

    light_mode = Column(Boolean, nullable=False, default=True, server_default="True")

    questionnaire = Column(JSONB, nullable=False, server_default="{}")

    dob = Column(DateTime(timezone=True), nullable=True)

    projects = relationship("Project", back_populates="owner")
    transactions = relationship("CreditTransaction", back_populates="user")

    collections = relationship("Collection", back_populates="owner")
    styleboards = relationship("StyleBoard", back_populates="owner")

    project_actions = relationship("ProjectAction", back_populates="author")
    project_versions = relationship("ProjectVersion", back_populates="author")
