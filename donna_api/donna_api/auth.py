import uuid
from datetime import datetime, timedelta, timezone
from random import randint
from typing import Any

import redis
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
)
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jose import JWTError, jwt
from pydantic import BaseModel

from donna_api.consts import CREDITS_BY_TIER
from donna_api.email import send_verification_email
from donna_api.types import JWTToken, RequestCreateUser, RequestLoginUser
from donna_common.orm.dal.user import UserDAL, get_user_dal
from donna_common.orm.models.user import User
from donna_common.settings import settings
from donna_common.utils.hashing import get_password_hash, verify_password
from donna_common.utils.profile_image import ICON_STORAGE_KEYS, PALETTES

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

# 3. Define the “token URL” that the client will call to get a token:
#    This corresponds to our login endpoint path (e.g. "/token").
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# this should be an environment variable. should this be regenerated on restart?
SECRET_KEY = (
    settings.auth_secret_key
)  # should be high-entropy (at least 256 bits). change this
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # e.g. tokens valid for 15 mins
REFRESH_TOKEN_EXPIRE_DAYS = 5
SECURITY_SALT = "email-confirm-salt"

EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES = 30

router = APIRouter()


def generate_email_verification_token(user_id: str) -> str:
    serializer = URLSafeTimedSerializer(SECRET_KEY, salt=SECURITY_SALT)
    return serializer.dumps(user_id)


def blacklist_jwt(jti: str) -> None:
    redis_client.set(jti, "revoked", ex=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))


async def get_current_user(
    token: str = Depends(oauth2_scheme), user_dal: UserDAL = Depends(get_user_dal)
) -> User:
    """
    Reads token from “Authorization: Bearer <token>” and returns user if successful
    """
    credentials_exception = HTTPException(
        status_code=401,  # Unauthorized
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 1. Decode token; this can raise JWTError if invalid/expired
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await user_dal.get_user_by(filter=(User.id == user_id))
    if user is None:
        raise credentials_exception
    if user.active == False:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


async def authenticate_jwt(
    token: str, user_dal: UserDAL = Depends(get_user_dal)
) -> str:
    credentials_exception = HTTPException(
        status_code=401,  # Unauthorized
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 1. Decode token; this can raise JWTError if invalid/expired
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    return user_id


async def authenticate_user(
    username: str, email: str, password: str, user_dal: UserDAL = Depends(get_user_dal)
) -> User:
    db_user = await user_dal.get_user_by(filter=(User.username == username))
    if username is None:
        db_user = await user_dal.get_user_by(filter=(User.email == email))
    else:
        db_user = await user_dal.get_user_by(filter=(User.username == username))

    if db_user is None:
        raise HTTPException(status_code=400, detail="User does not exist.")

    if verify_password(password, db_user.password) is False:
        raise HTTPException(status_code=400, detail="Invalid password.")

    return db_user


def create_access_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # Add standard "exp" field so libraries know when it expires:
    to_encode.update({"exp": expire, "scope": "access_token"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str, expected_scope: str) -> dict[str, Any]:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload["scope"] != expected_scope:
        raise JWTError("Invalid scope")

    if payload["jti"] is None:
        raise JWTError("Missing 'jti' in token")
    jti = payload["jti"]
    if redis_client.get(jti) is not None:
        raise JWTError("Token is blacklisted")

    if payload["exp"] is None:
        raise JWTError("Missing 'exp' in token")
    exp = payload["exp"]
    if datetime.now(timezone.utc) > datetime.fromtimestamp(exp, timezone.utc):
        raise JWTError("Token is expired")

    return payload


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    jti = str(uuid.uuid4())
    to_encode.update({"jti": jti})
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "scope": "refresh_token"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@router.get("/check_username")
async def check_username(username: str, user_dal: UserDAL = Depends(get_user_dal)):
    db_user = await user_dal.get_user_by(filter=(User.username == username))
    if db_user is not None:
        return JSONResponse(
            status_code=400, content={"error_msg": "Username already in use"}
        )
    return JSONResponse(status_code=200, content={"success": True})


@router.post("/register")
async def register(
    user: RequestCreateUser,
    response: Response,
    user_dal: UserDAL = Depends(get_user_dal),
):
    # return {
    #     "message":"Temporarily disabled"
    # }
    db_user = await user_dal.get_user_by(filter=(User.email == user.email))
    if db_user is not None:
        return JSONResponse(
            status_code=400, content={"error_msg": "Email already in use"}
        )

    db_user = await user_dal.get_user_by(filter=(User.username == user.username))
    if db_user is not None:
        return JSONResponse(
            status_code=400, content={"error_msg": "Username already in use"}
        )

    hashed_pw = get_password_hash(user.password)

    profile_img_storage_key = f"images/profile_images/{randint(0, len(ICON_STORAGE_KEYS) - 1)}_{randint(0, len(PALETTES) - 1)}.png"
    new_user = User(
        id=str(uuid.uuid4()),
        email=user.email,
        password=hashed_pw,
        username=user.username,
        profile_image_storage_key=profile_img_storage_key,
        credit_balance=CREDITS_BY_TIER["free"],
        is_verified=False,
    )
    new_user = await user_dal.create_user(new_user)

    verification_token = generate_email_verification_token(new_user.id)
    await send_verification_email(user.email, verification_token)

    return {}


@router.get("/verify")
async def verify(
    token: str, response: Response, user_dal: UserDAL = Depends(get_user_dal)
):
    serializer = URLSafeTimedSerializer(SECRET_KEY, salt=SECURITY_SALT)
    try:
        user_id = serializer.loads(
            token,
            salt=SECURITY_SALT,
            max_age=EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES * 60,
        )
    except SignatureExpired:
        raise HTTPException(400, "Verification link expired")
    except BadSignature:
        raise HTTPException(400, "Invalid verification link")

    user = await user_dal.get_user_by(filter=(User.id == user_id))
    if user is None:
        raise HTTPException(400, "Invalid verification link")

    user = await user_dal.update_user(user_id, is_verified=True)

    expires_in = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(data={"sub": user.id})

    jti = str(uuid.uuid4())
    refresh_token = create_refresh_token(data={"sub": user.id, "jti": jti})

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,  # not settings.debug,
        samesite="None",  # TODO: can't use "Lax" since we need cross-site cookies for the frontend
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # 5 days in seconds
        path="/",
    )

    return JWTToken(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    ).model_dump()


@router.post("/login")
async def login(
    request: RequestLoginUser,
    response: Response,
    user_dal: UserDAL = Depends(get_user_dal),
):
    if request.username is None and request.email is None:
        return JSONResponse(
            status_code=400, content={"error_msg": "Username or email is required"}
        )

    db_user = await authenticate_user(
        request.username, request.email, request.password, user_dal
    )

    if db_user is None:
        return JSONResponse(
            status_code=400, content={"error_msg": "Invalid username or password"}
        )
    if db_user.is_verified == False:
        return JSONResponse(
            status_code=400, content={"error_msg": "Account not verified"}
        )

    expires_in = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(data={"sub": db_user.id})

    jti = str(uuid.uuid4())
    refresh_token = create_refresh_token(data={"sub": db_user.id, "jti": jti})

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,  # not settings.debug,
        samesite="None",  # TODO: can't use "Lax" since we need cross-site cookies for the frontend
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # 5 days in seconds
        path="/",
    )
    return JWTToken(
        access_token=access_token,
        token_type="bearer",
        # refresh_token=refresh_token,
        expires_in=expires_in,
    ).model_dump()


# class RequestRefreshToken(BaseModel):
#     refresh_token: str


@router.post("/refresh")
async def refresh(request: Request, user_dal: UserDAL = Depends(get_user_dal)):
    refresh_token = request.cookies.get("refresh_token")
    # breakpoint()
    try:
        payload = decode_token(refresh_token, "refresh_token")
    except JWTError:
        return JSONResponse(
            status_code=400, content={"error_msg": "Invalid refresh token"}
        )

    db_user = await user_dal.get_user_by(filter=(User.id == payload["sub"]))
    if db_user is None:
        return JSONResponse(
            status_code=400, content={"error_msg": "User does not exist"}
        )
    if db_user.is_verified == False:
        return JSONResponse(
            status_code=400, content={"error_msg": "Account not verified"}
        )

    expires_in = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(data={"sub": db_user.id})
    return JWTToken(
        access_token=access_token,
        # refresh_token=request.refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    ).model_dump()


@router.post("/logout")
async def logout(request: Request, current_user: User = Depends(get_current_user)):
    refresh_token = request.cookies.get("refresh_token")
    try:
        payload = decode_token(refresh_token, "refresh_token")
        blacklist_jwt(payload["jti"])
    except JWTError:
        pass
    return JSONResponse(status_code=200, content={"success": True})


from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


class RequestGoogleAuth(BaseModel):
    access_token: str


@router.post("/auth/google")
async def google_auth(
    request: RequestGoogleAuth,
    response: Response,
    user_dal: UserDAL = Depends(get_user_dal),
):
    try:
        payload = id_token.verify_oauth2_token(
            request.access_token,
            google_requests.Request(),
            settings.oid_google_client_id,  # from your env vars
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    google_id = payload["sub"]
    email = payload["email"]
    user_name = payload["name"]
    profile_pic_url = payload["picture"]
    if payload["email_verified"] != True:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    # check if there is account with that google id, if so login
    existing_user = await user_dal.get_user_by(
        filter=(User.google_auth_id == google_id)
    )
    if existing_user is not None:
        # login
        user = existing_user

    else:
        user_by_email = await user_dal.get_user_by_email(email)
        if user_by_email is not None:
            raise HTTPException(
                status_code=400, detail="Email already in use, but not with Google Auth"
            )

        # create new user with google id
        # check if an account has that username
        db_user = await user_dal.get_user_by(filter=(User.username == user_name))
        while db_user is not None:
            user_name = f"{user_name}{randint(0, 9)}"
            db_user = await user_dal.get_user_by(filter=(User.username == user_name))
        user = User(
            id=str(uuid.uuid4()),
            google_auth_id=google_id,
            email=email,
            username=user_name,
            profile_image_storage_key=profile_pic_url,
            password="",
            credit_balance=CREDITS_BY_TIER["free"],
            is_verified=True,
        )

        user = await user_dal.create_user(user)

    expires_in = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(data={"sub": user.id})

    jti = str(uuid.uuid4())
    refresh_token = create_refresh_token(data={"sub": user.id, "jti": jti})

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,  # not settings.debug,
        samesite="None",  # TODO: can't use "Lax" since we need cross-site cookies for the frontend
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # 5 days in seconds
        path="/",
    )
    return JWTToken(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    ).model_dump()
