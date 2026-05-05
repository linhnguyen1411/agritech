from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.database import DbSession
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    CurrentUserId,
)
from app.core.config import settings
from app.models.user import User
from app.schemas import ApiResponse, LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.ftk_service import FtkService

router = APIRouter()


@router.post("/register", response_model=ApiResponse[TokenResponse], status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: DbSession) -> ApiResponse[TokenResponse]:
    # Check uniqueness
    existing = await db.execute(
        select(User).where((User.email == body.email) | (User.username == body.username))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already taken")

    user = User(
        username=body.username,
        email=str(body.email),
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    # Bootstrap game wallet
    ftk = FtkService(db)
    wallet = await ftk.get_or_create_wallet(str(user.id))
    # Welcome bonus
    await ftk.credit(
        user_id=str(user.id),
        amount=__import__("decimal").Decimal("100"),
        tx_type="mint",
        notes="Welcome bonus",
    )

    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    return ApiResponse.ok(
        TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    )


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(body: LoginRequest, db: DbSession) -> ApiResponse[TokenResponse]:
    result = await db.execute(select(User).where(User.email == str(body.email)))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    return ApiResponse.ok(
        TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    )


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh_token(body: RefreshRequest) -> ApiResponse[TokenResponse]:
    payload = decode_token(body.refresh_token, expected_type="refresh")
    user_id: str = payload["sub"]
    access = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)
    return ApiResponse.ok(
        TokenResponse(
            access_token=access,
            refresh_token=new_refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    )


@router.get("/me", response_model=ApiResponse[UserResponse])
async def get_me(user_id: CurrentUserId, db: DbSession) -> ApiResponse[UserResponse]:
    user = await db.get(User, __import__("uuid").UUID(user_id))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return ApiResponse.ok(UserResponse.model_validate(user))
