from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.types import GetAssetsResponse, GetProjectsResponse
from donna_common.orm import Project, ProjectDAL, UserDAL, get_project_dal, get_user_dal
from donna_common.orm.dal.credit_transaction import (
    CreditTransactionDAL,
    get_credit_transaction_dal,
)
from donna_common.orm.models.user import User
from donna_common.providers.storage import StorageProvider

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/user")


@router.get("/projects", status_code=200)
async def get_users_projects(
    limit: int,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
) -> GetProjectsResponse:
    projects = [
        project
        for project in await project_dal.get_all_projects_by(
            filter=(Project.user_id == current_user.id)
        )
        if project.textures == []
    ]
    assets = []
    for i in range(min(limit, len(projects))):
        project = projects[i]
        project_display = await project_dal.get_project_display(project)
        if project_display != None:  # skip finished projects (textured meshes)
            assets.append(project_display)
    return GetProjectsResponse(projects=assets, count=len(assets))


@router.get("/assets", status_code=200)
async def get_users_assets(
    limit: int,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
) -> GetAssetsResponse:
    projects = [
        project
        for project in await project_dal.get_all_projects_by(
            filter=(Project.user_id == current_user.id)
        )
        if project.textures != []
    ]
    assets = []
    for i in range(min(limit, len(projects))):
        project = projects[i]
        asset_display = await project_dal.get_asset_display(project)
        if asset_display != None:  # skip unfinished projects
            assets.append(asset_display)
    return GetAssetsResponse(assets=assets, count=len(assets))


class NotificationSettings(BaseModel):
    low_credits: bool
    monthly_credits: bool
    product_updates: bool
    promotions: bool


class GetSettingsResponse(BaseModel):
    username: str
    light_mode: bool
    notifications: NotificationSettings


@router.get("/settings", status_code=200)
async def get_user_settings(
    current_user: User = Depends(get_current_user),
) -> GetSettingsResponse:
    notifications = NotificationSettings(
        low_credits=current_user.notification_low_credits,
        monthly_credits=current_user.notification_monthly_credits,
        product_updates=current_user.notification_product_updates,
        promotions=current_user.notification_promotions,
    )
    return GetSettingsResponse(
        username=current_user.username,
        light_mode=current_user.light_mode,
        notifications=notifications,
    )


class RequestUpdateSettings(BaseModel):
    username: Optional[str] = None
    light_mode: Optional[bool] = None
    notifications: Optional[NotificationSettings] = None


@router.post("/settings", status_code=200)
async def update_user_settings(
    req: RequestUpdateSettings,
    user_dal: UserDAL = Depends(get_user_dal),
    current_user: User = Depends(get_current_user),
) -> None:
    if req.username != None:
        await user_dal.update_user(current_user.id, username=req.username)
    if req.light_mode != None:
        await user_dal.update_user(current_user.id, light_mode=req.light_mode)
    if req.notifications != None:
        await user_dal.update_user(
            current_user.id,
            notification_low_credits=req.notifications.low_credits,
            notification_monthly_credits=req.notifications.monthly_credits,
            notification_product_updates=req.notifications.product_updates,
            notification_promotions=req.notifications.promotions,
        )
    current_user = await user_dal.get_user_by_id(current_user.id)
    notifications = NotificationSettings(
        low_credits=current_user.notification_low_credits,
        monthly_credits=current_user.notification_monthly_credits,
        product_updates=current_user.notification_product_updates,
        promotions=current_user.notification_promotions,
    )
    return GetSettingsResponse(
        username=current_user.username,
        light_mode=current_user.light_mode,
        notifications=notifications,
    )


class GetUserInfoResponse(BaseModel):
    username: str
    subscription_tier: str
    credit_balance: int
    n_projects: int
    profile_image_url: Optional[str] = None


@router.get("/info", status_code=200)
async def get_user_info(
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
) -> GetUserInfoResponse:
    # TODO: should it be all projects or only projects with completed textures
    projects = await project_dal.get_all_projects_by(
        filter=(Project.user_id == current_user.id)
    )
    finished_projs = []
    for project in projects:
        if project.textures != []:
            finished_projs.append(project)

    storage_provider = StorageProvider()
    image_url = (
        storage_provider.generate_get_url(current_user.profile_image_storage_key)
        if current_user.profile_image_storage_key
        else None
    )

    return GetUserInfoResponse(
        username=current_user.username,
        subscription_tier=current_user.subscription_tier,
        credit_balance=current_user.credit_balance,
        n_projects=len(finished_projs),
        profile_image_url=image_url,
    )


class ItemCreditTransaction(BaseModel):
    description: str
    amount: int
    created_at: datetime


class ResponseCreditTransactions(BaseModel):
    transactions: List[ItemCreditTransaction]


@router.get("/transactions", status_code=200)
async def get_user_transactions(
    credit_transaction_dal: CreditTransactionDAL = Depends(get_credit_transaction_dal),
    current_user: User = Depends(get_current_user),
) -> ResponseCreditTransactions:
    transactions = await credit_transaction_dal.get_credit_transactions_by_user_id(
        current_user.id
    )

    return ResponseCreditTransactions(
        transactions=[
            ItemCreditTransaction(
                description=transaction.reason,
                amount=transaction.delta,
                created_at=transaction.created_at,
            )
            for transaction in transactions
        ],
    )
