from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.types import (
    CollectionResponse,
    GetAssetsResponse,
    GetProjectsResponse,
    ItemCollection,
)
from donna_common.orm.dal.collection import CollectionDAL, get_collection_dal
from donna_common.orm.dal.project import ProjectDAL, get_project_dal
from donna_common.orm.dal.project_collection import (
    ProjectCollectionDAL,
    get_project_collection_dal,
)
from donna_common.orm.models.user import User

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/collections")


@router.get("/", status_code=200)
async def get_root_collections(
    collections_dal: CollectionDAL = Depends(get_collection_dal),
    current_user: User = Depends(get_current_user),
) -> CollectionResponse:
    roots = await collections_dal.get_top_level_collections(current_user.id)
    collection_items = [
        ItemCollection(
            collection_id=collection.id,
            name=collection.name,
            parent_id=collection.parent_id,
        )
        for collection in roots
    ]
    return CollectionResponse(collections=collection_items)


@router.get("/{collection_id}", status_code=200)
async def get_collection_by_id(
    collection_id: str,
    collections_dal: CollectionDAL = Depends(get_collection_dal),
    current_user: User = Depends(get_current_user),
) -> CollectionResponse:
    # TODO: check if user has access to this collection

    collection = await collections_dal.get_collection_by_id(collection_id)
    collection_items = [
        ItemCollection(
            collection_id=collection.id,
            name=collection.name,
            parent_id=collection.parent_id,
        )
    ]
    return CollectionResponse(collections=collection_items)


@router.get("/{collection_id}/children", status_code=200)
async def get_children_collections(
    collection_id: str,
    collections_dal: CollectionDAL = Depends(get_collection_dal),
    current_user: User = Depends(get_current_user),
) -> CollectionResponse:
    # TODO: check if user has access to this collection
    children = await collections_dal.get_children_collections(collection_id)
    collection_items = [
        ItemCollection(
            collection_id=collection.id,
            name=collection.name,
            parent_id=collection.parent_id,
        )
        for collection in children
    ]
    return CollectionResponse(collections=collection_items)


@router.get("/{collection_id}/projects", status_code=200)
async def get_projects_from_collection(
    collection_id: str,
    collections_dal: CollectionDAL = Depends(get_collection_dal),
    project_dal: ProjectDAL = Depends(get_project_dal),
    project_collection_dal: ProjectCollectionDAL = Depends(get_project_collection_dal),
    current_user: User = Depends(get_current_user),
):
    # TODO: check if user has access to this collection and all the projects in it
    projects = await project_collection_dal.get_projects_from_collection(collection_id)
    project_items = []
    for project in projects:
        proj_display = await project_dal.get_project_display(project)
        if proj_display != None:
            project_items.append(proj_display)

    # get child collections
    children = await collections_dal.get_children_collections(collection_id)
    for child in children:
        child_projects = await project_collection_dal.get_projects_from_collection(
            child.id
        )
        for project in child_projects:
            proj_display = await project_dal.get_project_display(project)
            if proj_display != None:
                project_items.append(proj_display)

    return GetProjectsResponse(projects=project_items, count=len(project_items))


@router.get("/{collection_id}/assets", status_code=200)
async def get_assets_from_collection(
    collection_id: str,
    collections_dal: CollectionDAL = Depends(get_collection_dal),
    project_dal: ProjectDAL = Depends(get_project_dal),
    project_collection_dal: ProjectCollectionDAL = Depends(get_project_collection_dal),
    current_user: User = Depends(get_current_user),
):
    # TODO: check if user has access to this collection and all the assets in it
    projects = await project_collection_dal.get_projects_from_collection(collection_id)
    assets = []
    for project in projects:
        asset_display = await project_dal.get_asset_display(project)
        if asset_display != None:
            assets.append(asset_display)

    # get child collections
    children = await collections_dal.get_children_collections(collection_id)
    for child in children:
        child_projects = await project_collection_dal.get_projects_from_collection(
            child.id
        )
        for project in child_projects:
            asset_display = await project_dal.get_asset_display(project)
            if asset_display != None:
                assets.append(asset_display)

    return GetAssetsResponse(assets=assets, count=len(assets))


class CreateCollectionRequest(BaseModel):
    name: str
    parent_id: Optional[str] = None


class CreateCollectionResponse(BaseModel):
    collection: ItemCollection


@router.post("/create", status_code=200)
async def create_collection(
    req: CreateCollectionRequest,
    collections_dal: CollectionDAL = Depends(get_collection_dal),
    current_user: User = Depends(get_current_user),
):
    collection = await collections_dal.create_collection(
        name=req.name, user_id=current_user.id, parent_id=req.parent_id
    )
    return CreateCollectionResponse(
        collection=ItemCollection(
            collection_id=collection.id,
            name=collection.name,
            parent_id=collection.parent_id,
        ),
    )


@router.post("/{collection_id}/delete", status_code=200)
async def delete_collection(
    collection_id: str,
    collections_dal: CollectionDAL = Depends(get_collection_dal),
    current_user: User = Depends(get_current_user),
):
    collection = await collections_dal.get_collection_by_id(collection_id)
    if collection.user_id != current_user.id:
        return JSONResponse(
            status_code=403,
            content={
                "error_msg": "You don't have permission to delete this collection"
            },
        )
    await collections_dal.delete_collection(collection_id)
    return JSONResponse(status_code=200)


class RenameCollectionRequest(BaseModel):
    name: str
    collection_id: str


@router.post("/{collection_id}/rename", status_code=200)
async def rename_collection(
    collection_id: str,
    req: RenameCollectionRequest,
    collections_dal: CollectionDAL = Depends(get_collection_dal),
    current_user: User = Depends(get_current_user),
):
    collection = await collections_dal.get_collection_by_id(collection_id)
    if collection.user_id != current_user.id:
        return JSONResponse(
            status_code=403,
            content={
                "error_msg": "You don't have permission to rename this collection"
            },
        )
    await collections_dal.rename_collection(collection_id, req.name)
    return JSONResponse(status_code=200)
