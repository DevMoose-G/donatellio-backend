from datetime import datetime
from typing import List

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_common.orm import ProjectDAL, get_project_dal
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
    collections_to_remove: List[str]
    collections_to_add: List[str]


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

class GetProjectInfoResponse(BaseModel):
    project_id: str
    name: str
    created_at: datetime
    is_public: bool
    user_info: UserInfo
    collection_paths: List[CollectionPath]

@router.get("/{project_id}/info", status_code=200)
async def get_project_info(
    project_id: str,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
):
    project = await project_dal.get_project_by_id(project_id)
    if current_user.id != project.user_id:
        return JSONResponse(
            status_code=400,
            content={"error_msg": "You don't have permission to move this project"},
        )
    
    profile_storage_key = project.owner.profile_image_storage_key
    if profile_storage_key is None:
        # temporary
        profile_img_url = "https://static.vecteezy.com/system/resources/previews/056/260/989/non_2x/neon-glowing-cube-with-floating-shapes-abstract-3d-render-free-png.png"
    else:
        storage_provider = StorageProvider()
        profile_img_url = await storage_provider.generate_put_url_for_image(profile_storage_key)

    # can't do this b/c utc zones
    # created_at = project.created_at.strftime("%B %d, %Y at %I:%M%p")

    return GetProjectInfoResponse(
        project_id=project.id,
        name=project.name,
        created_at=project.created_at,
        is_public=project.public,
        user_info=UserInfo(
            id=project.user_id,
            username=project.owner.username,
            profile_image_url=profile_img_url,
        ),
        collection_paths=[ 
            # CollectionPath(collection_id=collection.id)
            # for collection in project.collections
        ],
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
            content={"error_msg": "You don't have permission to move this project"},
        )

    return