import json
from datetime import datetime, timezone
from typing import List, Optional

import stripe
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from donna_api.auth import get_current_user
from donna_api.consts import (
    CARD_BRAND_LOGOS,
    CREDITS_BY_PACKAGE,
    CREDITS_BY_TIER,
    PACKAGE_MAP,
    PRICE_BY_TIER,
    REVERSED_PACKAGE_MAP,
    REVERSED_TIER_MAP,
    TIER_FEATURES,
    TIER_MAP,
)
from donna_api.types import GetAssetsResponse, GetProjectsResponse
from donna_common.orm import Project, ProjectDAL, UserDAL, get_project_dal, get_user_dal
from donna_common.orm.dal.credit_transaction import (
    CreditTransactionDAL,
    get_credit_transaction_dal,
)
from donna_common.orm.models.user import User
from donna_common.providers.storage import StorageProvider
from donna_common.settings import settings

load_dotenv()  # reads .env from cwd

router = APIRouter(prefix="/user")

stripe.api_key = settings.stripe_secret_key


@router.post("/pay/processed")
async def webhook(request: Request, user_dal: UserDAL = Depends(get_user_dal)):
    raw_body: bytes = await request.body()

    event = json.loads(raw_body)
    if event["type"] == "checkout.session.completed":
        # todo filter if this is recurring or one type (additional credits)

        invoice = event["data"]["object"]  # The Invoice object
        customer_id = invoice["customer"]  # Stripe Customer ID
        metadata = invoice['metadata']

        # i think there should only be one source of truth
        user_id = metadata["user_id"]
        user = await user_dal.get_user_by(filter=(User.id == user_id))

        product_id = metadata['product_id']
        user_tier = PACKAGE_MAP[product_id]
        added_credits = CREDITS_BY_PACKAGE[user_tier]

        # TODO: find some way to get the # of remaining monthly credits (not the additional credits)
        user = await user_dal.update_user(
            user.id,
            credit_balance=user.credit_balance + added_credits,
            stripe_customer_id=customer_id,
        )

        # record credit transaction
        credit_dal = await get_credit_transaction_dal(user_dal.session)
        await credit_dal.create_credit_transaction(
            user_id=user.id, delta=added_credits, reason="credits refill"
        )


class RequestSubscribe(BaseModel):
    tier: str


def make_idempotency_key(user_id: str) -> str:
    # e.g. "user_1234:2025-07-05T11:23:45Z:550e8400-e29b-41d4-a716-446655440000"
    return f"{user_id}:{datetime.now(timezone.utc).isoformat()}"


@router.post("/pay", status_code=200)
async def purchase_credits(
    request: RequestSubscribe,
    current_user: User = Depends(get_current_user),
) -> None:
    stripe.api_key = settings.stripe_secret_key

    idempotency_key = make_idempotency_key(current_user.id)
    product_id = REVERSED_PACKAGE_MAP[request.tier]
    prices = stripe.Price.list(
        product=product_id, active=True, limit=1
    )

    price = prices.data[0]

    if (current_user.stripe_customer_id):
        session = stripe.checkout.Session.create(
            success_url=settings.frontend_url + "/subscribe/complete?session_id={CHECKOUT_SESSION_ID}",
            line_items=[{"price": price.id, "quantity": 1}],
            mode="payment",
            idempotency_key=idempotency_key,
            metadata={
                "user_id": current_user.id,
                "package": request.tier,
                "product_id": product_id,
            },
            customer=current_user.stripe_customer_id,
        )
    else:
        session = stripe.checkout.Session.create(
            success_url=settings.frontend_url + "/subscribe/complete?session_id={CHECKOUT_SESSION_ID}",
            line_items=[{"price": price.id, "quantity": 1}],
            idempotency_key=idempotency_key,
            mode="payment",
            metadata={
                "user_id": current_user.id,
                "package": request.tier,
                "price_id": price.id,
            },
            customer_email=current_user.email,
            customer_creation="always",
        )

    return {"payment_link": session.url}


class RequestSubscriptionComplete(BaseModel):
    session_id: str


@router.post("/pay/complete", status_code=200)
async def subscribe_user_complete(
    request: RequestSubscriptionComplete,
    current_user: User = Depends(get_current_user),
    user_dal: UserDAL = Depends(get_user_dal),
):
    session = stripe.checkout.Session.retrieve(request.session_id)

    # this should trigger before the webhook
    await user_dal.update_user(
        current_user.id,
        stripe_customer_id=session.customer,
    )

    return {"success": True}

@router.post("/unsubscribe", status_code=200)
async def unsubscribe_user(
    current_user: User = Depends(get_current_user),
    user_dal: UserDAL = Depends(get_user_dal),
):
    updated_subscription = stripe.Subscription.modify(
        current_user.subscription_id, cancel_at_period_end=True
    )
    await user_dal.update_user(
        current_user.id,
        is_subscribed=False,
    )
    return {"success": True}

@router.get("/projects", status_code=200)
async def get_users_projects(
    limit: int,
    project_dal: ProjectDAL = Depends(get_project_dal),
    current_user: User = Depends(get_current_user),
) -> GetProjectsResponse:
    projects = [
        project
        for project in await project_dal.get_all_projects_by(
            filter=(Project.user_id == current_user.id), order_by=Project.created_at.desc()
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

    image_url = None

    if current_user.profile_image_storage_key == None:
        image_url = None
    elif current_user.profile_image_storage_key.startswith("http"):
        image_url = current_user.profile_image_storage_key
    elif current_user.profile_image_storage_key:
        image_url = storage_provider.generate_get_url(
            current_user.profile_image_storage_key
        )

    # if current_user.is_subscribed:
    #     subscription = stripe.Subscription.retrieve(current_user.subscription_id)
    #     product_id = subscription["items"]["data"][0].price.product

    #     subscription_tier = TIER_MAP[product_id]
    # else:
    #     subscription_tier = "free"

    return GetUserInfoResponse(
        username=current_user.username,
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


class BillingResponse(BaseModel):
    last_4_digits: str
    expiry_month: int
    expiry_year: int
    brand_name: str
    card_logo_url: str = ""


@router.get("/billing", status_code=200)
async def get_billing_info(
    current_user: User = Depends(get_current_user),
) -> Optional[BillingResponse]:
    stripe.api_key = settings.stripe_secret_key

    if True:
        return None

    sub = stripe.Subscription.retrieve(
        current_user.subscription_id, expand=["default_payment_method"]
    )
    pm = sub.default_payment_method
    if not pm or pm.type != "card":
        # no payment method/card
        return None

    card = pm.card

    card_logo_url = CARD_BRAND_LOGOS[card.brand]

    return BillingResponse(
        brand_name=card.brand,
        last_4_digits=card.last4,
        expiry_month=card.exp_month,
        expiry_year=card.exp_year,
        card_logo_url=card_logo_url,
    )
