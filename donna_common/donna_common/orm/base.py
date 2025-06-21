# db/base.py
import enum
from sqlalchemy import Boolean, Column, Enum
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    active = Column(Boolean, nullable=False, default=True, server_default="True")

# types
class AssetStage(enum.Enum):
    image = "image"
    mesh = "mesh"
    texture = "texture"
    
asset_stage_enum = Enum(AssetStage, name="asset_stage_enum", create_type=False, checkfirst=True)