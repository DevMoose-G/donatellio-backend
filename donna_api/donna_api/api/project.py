from datetime import datetime
from enum import Enum
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.types import CollectionResponse, ItemCollection
from donna_common.orm import ProjectDAL, get_project_dal
from donna_common.orm.dal.collection import CollectionDAL, get_collection_dal
from donna_common.orm.dal.project_collection import (
    ProjectCollectionDAL,
    get_project_collection_dal,
)
from donna_common.orm.models.user import User
from donna_common.providers.storage import StorageProvider

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/project")


@router.delete("/{project_id}", status_code=200)
async def delete_project(
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "You don't have permission to delete this project"},
        )
    await project_dal.hard_delete_project(project.id)
    return {"success": True}


class MoveProjectCollectionRequest(BaseModel):
    project_id: str
    collections_to_remove: List[str] = []
    collections_to_add: List[str] = []


@router.post("/{project_id}/move", status_code=200)
async def move_project_to_collection(
    project_id: str,
    req: MoveProjectCollectionRequest,
    project_dal: ProjectDAL = Depends(get_project_dal),
    project_collection_dal: ProjectCollectionDAL = Depends(get_project_collection_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "You don't have permission to move this project"},
        )

    for coll in req.collections_to_remove:
        await project_collection_dal.delete_project_collection_bridge(project_id, coll)

    for coll in req.collections_to_add:
        await project_collection_dal.create_project_collection_bridge(project_id, coll)

    return {"success": True}


class UserInfo(BaseModel):
    id: str
    username: str
    profile_image_url: str


class CollectionPath(BaseModel):
    collection_id: str
    name: str
    path: List[ItemCollection]

class ProjectProgress(Enum):
    NOT_STARTED = 0
    IMAGE_GENERATED = 1
    IMAGE_COMPLETED = 2
    MESH_GENERATED = 3
    TEXTURE_GENERATED = 4

class GetProjectInfoResponse(BaseModel):
    project_id: str
    name: str
    preview_url: Optional[str] = None
    textured_url: Optional[str] = None
    created_at: datetime
    is_public: bool
    user_info: UserInfo


    editable: bool
    collection_paths: List[CollectionPath]
    current_progress: Optional[ProjectProgress] = None


@router.get("/{project_id}/info", status_code=200)
async def get_project_info(
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    collection_dal: CollectionDAL = Depends(get_collection_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(project_id)
    if project.user_id != current_user.id and not project.public:
        return JSONResponse(
            status_code=403,
            content={"error_msg": "You don't have permission to view this project"},
        )

    storage_provider = StorageProvider()
    profile_storage_key = project.owner.profile_image_storage_key
    if profile_storage_key is None:
        # temporary (use the user profile img url)
        profile_img_url = "https://static.vecteezy.com/system/resources/previews/056/260/989/non_2x/neon-glowing-cube-with-floating-shapes-abstract-3d-render-free-png.png"
    else:
        profile_img_url = await storage_provider.generate_get_url(
            profile_storage_key
        )
    
    preview_url = None
    if project.textures != []:
        if (project.textures[-1].static_render_storage_key is None):
            # TODO: send request to generate static render
            pass
        else:
            preview_url = storage_provider.generate_get_url(project.textures[-1].static_render_storage_key)

    elif project.meshes != []:
        if (project.meshes[-1].static_render_storage_key is None):
            # TODO: send request to generate static render
            pass
        else:
            preview_url = storage_provider.generate_get_url(project.meshes[-1].static_render_storage_key)
    else:
        preview_url = storage_provider.generate_get_url(project.images[-1].storage_key)

    coll_paths = []
    proj_progress = None
    textured_url = None
    if current_user.id == project.user_id:
        for collection in project.collections:
            path = []
            parent_id = collection.id
            while parent_id is not None:
                parent = await collection_dal.get_collection_by_id(parent_id)
                path.insert(0, ItemCollection(name=parent.name, collection_id=parent.id, parent_id=parent.parent_id))
                parent_id = parent.parent_id
            coll_paths.append(CollectionPath(collection_id=collection.id, name=collection.name, path=path))
    
        proj_progress = ProjectProgress.NOT_STARTED
        if project.images != []:
            proj_progress = ProjectProgress.IMAGE_GENERATED
        if project.meshes != []:
            proj_progress = ProjectProgress.MESH_GENERATED
        if project.textures != []:
            proj_progress = ProjectProgress.TEXTURE_GENERATED
    else:
        mesh_key = project.meshes[-1].storage_key if project.meshes else None
        if mesh_key:
            textured_url = storage_provider.generate_get_url(mesh_key)
    return GetProjectInfoResponse(
        project_id=project.id,
        name=project.name,
        preview_url=preview_url,
        created_at=project.created_at,
        is_public=project.public,
        user_info=UserInfo(
            id=project.user_id,
            username=project.owner.username,
            profile_image_url=profile_img_url,
        ),
        collection_paths=coll_paths,
        current_progress=proj_progress,
        editable=current_user.id == project.user_id,
        textured_url=textured_url,
    )


@router.post("/{project_id}/edit", status_code=200)
async def edit_project(
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "You don't have permission to edit this project"},
        )
    # TODO: implement
    return

class RenameProjectRequest(BaseModel):
    name: str

@router.post("/{project_id}/rename", status_code=200)
async def rename_project(
    project_id: str,
    req: RenameProjectRequest,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "You don't have permission to move this project"},
        )

    await project_dal.update_project(id=project_id, name=req.name)
    return