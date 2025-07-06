from datetime import datetime, timezone
import json
from typing import List, Optional
import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.types import GetAssetsResponse, GetProjectsResponse
from donna_common.settings import settings
from donna_common.orm import Project, ProjectDAL, UserDAL, get_project_dal, get_user_dal
from donna_common.orm.dal.credit_transaction import (
    CreditTransactionDAL,
    get_credit_transaction_dal,
)
from donna_common.orm.models.user import User
from donna_common.providers.storage import StorageProvider
import stripe

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/user")

stripe.api_key = settings.stripe_secret_key

TIER_MAP = {
    "":"free",
    "prod_Scu7PE0RUE0bkF": "pro",
    "prod_ScyEebHjNsSFAa": "studio"
}
REVERSED_TIER_MAP = {v: k for k, v in TIER_MAP.items()}

CREDITS_BY_TIER = {
    "free": 10,
    "pro": 200,
    "studio": 1000
}

@router.post("/subscribe")
async def webhook(request: Request, user_dal: UserDAL = Depends(get_user_dal)):
    raw_body: bytes = await request.body()
    event = stripe.Webhook.construct_event(
        raw_body, request.headers["Stripe-Signature"], settings.stripe_websocket_secret
    )
    
    assert event is not None

    # When a recurring invoice is successfully paid…
    if event.type == "invoice.paid":
        invoice = event.data.object       # The Invoice object
        customer_id = invoice.customer    # Stripe Customer ID
        
        user: User = await user_dal.get_user_by(filter=(User.stripe_customer_id == customer_id))
        
        if user is None:
            print("User not found. This should not happen.")
            return
        
        subscription = stripe.Subscription.retrieve(user.subscription_id)
        product_id = subscription['items']['data'][0].price.product
        user_tier = TIER_MAP[product_id]
        breakpoint()
        
        # TODO: find some way to get the # of remaining monthly credits (not the additional credits)
        added_credits = CREDITS_BY_TIER[user_tier] - user.credit_balance
        user = await user_dal.update_user(user.id, credit_balance=CREDITS_BY_TIER[user_tier])
        
        # record credit transaction
        credit_dal = await get_credit_transaction_dal(user_dal.session)
        await credit_dal.create_credit_transaction(user_id=user.id, delta=added_credits, reason="monthly subscription refill")


class RequestSubscribe(BaseModel):
    tier: str
    monthly: bool

def make_idempotency_key(user_id: str) -> str:
    # e.g. "user_1234:2025-07-05T11:23:45Z:550e8400-e29b-41d4-a716-446655440000"
    return f"{user_id}:{datetime.now(timezone.utc).isoformat()}"

@router.post("/subscribe/pay", status_code=200)
async def subscribe_user(
    request: RequestSubscribe,
    current_user: User = Depends(get_current_user),
) -> None:
    stripe.api_key = settings.stripe_secret_key
    
    # TODO: check if user has a stripe customer id before creating a new one
    # check for existing ones by email or your user_id metadata
    
    idempotency_key = make_idempotency_key(current_user.id)
    prices = stripe.Price.list(
        product=REVERSED_TIER_MAP[request.tier],
        active=True,
        type="recurring",
        limit=8
    )

    price = None
    for p in prices.auto_paging_iter():
        interval = p.recurring.interval 
        if interval == "month" and request.monthly:
            price = p
        elif interval == "year" and not request.monthly:
            price = p
    
    payment_link = stripe.PaymentLink.create(
        line_items=[{
            "price": price.id,
            "quantity": 1
        }],
        submit_type="subscribe",
        metadata={
            "user_id": current_user.id,
            "tier": request.tier,
            "price_id": price.id
        },
        after_completion={
            "type": "redirect",
            "redirect": {
                "url": "http://localhost:3000/subscribe/complete?session_id={CHECKOUT_SESSION_ID}"
            }
        },
        idempotency_key=idempotency_key
    )
    
    return {
        "payment_link": payment_link.url
    }
    
    # await credit_transaction_dal.create_credit_transaction(user.id, 5000, "subscription")

class RequestSubscriptionComplete(BaseModel):
    session_id: str

@router.post("/subscribe/complete", status_code=200)
async def subscribe_user_complete(
    request: RequestSubscriptionComplete,
    current_user: User = Depends(get_current_user),
    user_dal: UserDAL = Depends(get_user_dal),
):
    session = stripe.checkout.Session.retrieve(request.session_id)
    
    await user_dal.update_user(
        current_user.id, 
        stripe_customer_id=session.customer, 
        subscription_id=session.subscription
    )
    
    subscription = stripe.Subscription.retrieve(session.subscription)
    product_id = subscription['items']['data'][0].price.product
    
    subscription_tier = TIER_MAP[product_id]
    
    return {
        "tier": subscription_tier
    }
    

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
    
    if current_user.subscription_id != '':
        subscription = stripe.Subscription.retrieve(current_user.subscription_id)
        product_id = subscription['items']['data'][0].price.product
        
        subscription_tier = TIER_MAP[product_id]
    else:
        subscription_tier = "free"

    return GetUserInfoResponse(
        username=current_user.username,
        subscription_tier=subscription_tier, # TEMP: current_user.subscription_id
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
