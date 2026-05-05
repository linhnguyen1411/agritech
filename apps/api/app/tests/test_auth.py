"""Tests for POST /auth/login, POST /auth/refresh, POST /auth/register, GET /auth/me.

Covers
------
- Email/password registration and login
- Duplicate username / email rejection
- Wrong password rejection
- Token refresh
- /me endpoint
- Nonce generation endpoint
- Wallet login with invalid signature (mocked)
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch

from app.tests.conftest import auth_headers, register_user

pytestmark = pytest.mark.asyncio

PREFIX = "/api/v1/game/auth"


# ── Registration ──────────────────────────────────────────────────────────────

async def test_register_success(client: AsyncClient) -> None:
    resp = await client.post(
        f"{PREFIX}/register",
        json={"username": "alice", "email": "alice@test.com", "password": "Alice123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    token_data = body["data"]
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["expires_in"] == 15 * 60  # 15 minutes
    assert "timestamp" in body


async def test_register_duplicate_email(client: AsyncClient) -> None:
    await register_user(client, "bob")
    resp = await client.post(
        f"{PREFIX}/register",
        json={"username": "bob2", "email": "bob@test.com", "password": "Bob12345"},
    )
    assert resp.status_code == 409
    assert resp.json()["success"] is False


async def test_register_duplicate_username(client: AsyncClient) -> None:
    await register_user(client, "charlie")
    resp = await client.post(
        f"{PREFIX}/register",
        json={"username": "charlie", "email": "charlie2@test.com", "password": "Charlie1"},
    )
    assert resp.status_code == 409


async def test_register_weak_password(client: AsyncClient) -> None:
    resp = await client.post(
        f"{PREFIX}/register",
        json={"username": "dave", "email": "dave@test.com", "password": "weakpass"},
    )
    assert resp.status_code == 422   # Pydantic validation error


# ── Login ─────────────────────────────────────────────────────────────────────

async def test_login_password_success(client: AsyncClient) -> None:
    await register_user(client, "eve")
    resp = await client.post(
        f"{PREFIX}/login",
        json={"email": "eve@test.com", "password": "Tester123"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


async def test_login_wrong_password(client: AsyncClient) -> None:
    await register_user(client, "frank")
    resp = await client.post(
        f"{PREFIX}/login",
        json={"email": "frank@test.com", "password": "WrongPass1"},
    )
    assert resp.status_code == 401
    assert resp.json()["success"] is False


async def test_login_unknown_email(client: AsyncClient) -> None:
    resp = await client.post(
        f"{PREFIX}/login",
        json={"email": "nobody@test.com", "password": "NoPass123"},
    )
    assert resp.status_code == 401


async def test_login_no_method_raises_422(client: AsyncClient) -> None:
    resp = await client.post(f"{PREFIX}/login", json={"email": "x@test.com"})
    assert resp.status_code == 422


# ── Nonce ─────────────────────────────────────────────────────────────────────

async def test_request_nonce(client: AsyncClient) -> None:
    resp = await client.post(
        f"{PREFIX}/nonce",
        json={"wallet_address": "0xAbCd1234AbCd1234AbCd1234AbCd1234AbCd1234"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["nonce"]) == 32
    assert "AgriTech" in data["message"]
    assert data["expires_in"] == 300


async def test_wallet_login_invalid_signature(client: AsyncClient) -> None:
    """Wallet login with a bad signature must be rejected."""
    wallet = "0xAbCd1234AbCd1234AbCd1234AbCd1234AbCd1234"
    # Get nonce
    await client.post(f"{PREFIX}/nonce", json={"wallet_address": wallet})

    # Attempt login with garbage signature
    resp = await client.post(
        f"{PREFIX}/login",
        json={"wallet_address": wallet, "signature": "0xdeadbeef"},
    )
    assert resp.status_code == 401


async def test_wallet_login_valid_signature(client: AsyncClient) -> None:
    """Wallet login with a valid EIP-191 signature succeeds."""
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from app.core.security import _wallet_login_message

    acct = Account.create()
    wallet = acct.address

    # 1. Get nonce
    nonce_resp = await client.post(f"{PREFIX}/nonce", json={"wallet_address": wallet})
    assert nonce_resp.status_code == 200
    nonce_data = nonce_resp.json()["data"]
    nonce = nonce_data["nonce"]

    # 2. Sign message
    message = _wallet_login_message(wallet, nonce)
    msg = encode_defunct(text=message)
    signed = acct.sign_message(msg)

    # 3. Login
    resp = await client.post(
        f"{PREFIX}/login",
        json={"wallet_address": wallet, "signature": signed.signature.hex()},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


# ── Refresh ───────────────────────────────────────────────────────────────────

async def test_refresh_token(client: AsyncClient) -> None:
    data = await register_user(client, "grace")
    resp = await client.post(
        f"{PREFIX}/refresh",
        json={"refresh_token": data["refresh_token"]},
    )
    assert resp.status_code == 200
    new_tokens = resp.json()["data"]
    assert new_tokens["access_token"] != data["access_token"]


async def test_refresh_with_access_token_fails(client: AsyncClient) -> None:
    data = await register_user(client, "heidi")
    resp = await client.post(
        f"{PREFIX}/refresh",
        json={"refresh_token": data["access_token"]},  # wrong token type
    )
    assert resp.status_code == 401


# ── /me ───────────────────────────────────────────────────────────────────────

async def test_get_me(client: AsyncClient) -> None:
    headers = await auth_headers(client, "ivan")
    resp = await client.get(f"{PREFIX}/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "ivan"


async def test_get_me_no_token(client: AsyncClient) -> None:
    resp = await client.get(f"{PREFIX}/me")
    assert resp.status_code == 403
