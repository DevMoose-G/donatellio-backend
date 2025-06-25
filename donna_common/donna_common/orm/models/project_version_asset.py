from sqlalchemy import Column, ForeignKey, PrimaryKeyConstraint, String
from sqlalchemy.orm import relationship

from donna_common.orm.base import asset_stage_enum, Base


class ProjectVersionAsset(Base):
    __tablename__ = "project_version_assets"

    project_version_id: str = Column(String(128), ForeignKey("project_versions.id", ondelete="CASCADE"), nullable=False, primary_key=True)
    asset_type: str = Column(asset_stage_enum, nullable=False, primary_key=True)
    asset_id = Column(String(128), nullable=False, primary_key=True)

    # __table_args__ = (PrimaryKeyConstraint(project_version_id, asset_type, asset_id, name="pk_project_version_asset"),)
    
    project_version = relationship("ProjectVersion", back_populates="assets", lazy="selectin", passive_deletes=True)