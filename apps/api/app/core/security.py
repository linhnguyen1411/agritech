"""Security utilities: JWT, password hashing, Web3 signature,
and per-endpoint rate-limit FastAPI dependency.
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ── Password hashing ──────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
http_bearer = HTTPBearer(auto_error=True)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Web3 signature verification ───────────────────────────────────────────────

def verify_wallet_signature(wallet_address: str, nonce: str, signature: str) -> bool:
    """Return True if `signature` was produced by `wallet_address` signing the
    standard login message that includes `nonce`.

    Uses eth_account (EIP-191 personal_sign format).
    """
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct

        message = _wallet_login_message(wallet_address, nonce)
        msg = encode_defunct(text=message)
        recovered = Account.recover_message(msg, signature=signature)
        return recovered.lower() == wallet_address.lower()
    except Exception:
        return False


def _wallet_login_message(wallet_address: str, nonce: str) -> str:
    return (
        f"Welcome to AgriTech Farm Game!\n"
        f"Sign this message to verify your wallet.\n\n"
        f"Wallet: {wallet_address}\n"
        f"Nonce: {nonce}"
    )


# ── JWT helpers ───────────────────────────────────────────────────────────────

TokenType = Literal["access", "refresh"]


def _make_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra: dict | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: str, roles: list[str] | None = None) -> str:
    return _make_token(
        subject=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra={"roles": roles or []},
    )


def create_refresh_token(user_id: str) -> str:
    return _make_token(
        subject=user_id,
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType = "access") -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise credentials_exception

    if payload.get("type") != expected_type:
        raise credentials_exception

    return payload


# ── FastAPI auth dependency ───────────────────────────────────────────────────

def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(http_bearer)],
) -> str:
    """Returns the user_id (str UUID) from a valid access token."""
    payload = decode_token(credentials.credentials, expected_type="access")
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )
    return user_id


# Annotated shortcut used by routers
CurrentUserId = Annotated[str, Depends(get_current_user_id)]


# ── Per-endpoint rate limit dependencies ──────────────────────────────────────

def make_rate_limit_dep(limit: int, window_seconds: int = 60):  # type: ignore[no-untyped-def]
    """Factory that returns a FastAPI dependency enforcing `limit` req / window.

    Identifier: Bearer sub (user) → IP address (fallback).
    """
    from app.core.redis import check_rate_limit  # local import avoids circular

    async def _dep(request: Request) -> None:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                payload = decode_token(auth[7:], expected_type="access")
                identifier = f"rl:user:{payload['sub']}:{request.url.path}"
            except HTTPException:
                identifier = f"rl:ip:{_ip(request)}:{request.url.path}"
        else:
            identifier = f"rl:ip:{_ip(request)}:{request.url.path}"

        allowed, remaining = await check_rate_limit(
            identifier, limit=limit, window_seconds=window_seconds
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {limit} requests per {window_seconds}s",
                headers={"Retry-After": str(window_seconds)},
            )
        request.state.rate_limit_remaining = remaining

    return _dep


def _ip(request: Request) -> str:
    # Respect X-Forwarded-For from trusted reverse proxy
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Pre-built dependency instances
AuthRateLimit = Depends(make_rate_limit_dep(limit=settings.AUTH_RATE_LIMIT_PER_MINUTE))
WalletRateLimit = Depends(make_rate_limit_dep(limit=settings.AUTH_RATE_LIMIT_PER_MINUTE))
