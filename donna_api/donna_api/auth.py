import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import redis
from fastapi import APIRouter, Depends, HTTPException, WebSocket, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from donna_api.types import JWTToken, RequestCreateUser, RequestLoginUser
from donna_common.orm.dal.user import UserDAL, get_user_dal
from donna_common.orm.models.user import User
from donna_common.utils.hashing import get_password_hash, verify_password

redis_client = redis.Redis(host="localhost", port=6379, db=0)

# 3. Define the “token URL” that the client will call to get a token:
#    This corresponds to our login endpoint path (e.g. "/token").
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# this should be an environment variable. should this be regenerated on restart?
SECRET_KEY = "a-very-long-random-string-that-you-keep-secret"  # should be high-entropy (at least 256 bits). change this
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # e.g. tokens valid for 1 hour
REFRESH_TOKEN_EXPIRE_DAYS = 5

router = APIRouter()


def blacklist_jwt(jti: str) -> None:
    redis_client.set(jti, "revoked", ex=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))


async def get_current_user(
    token: str = Depends(oauth2_scheme), user_dal: UserDAL = Depends(get_user_dal)
) -> User:
    """
    Dependency that:
      - Reads token from “Authorization: Bearer <token>”
      - Decodes & validates JWT
      - Retrieves user from DB
      - Raises 401 if something fails
      - Returns UserInDB if successful
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
    # if user.disabled:
    #     raise HTTPException(status_code=400, detail="Inactive user")
    return user


async def get_current_user_from_ws(
    websocket: WebSocket, user_dal: UserDAL = Depends(get_user_dal)
):
    """
    Dependency to extract and verify JWT from WebSocket headers.
    """

    # Extract the Sec-WebSocket-Protocol header
    header_value = websocket.headers.get("sec-websocket-protocol")
    if not header_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Sec-WebSocket-Protocol",
        )
    # header_value might look like "access-token, eyJhbGciOiJIUzI1NiIsInR5cCI6..."
    parts = [p.strip() for p in header_value.split(",")]
    if parts[0] != "access-token" or len(parts) < 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid subprotocol format",
        )
    token = parts[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise JWTError("Missing 'sub' in token")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate token"
        )

    credentials_exception = HTTPException(
        status_code=401,  # Unauthorized
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = await user_dal.get_user_by(filter=(User.id == user_id))
    if user is None:
        raise credentials_exception
    # if user.disabled:
    #     raise HTTPException(status_code=400, detail="Inactive user")
    await websocket.accept(subprotocol=header_value)
    return user


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
async def register(user: RequestCreateUser, user_dal: UserDAL = Depends(get_user_dal)):
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
    new_user = User(
        id=str(uuid.uuid4()),
        email=user.email,
        password=hashed_pw,
        username=user.username,
    )
    new_user = await user_dal.create_user(new_user)

    expires_in = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(data={"sub": new_user.id})

    jti = str(uuid.uuid4())
    refresh_token = create_refresh_token(data={"sub": new_user.id, "jti": jti})

    return JWTToken(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
        refresh_token=refresh_token,
    )


@router.post("/login")
async def login(request: RequestLoginUser, user_dal: UserDAL = Depends(get_user_dal)):
    if request.username is None and request.email is None:
        return JSONResponse(
            status_code=400, content={"error_msg": "Username or email is required"}
        )

    db_user = await authenticate_user(
        request.username, request.email, request.password, user_dal
    )
    expires_in = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(data={"sub": db_user.id})

    jti = str(uuid.uuid4())
    refresh_token = create_refresh_token(data={"sub": db_user.id, "jti": jti})

    return JWTToken(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


class RequestRefreshToken(BaseModel):
    refresh_token: str


@router.post("/refresh")
async def refresh(
    request: RequestRefreshToken, user_dal: UserDAL = Depends(get_user_dal)
):
    try:
        payload = decode_token(request.refresh_token, "refresh_token")
    except JWTError:
        return JSONResponse(
            status_code=400, content={"error_msg": "Invalid refresh token"}
        )

    db_user = await user_dal.get_user_by(filter=(User.id == payload["sub"]))
    if db_user is None:
        return JSONResponse(
            status_code=400, content={"error_msg": "User does not exist"}
        )

    expires_in = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(data={"sub": db_user.id})
    return JWTToken(
        access_token=access_token,
        refresh_token=request.refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post("/logout")
async def logout(
    request: RequestRefreshToken,
    #  , current_user: User = Depends(get_current_user)
):
    payload = decode_token(request.refresh_token, "refresh_token")
    blacklist_jwt(payload["jti"])
    return JSONResponse(status_code=200, content={"success": True})
