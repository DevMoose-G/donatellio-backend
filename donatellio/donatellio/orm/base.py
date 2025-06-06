# db/base.py
from sqlalchemy import Boolean, Column
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    active = Column(Boolean, nullable=False, default=True, server_default="True")
