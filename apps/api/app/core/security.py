import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status
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


# ── FastAPI dependencies ──────────────────────────────────────────────────────

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


# Annotated shortcut
CurrentUserId = Annotated[str, Depends(get_current_user_id)]
