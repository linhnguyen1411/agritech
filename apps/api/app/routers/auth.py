"""Auth router.

Endpoints
---------
POST /auth/nonce      – request a one-time nonce for Web3 wallet login
POST /auth/login      – password OR wallet+signature login
POST /auth/refresh    – rotate access token
POST /auth/register   – email/password registration
GET  /auth/me         – current user profile

Rate limit: 10 req / 60 s per IP / user (AUTH_RATE_LIMIT_PER_MINUTE).
"""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.config import settings
from app.core.database import DbSession
from app.core.redis import cache_delete, cache_get, cache_set
from app.core.security import (
    AuthRateLimit,
    CurrentUserId,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    verify_wallet_signature,
    _wallet_login_message,
)
from app.models.user import User
from app.schemas import ApiResponse, TokenResponse
from app.schemas.auth import (
    LoginRequest,
    NonceRequest,
    NonceResponse,
    RefreshRequest,
    RegisterRequest,
    UserResponse,
)
from app.services.ftk_service import FtkService

router = APIRouter()

_RATE = {"dependencies": [AuthRateLimit]}   # shorthand applied to all handlers


# ── Helper: issue tokens + ensure wallet ─────────────────────────────────────

async def _issue_tokens(user: User, db: DbSession) -> TokenResponse:
    """Create JWT pair and bootstrap game_wallet if missing."""
    ftk = FtkService(db)
    await ftk.get_or_create_wallet(str(user.id))

    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── Nonce for Web3 login ──────────────────────────────────────────────────────

@router.post(
    "/nonce",
    response_model=ApiResponse[NonceResponse],
    summary="Get a one-time nonce to sign with your wallet",
    **_RATE,
)
async def request_nonce(body: NonceRequest) -> ApiResponse[NonceResponse]:
    """Generates a random nonce stored in Redis (TTL=5 min).

    The client must sign the `message` field with personal_sign (EIP-191)
    and submit the signature to `POST /login`.
    """
    nonce = uuid.uuid4().hex          # 32-char random hex
    redis_key = f"nonce:{body.wallet_address.lower()}"

    await cache_set(redis_key, nonce, ttl=settings.NONCE_TTL_SECONDS)

    message = _wallet_login_message(body.wallet_address, nonce)
    return ApiResponse.ok(
        NonceResponse(
            wallet_address=body.wallet_address,
            nonce=nonce,
            message=message,
            expires_in=settings.NONCE_TTL_SECONDS,
        )
    )


# ── Login (password OR wallet) ────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=ApiResponse[TokenResponse],
    summary="Login with email/password or wallet signature",
    **_RATE,
)
async def login(body: LoginRequest, db: DbSession) -> ApiResponse[TokenResponse]:
    if body.is_wallet_login:
        tokens = await _wallet_login(body, db)
    else:
        tokens = await _password_login(body, db)
    return ApiResponse.ok(tokens)


async def _password_login(body: LoginRequest, db: DbSession) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == str(body.email)))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(str(body.password), user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    return await _issue_tokens(user, db)


async def _wallet_login(body: LoginRequest, db: DbSession) -> TokenResponse:
    wallet_addr = str(body.wallet_address).lower()
    redis_key = f"nonce:{wallet_addr}"

    # 1. Retrieve nonce from Redis
    nonce = await cache_get(redis_key)
    if nonce is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Nonce expired or not found. Call POST /auth/nonce first.",
        )

    # 2. Verify EIP-191 signature
    valid = verify_wallet_signature(
        wallet_address=str(body.wallet_address),
        nonce=str(nonce),
        signature=str(body.signature),
    )
    if not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid wallet signature")

    # 3. Consume nonce (prevents replay attacks)
    await cache_delete(redis_key)

    # 4. Find or create user
    result = await db.execute(
        select(User).where(User.wallet_address == str(body.wallet_address))
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Auto-register on first wallet login
        user = User(
            username=f"player_{uuid.uuid4().hex[:8]}",
            email=f"{wallet_addr}@wallet.local",
            hashed_password=hash_password(uuid.uuid4().hex),  # unusable password
            wallet_address=str(body.wallet_address),
        )
        db.add(user)
        await db.flush()

        # Welcome bonus for new wallet users
        ftk = FtkService(db)
        await ftk.credit(
            user_id=str(user.id),
            amount=Decimal("100"),
            tx_type="mint",
            notes="Welcome bonus (wallet login)",
        )
    elif not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    return await _issue_tokens(user, db)


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=ApiResponse[TokenResponse],
    summary="Rotate access token using a valid refresh token",
    **_RATE,
)
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


# ── Register ──────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=ApiResponse[TokenResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account with email and password",
    **_RATE,
)
async def register(body: RegisterRequest, db: DbSession) -> ApiResponse[TokenResponse]:
    existing = await db.execute(
        select(User).where(
            (User.email == str(body.email)) | (User.username == body.username)
        )
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

    ftk = FtkService(db)
    await ftk.credit(
        user_id=str(user.id),
        amount=Decimal("100"),
        tx_type="mint",
        notes="Welcome bonus",
    )
    return ApiResponse.ok(await _issue_tokens(user, db))


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=ApiResponse[UserResponse],
    summary="Get current authenticated user's profile",
)
async def get_me(user_id: CurrentUserId, db: DbSession) -> ApiResponse[UserResponse]:
    user = await db.get(User, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return ApiResponse.ok(UserResponse.model_validate(user))
