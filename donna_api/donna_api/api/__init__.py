from dotenv import load_dotenv
from fastapi import APIRouter, Depends

from donna_api.api.collections import router as collections_router
from donna_api.api.image import router as image_router
from donna_api.api.mesh import router as mesh_router
from donna_api.api.user import router as user_router
from donna_api.auth import get_current_user
from donna_api.types import GetAssetsResponse
from donna_common.orm import Project, ProjectDAL, get_project_dal
from donna_common.orm.models.user import User

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/api")

router.include_router(collections_router)
router.include_router(user_router)
router.include_router(image_router)
router.include_router(mesh_router)

# add a project  info endpoint or just include it in websockets?


@router.get("/market/assets", status_code=200)
async def get_market_assets(
    limit: int,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
) -> GetAssetsResponse:
    projects = [
        project
        for project in await project_dal.get_all_projects_by(
            filter=((Project.user_id != current_user.id) & (Project.public))
        )
        if project.meshes != []
    ]
    assets = []
    for i in range(min(limit, len(projects))):
        project = projects[i]
        asset_display = await project_dal.get_asset_display(project)
        if asset_display != None:  # skip unfinished projects
            assets.append(asset_display)
    return GetAssetsResponse(assets=assets, count=len(assets))
