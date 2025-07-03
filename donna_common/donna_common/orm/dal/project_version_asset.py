from typing import List
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_common.orm.dal.mesh import MeshDAL
from donna_common.orm.dal.project_version import ProjectVersionDAL
from donna_common.orm.dal.texture import TextureDAL
from donna_common.orm.main import get_db
from donna_common.orm.models.project import Project
from donna_common.orm.models.project_action import ProjectAction
from donna_common.orm.models.project_version_asset import ProjectVersionAsset


class ProjectVersionAssetDAL:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, project_version_id: str, asset_type: str, asset_id: str) -> ProjectVersionAsset:
        asset = ProjectVersionAsset(project_version_id=project_version_id, asset_type=asset_type, asset_id=asset_id)
        self.session.add(asset)
        await self.session.commit()
        await self.session.refresh(asset)
        return asset
    
    async def get_assets_by_version_id(self, project_version_id: str) -> List[ProjectVersionAsset]:
        return await self.session.scalars(select(ProjectVersionAsset).where(ProjectVersionAsset.project_version_id == project_version_id))
    
    async def seed_from_parent_version(self, project_version_id: str, parent_version_id: str) -> List[ProjectVersionAsset]:
        assets: List[ProjectVersionAsset] = await self.get_assets_by_version_id(project_version_id=parent_version_id)
        for asset in assets:
            await self.create(project_version_id=project_version_id, asset_type=asset.asset_type, asset_id=asset.asset_id)
    
        return await self.get_assets_by_version_id(project_version_id=project_version_id)
    
    async def unlink_asset(self, project_version_id: str, asset_type: str, asset_id: str):
        stmt = select(ProjectVersionAsset).where(ProjectVersionAsset.project_version_id == project_version_id, ProjectVersionAsset.asset_type == asset_type, ProjectVersionAsset.asset_id == asset_id)
        asset = await self.session.scalar(stmt)
        await self.session.delete(asset)
        await self.session.commit()
    
    async def update_from_actions(self, project_version_id: str, actions: List[ProjectAction]):
        assets = await self.get_assets_by_version_id(project_version_id=project_version_id)
        old_assets = {asset.asset_id: asset for asset in assets}
        for action in actions:
            
            # delete the links to old assets
            # For now, all images shown no matter what project version
            # if action.asset_stage == "image" and action.asset_id in image_ids:
            #     continue
            if action.asset_stage == "mesh":
                mesh = await MeshDAL(session=self.session).get_mesh_by_id(action.asset_id)
                if mesh is None:
                    raise RuntimeError(400, detail="Mesh not found in project version")
                if mesh.parent_mesh_id in old_assets.keys():
                    old_asset = old_assets[mesh.parent_mesh_id]
                    self.delete_asset(project_version_id=project_version_id, asset_type=old_asset.asset_type, asset_id=old_asset.asset_id)
            elif action.asset_stage == "texture":
                texture = await TextureDAL(session=self.session).get_texture_by_id(action.asset_id)
                if texture is None:
                    raise RuntimeError(400, detail="Texture not found in project version")
                if texture.parent_texture_id in old_assets.keys():
                    old_asset = old_assets[texture.parent_texture_id]
                    self.delete_asset(project_version_id=project_version_id, asset_type=old_asset.asset_type, asset_id=old_asset.asset_id)
            
            # check if asset link to version already exists
            if action.asset_id in old_assets.keys() and action.asset_stage == old_assets[action.asset_id].asset_type:
                continue
            await self.create(project_version_id=project_version_id, asset_type=action.asset_stage, asset_id=action.asset_id)
    
def get_project_version_asset_dal(session: AsyncSession = Depends(get_db)) -> ProjectVersionAssetDAL:
    return ProjectVersionAssetDAL(session=session)