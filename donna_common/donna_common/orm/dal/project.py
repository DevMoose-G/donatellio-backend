from typing import List

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_common.orm.dal.image import ImageDAL
from donna_common.orm.dal.project_branch import ProjectBranchDAL
from donna_common.orm.dal.user import UserDAL
from donna_common.orm.main import get_db
from donna_common.orm.models.image import Image
from donna_common.orm.models.mesh import Mesh
from donna_common.orm.models.project import Project
from donna_common.orm.models.project_branch import ProjectBranch
from donna_common.orm.models.texture import Texture
from donna_common.providers.storage import StorageProvider
from donna_common.utils.types import AssetDisplay, ItemImagePromptChat, ProjectDisplay, ResponseImagePromptChat


class ProjectDAL:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_project_by_id(self, project_id) -> Project:
        return await self.session.get(Project, project_id)

    async def get_project_by(self, filter) -> Project:
        projects = await self.session.execute(select(Project).where(filter))
        return projects.scalars().first()

    async def get_image_prompt_chats(self, project_id: str) -> ResponseImagePromptChat:
        project = await self.get_project_by_id(project_id)
        image_prompts = []
        for image in project.images:
            thumbnail_url = None
            image_url = None

            if image.thumbnail_image_storage_key != None:
                thumbnail_url = StorageProvider().generate_get_url(
                    image.thumbnail_image_storage_key
                )
            elif image.storage_key != None:
                thumbnail_url = StorageProvider().generate_get_url(image.storage_key)

            if image.storage_key != None:
                image_url = StorageProvider().generate_get_url(image.storage_key)

            displayed_error = None
            if image.error:
                displayed_error = image.error

            parent_image_url = None
            if image.parent_image_id != None:
                parent_image = await ImageDAL(self.session).get_image_by_id(
                    image.parent_image_id
                )
                parent_image_url = StorageProvider().generate_get_url(
                    parent_image.storage_key
                )
            image_prompts.append(
                ItemImagePromptChat(
                    image_id=image.id,
                    prompt=image.prompt,
                    image_url=image_url,
                    thumbnail_url=thumbnail_url,
                    created_at=image.created_at,
                    parent_image_url=parent_image_url,
                    error=displayed_error,
                )
            )

        image_prompts.sort(key=lambda x: x.created_at)

        return ResponseImagePromptChat(chats=image_prompts)

    async def get_image_s3_keys(self, project_id: str) -> List[str]:
        project = await self.get_project_by_id(project_id)
        image_s3_keys = await project.image_s3_keys

        return image_s3_keys

    async def get_images(self, project_id: str) -> List[Image]:
        project = await self.get_project_by_id(project_id)
        unsorted_imgs = project.images
        return sorted(unsorted_imgs, key=lambda x: x.created_at)

    async def get_meshes(self, project_id: str) -> List[Mesh]:
        project = await self.get_project_by_id(project_id)
        unsorted_meshes = project.meshes
        return sorted(unsorted_meshes, key=lambda x: x.created_at)

    async def get_project_display(self, project: Project) -> ProjectDisplay:
        storage_provider = (
            StorageProvider()
        )  # make a service that combines all this so it's only called once

        user_dal = UserDAL(self.session)
        user = await user_dal.get_user_by_id(project.user_id)

        if project.meshes == []:
            uploaded_images = await self.get_uploaded_images(project_id=project.id)
            if uploaded_images != []:
                url = storage_provider.generate_get_url(uploaded_images[-1].storage_key)
                return ProjectDisplay(
                    project_id=project.id,
                    project_name=project.name,
                    url=url,
                    user_name=user.username,
                    current_state="image",
                )
            else:
                return ProjectDisplay(
                    project_id=project.id,
                    project_name=project.name,
                    url=None,
                    user_name=user.username,
                    current_state="image",
                )
        elif (
            project.textures == []
        ):  # don't display textured meshes (considered complete)
            uploaded_meshes = await self.get_uploaded_meshes(project_id=project.id)
            if uploaded_meshes != []:
                url = storage_provider.generate_get_url(uploaded_meshes[-1].storage_key)
                textured_image_url = (
                    storage_provider.generate_get_url(
                        uploaded_meshes[-1].static_render_storage_key
                    )
                    if uploaded_meshes[-1].static_render_storage_key
                    else None
                )
                mesh_image_url = (
                    storage_provider.generate_get_url(
                        uploaded_meshes[-1].static_render_storage_key
                    )
                    if uploaded_meshes[-1].static_render_storage_key
                    else None
                )
                return ProjectDisplay(
                    project_id=project.id,
                    project_name=project.name,
                    url=url,
                    user_name=user.username,
                    current_state="mesh",
                    textured_image_url=textured_image_url,
                    mesh_image_url=mesh_image_url,
                )
            else:
                return ProjectDisplay(
                    project_id=project.id,
                    project_name=project.name,
                    url=None,
                    user_name=user.username,
                    current_state="mesh",
                )

    async def get_asset_display(self, project: Project) -> AssetDisplay:
        storage_provider = StorageProvider()
        uploaded_textures = await self.get_uploaded_textures(project_id=project.id)
        if uploaded_textures != []:
            url = storage_provider.generate_get_url(uploaded_textures[-1].storage_key)
            textured_image_url = (
                storage_provider.generate_get_url(
                    uploaded_textures[-1].static_render_storage_key
                )
                if uploaded_textures[-1].static_render_storage_key
                else None
            )
            mesh_image_url = (
                storage_provider.generate_get_url(
                    uploaded_textures[-1].mesh.static_render_storage_key
                )
                if uploaded_textures[-1].mesh.static_render_storage_key
                else None
            )
            return AssetDisplay(
                project_id=project.id,
                project_name=project.name,
                url=url,
                user_name=project.owner.username,
                textured_image_url=textured_image_url,
                mesh_image_url=mesh_image_url,
            )

    async def get_textures(self, project_id: str) -> List[Texture]:
        project = await self.get_project_by_id(project_id)
        unsorted_textures = project.textures
        return sorted(unsorted_textures, key=lambda x: x.created_at)

    async def get_uploaded_images(self, project_id: str) -> List[Image]:
        project = await self.get_project_by_id(project_id)
        return [image for image in project.images if image.storage_key != None]

    async def get_uploaded_meshes(self, project_id: str) -> List[Mesh]:
        project = await self.get_project_by_id(project_id)
        return [mesh for mesh in project.meshes if mesh.storage_key != None]

    async def get_uploaded_textures(self, project_id: str) -> List[Texture]:
        project = await self.get_project_by_id(project_id)
        return [texture for texture in project.textures if texture.storage_key != None]

    async def get_all_projects_by(
        self, filter, limit=None, offset=None, order_by=None
    ) -> List[Project]:
        exec = select(Project).where(filter)
        if offset is not None:
            exec = exec.offset(offset)
        if limit is not None:
            exec = exec.limit(limit)
        if order_by is not None:
            exec = exec.order_by(order_by)
        projects = await self.session.execute(exec)
        return projects.scalars().all()

    async def get_all_projects(self) -> List[Project]:
        projects = await self.session.execute(select(Project))
        return projects.scalars().all()

    async def create_project(self, id: str, user_id: str, **kwargs) -> Project:
        project = Project(id=id, user_id=user_id, **kwargs)
        self.session.add(project)

        await ProjectBranchDAL(self.session).create_branch(
            project_id=id, author_id=user_id, name="main"
        )

        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def get_main_branch(self, project_id: str) -> ProjectBranch:
        # TODO: handle case where main branch doesn't exist & if there are multiple main branches
        exec = await self.session.execute(
            select(ProjectBranch).where(
                ProjectBranch.project_id == project_id, ProjectBranch.name == "main"
            )
        )
        return exec.scalars().first()

    async def update_project(self, id: str, **kwargs) -> Project:
        project = await self.get_project_by_id(id)
        if project is None:
            raise RuntimeError("Project not found")
        for key, value in kwargs.items():
            if hasattr(project, key) and value is not None:
                setattr(project, key, value)
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def delete_project(self, project_id: str) -> None:
        project = await self.get_project_by_id(project_id)
        project.active = False
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return

    async def hard_delete_project(self, project_id: str) -> None:
        project = await self.get_project_by_id(project_id)

        for branch in project.branches:
            await ProjectBranchDAL(self.session).hard_delete_branch(branch_id=branch.id)
        # for version in project.versions:
        #     for assets in version.assets:
        #         await self.session.delete(assets)
        #     await self.session.delete(version)

        await self.session.delete(project)
        await self.session.commit()


async def get_project_dal(db: AsyncSession = Depends(get_db)) -> ProjectDAL:
    return ProjectDAL(db)
