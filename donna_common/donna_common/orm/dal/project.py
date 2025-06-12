from typing import List

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from donna_api.types import (
    AssetDisplay,
    ItemImagePromptChat,
    ProjectDisplay,
    ResponseImagePromptChat,
)
from donna_common.orm.dal.user import UserDAL
from donna_common.orm.main import get_db
from donna_common.orm.models.image import Image
from donna_common.orm.models.mesh import Mesh
from donna_common.orm.models.project import Project
from donna_common.orm.models.texture import Texture
from donna_common.providers.storage import StorageProvider


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
            if image.thumbnail_image_storage_key != None:
                thumbnail_url = StorageProvider().generate_get_url(
                    image.thumbnail_image_storage_key
                )

            displayed_error = None
            if image.error:
                displayed_error = "Error while generating image. Try again."
            image_prompts.append(
                ItemImagePromptChat(
                    prompt=image.prompt,
                    thumbnail_url=thumbnail_url,
                    created_at=image.created_at,
                    original_image_id=image.original_image_id,
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
        return project.images

    async def get_meshes(self, project_id: str) -> List[Mesh]:
        project = await self.get_project_by_id(project_id)
        return project.meshes

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
        return project.textures

    async def get_uploaded_images(self, project_id: str) -> List[Image]:
        project = await self.get_project_by_id(project_id)
        return [image for image in project.images if image.storage_key != None]

    async def get_uploaded_meshes(self, project_id: str) -> List[Mesh]:
        project = await self.get_project_by_id(project_id)
        return [mesh for mesh in project.meshes if mesh.storage_key != None]

    async def get_uploaded_textures(self, project_id: str) -> List[Texture]:
        project = await self.get_project_by_id(project_id)
        return [texture for texture in project.textures if texture.storage_key != None]

    async def get_all_projects_by(self, filter) -> List[Project]:
        projects = await self.session.execute(select(Project).where(filter))
        return projects.scalars().all()

    async def get_all_projects(self) -> List[Project]:
        projects = await self.session.execute(select(Project))
        return projects.scalars().all()

    async def create_project(self, id: str, name: str, user_id: str) -> Project:
        project = Project(id=id, name=name, user_id=user_id)
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def update_project(
        self, id: str, name: str = None, user_id: str = None
    ) -> Project:
        project = await self.get_project_by_id(id)
        if project is None:
            raise RuntimeError(400, detail="Invalid Project")

        if name is not None:
            project.name = name
        if user_id is not None:
            project.user_id = user_id
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
        await self.session.delete(project)
        await self.session.commit()


async def get_project_dal(db: AsyncSession = Depends(get_db)) -> ProjectDAL:
    return ProjectDAL(db)
