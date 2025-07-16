from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from donna_api.api.collections import router as collections_router
from donna_api.api.image import router as image_router
from donna_api.api.mesh import router as mesh_router
from donna_api.api.project import router as project_router
from donna_api.api.user import router as user_router
from donna_api.api.texture import router as texture_router
from donna_api.auth import get_current_user
from donna_api.consts import CREDITS_BY_TIER, TIER_FEATURES
from donna_api.types import GetAssetsResponse
from donna_common.orm import Project, ProjectDAL, get_project_dal
from donna_common.orm.models.user import User

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/api")

router.include_router(collections_router)
router.include_router(user_router)
router.include_router(image_router)
router.include_router(mesh_router)
router.include_router(project_router)
router.include_router(texture_router)

# add a project  info endpoint or just include it in websockets?


@router.get("/market/assets", status_code=200)
async def get_market_assets(
    limit: int,
    offset: Optional[int] = 0,
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
    # TODO: need better way to implement limit & offset (prob need a static list of projects that gets updated periodically)
    for i in range(min(limit, len(projects))):
        project = projects[i]
        asset_display = await project_dal.get_asset_display(project)
        if asset_display != None:  # skip unfinished projects
            if offset > 0:
                offset -= 1
                continue
            assets.append(asset_display)
    assets = assets[:limit]
    return GetAssetsResponse(assets=assets, count=len(assets))


# deprecated
class PricingTier(BaseModel):
    name: str
    monthly_price: Optional[float]
    annual_price: Optional[float]
    description: str
    n_monthly_credits: Optional[int]
    features: List[str]
    additional_credits_price: Optional[float] = None

class PricingPackage(BaseModel):
    name: str
    description: str
    price: float
    n_credits: int

class PricingResponse(BaseModel):
    starter: PricingPackage
    indie: PricingPackage
    studio: PricingPackage


@router.get("/pricing", status_code=200)
async def get_pricing():
    return PricingResponse(
        starter=PricingPackage(
            name="Starter",
            description="Perfect for getting started. For solo developers or hobbyists",
            price=9,
            n_credits=50,
        ),
        indie=PricingPackage(
            name="Indie",
            description="The community's favorite. For small teams",
            price=39,
            n_credits=250
        ),
        studio=PricingPackage(
            name="Studio",
            description="Unleash your creativity at scale. For studios in active production",
            price=99,
            n_credits=1000
        ),
    )
