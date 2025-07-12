from typing import List, Union
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_common.orm.dal.project_action import ProjectActionDAL
from donna_common.orm.dal.project_version import ProjectVersionDAL
from donna_common.orm.dal.project_version_asset import ProjectVersionAssetDAL
from donna_common.orm.main import get_db
from donna_common.orm.models.image import Image
from donna_common.orm.models.mesh import Mesh
from donna_common.orm.models.project_action import ProjectAction
from donna_common.orm.models.project_branch import ProjectBranch
from donna_common.orm.models.project_version import ProjectVersion
from donna_common.orm.models.texture import Texture


class ProjectBranchDAL:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_branches(self, project_id: str) -> List[ProjectBranch]:
        return await self.session.scalars(
            select(ProjectBranch).where(ProjectBranch.project_id == project_id)
        )

    async def get_branch_by_id(self, branch_id: str) -> ProjectBranch:
        return await self.session.get(ProjectBranch, branch_id)

    async def create_branch(
        self, project_id: str, author_id: str, name: str, version_id: str = None
    ) -> ProjectBranch:
        if version_id is None:
            new_version = await ProjectVersionDAL(self.session).create_version(
                project_id=project_id,
                author_id=author_id,
                version_number=0,
                message="Initialized branch",
            )
            version_id = new_version.id
        branch = ProjectBranch(
            id=str(uuid4()),
            project_id=project_id,
            name=name,
            head_version_id=version_id,
        )
        self.session.add(branch)
        await self.session.commit()
        await self.session.refresh(branch)
        return branch

    async def update_branch(
        self, branch_id: str, name: str = None, head_version_id: str = None
    ) -> ProjectBranch:
        branch = await self.get_branch_by_id(branch_id)
        if name is not None:
            branch.name = name
        if head_version_id is not None:
            branch.head_version_id = head_version_id
        self.session.add(branch)
        await self.session.commit()
        await self.session.refresh(branch)
        return branch

    async def create_version(
        self, branch_id, author_id, version_message
    ) -> ProjectVersion:
        project_version_dal = ProjectVersionDAL(self.session)
        branch = await self.get_branch_by_id(branch_id)
        parent_version_id = branch.head_version_id
        parent_version = await project_version_dal.get_version_by_id(parent_version_id)

        # create new version
        version = await project_version_dal.create_version(
            project_id=branch.project_id,
            author_id=author_id,
            version_number=parent_version.version_number + 1,
            parent_version_id=parent_version_id,
            message=version_message,
        )

        # copy all project_version_assets linked to parent_version
        project_version_asset_dal = ProjectVersionAssetDAL(self.session)
        await project_version_asset_dal.seed_from_parent_version(
            project_version_id=version.id, parent_version_id=branch.head_version_id
        )

        # update branch to point to new version
        branch = await self.update_branch(
            branch_id=branch.id, head_version_id=version.id
        )

        return version

    async def perform_action(
        self,
        branch_id: str,
        author_id: str,
        new_asset: Union[Mesh, Texture, Image],
        action_type: str,
        parameters: dict,
        version_id: str = None,
        version_message: str = None,
    ) -> ProjectAction:
        project_version_asset_dal = ProjectVersionAssetDAL(self.session)
        # if version_id == None:
        # raise RuntimeError(400, detail="Need either branch_id or version_id to perform action")

        if version_id is None:
            if version_message is None:
                raise RuntimeError(
                    400,
                    detail="Need either version_message or version_id to perform action",
                )
            version = await self.create_version(
                branch_id=branch_id,
                author_id=author_id,
                version_message=version_message,
            )
        else:
            project_version_dal = ProjectVersionDAL(self.session)
            version = await project_version_dal.get_version_by_id(version_id)

        asset_type = type(new_asset).__name__.lower()
        action = await ProjectActionDAL(self.session).create_action(
            version_id=version.id,
            author_id=author_id,
            asset_id=new_asset.id,
            asset_type=asset_type,
            action_type=action_type,
            parameters=parameters,
        )
        # loop through actions to update those links
        await project_version_asset_dal.update_from_actions(
            project_version_id=version.id, actions=[action]
        )
        return action

    async def hard_delete_branch(self, branch_id: str) -> ProjectBranch:
        branch = await self.get_branch_by_id(branch_id)
        await self.session.delete(branch)
        await self.session.commit()
        return branch


def get_project_branch_dal(session: AsyncSession = Depends(get_db)) -> ProjectBranchDAL:
    return ProjectBranchDAL(session)
