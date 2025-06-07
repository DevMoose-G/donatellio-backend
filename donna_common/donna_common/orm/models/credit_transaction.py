from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from donna_common.orm.base import Base


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    id = Column(String(128), primary_key=True)
    user_id = Column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    delta = Column(Integer, nullable=False)
    reason = Column(String(1024), nullable=False)

    user = relationship("User", back_populates="transactions", lazy="selectin")

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
