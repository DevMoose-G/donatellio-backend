from datetime import datetime
from enum import Enum
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.types import ItemCollection, WSModelResponse
from donna_api.websocket import get_all_models_items
from donna_common.orm import ProjectDAL, get_project_dal
from donna_common.orm.dal.collection import CollectionDAL, get_collection_dal
from donna_common.orm.dal.mesh import MeshDAL, get_mesh_dal
from donna_common.orm.dal.project_branch import ProjectBranchDAL, get_project_branch_dal
from donna_common.orm.dal.project_collection import (
    ProjectCollectionDAL,
    get_project_collection_dal,
)
from donna_common.orm.dal.project_version import ProjectVersionDAL, get_project_version_dal
from donna_common.orm.dal.texture import TextureDAL, get_texture_dal
from donna_common.orm.dal.user import UserDAL, get_user_dal
from donna_common.orm.models.project_version import ProjectVersion
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
    
    mesh_url: Optional[str] = None
    textured_url: Optional[str] = None
    
    created_at: datetime
    is_public: bool
    user_info: UserInfo

    editable: bool
    collection_paths: List[CollectionPath]
    current_progress: Optional[ProjectProgress] = None
    
    main_branch_id: Optional[str] = None


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
        profile_img_url = storage_provider.generate_get_url(profile_storage_key)

    preview_url = None
    if project.textures != []:
        if project.textures[-1].static_render_storage_key is None:
            # TODO: send request to generate static render
            pass
        else:
            preview_url = storage_provider.generate_get_url(
                project.textures[-1].static_render_storage_key
            )

    elif project.meshes != []:
        if project.meshes[-1].static_render_storage_key is None:
            # TODO: send request to generate static render
            pass
        else:
            preview_url = storage_provider.generate_get_url(
                project.meshes[-1].static_render_storage_key
            )
    else:
        if project.images[-1].storage_key != None:
            preview_url = storage_provider.generate_get_url(project.images[-1].storage_key)

    coll_paths = []
    proj_progress = None
    textured_url = None
    mesh_url = None
    main_branch_id = None
    
    if current_user.id == project.user_id:
        # Get the full project info
        for collection in project.collections:
            path = []
            parent_id = collection.id
            while parent_id is not None:
                parent = await collection_dal.get_collection_by_id(parent_id)
                path.insert(
                    0,
                    ItemCollection(
                        name=parent.name,
                        collection_id=parent.id,
                        parent_id=parent.parent_id,
                    ),
                )
                parent_id = parent.parent_id
            coll_paths.append(
                CollectionPath(
                    collection_id=collection.id, name=collection.name, path=path
                )
            )

        proj_progress = ProjectProgress.NOT_STARTED
        if project.images != []:
            proj_progress = ProjectProgress.IMAGE_GENERATED
        if project.meshes != []:
            proj_progress = ProjectProgress.MESH_GENERATED
        if project.textures != []:
            proj_progress = ProjectProgress.TEXTURE_GENERATED
            
        main_branch = await project_dal.get_main_branch(project_id=project_id)
        main_branch_id = main_branch.id
    else:
        # not the creator, just show the basic info
        
        texture_key = project.textures[-1].storage_key if project.textures else None
        mesh_key = project.meshes[-1].storage_key if project.meshes else None
        if texture_key:
            textured_url = storage_provider.generate_get_url(texture_key)
        if mesh_key:
            mesh_url = storage_provider.generate_get_url(mesh_key)

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
        mesh_url=mesh_url,
        main_branch_id=main_branch_id
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


class ResponseRenameProject(BaseModel):
    project_id: str
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

    project = await project_dal.update_project(id=project_id, name=req.name)
    return ResponseRenameProject(
        project_id=project.id,
        name=project.name,
    )

class ProjectVersionResponse(BaseModel):
    version_id: str
    version_number: int
    message: str
    author_name: str
    author_id: str

class GetProjectHistoryResponse(BaseModel):
    project_id: str
    project_name: str
    branch_id: str
    branch_name: str
    versions: List[ProjectVersionResponse]

@router.get("/{project_id}/history", status_code=200)
async def get_project_history(
    project_id: str,
    branch_id: str,
    mesh_id: Optional[str] = None,
    project_dal: ProjectDAL = Depends(get_project_dal),
    project_branch_dal: ProjectBranchDAL = Depends(get_project_branch_dal),
    project_version_dal: ProjectVersionDAL = Depends(get_project_version_dal),
    texture_dal: TextureDAL = Depends(get_texture_dal),
    mesh_dal: MeshDAL = Depends(get_mesh_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "You don't have permission to move this project"},
        )
    
    branch = await project_branch_dal.get_branch_by_id(branch_id)
    head_version = await project_version_dal.get_version_by_id(branch.head_version_id)
    
    mesh_ids = []
    if mesh_id is not None:
        mesh_ancestor_id = mesh_id
        while mesh_ancestor_id is not None:
            mesh = await mesh_dal.get_mesh_by_id(mesh_ancestor_id)
            mesh_ids.append(mesh_ancestor_id)
            mesh_ancestor_id = mesh.parent_mesh_id
    # breakpoint()
    
    versions = []
    curr_version = head_version
    while curr_version is not None:
        
        add_version = False
        
        if mesh_id is not None:
            if curr_version.mesh_ids != []:
                for mesh_ancestor in mesh_ids:
                    if mesh_ancestor in curr_version.mesh_ids:
                        add_version = True
                        break
            if not add_version and curr_version.texture_ids != []:
                # breakpoint()
                for texture_id in curr_version.texture_ids:
                    texture = await texture_dal.get_texture_by_id(texture_id)

                    if mesh_id == texture.mesh_id:
                        add_version = True
                        break
        else:
            add_version = True
        
        if add_version:
            versions.append(ProjectVersionResponse(
                version_id=curr_version.id,
                version_number=curr_version.version_number,
                message=curr_version.message,
                author_name=curr_version.author.username,
                author_id=curr_version.author_id
            ))
        
        curr_version = await project_version_dal.get_version_by_id(curr_version.parent_version_id)
    return GetProjectHistoryResponse(
        project_id=project_id,
        project_name=project.name,
        branch_id=branch_id,
        branch_name=branch.name,
        versions=reversed(versions)
    )

@router.post("/{project_id}/mesh/{project_version_id}")
async def mesh_project_version_updates(
    project_id: str,
    project_version_id: str,
    user_dal: UserDAL = Depends(get_user_dal),
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    storage_provider = StorageProvider()

    # getting what's in the database
    new_model_items, _ = await get_all_models_items(storage_provider, set(), project_version_id)

    if new_model_items != []:
        return WSModelResponse(models=new_model_items).model_dump(mode="json")