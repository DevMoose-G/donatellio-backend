from sqlalchemy import Column, String, JSON, TIMESTAMP, func
from donatellio.orm.main import Base


class InferenceJob(Base):
    __tablename__ = "inference_jobs"

    id = Column(String, primary_key=True, index=True)
    payload = Column(JSON, nullable=False)
    response = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="queued")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
