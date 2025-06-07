from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base


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

    subscription_tier = Column(String(32), nullable=False, default="free")
    credit_balance = Column(Integer, nullable=False, default=0)

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

    projects = relationship("Project", back_populates="owner")
    transactions = relationship("CreditTransaction", back_populates="user")
    collections = relationship("Collection", back_populates="owner")
