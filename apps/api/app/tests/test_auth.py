import pytest
from httpx import AsyncClient

from app.tests.conftest import auth_headers, register_user

pytestmark = pytest.mark.asyncio


async def test_register_success(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/game/auth/register",
        json={"username": "alice", "email": "alice@test.com", "password": "Alice123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert "timestamp" in data


async def test_register_duplicate(client: AsyncClient) -> None:
    await register_user(client, "bob")
    resp = await client.post(
        "/api/v1/game/auth/register",
        json={"username": "bob", "email": "bob@test.com", "password": "Bob12345"},
    )
    assert resp.status_code == 409


async def test_login_success(client: AsyncClient) -> None:
    await register_user(client, "charlie")
    resp = await client.post(
        "/api/v1/game/auth/login",
        json={"email": "charlie@test.com", "password": "Tester123"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


async def test_login_wrong_password(client: AsyncClient) -> None:
    await register_user(client, "dave")
    resp = await client.post(
        "/api/v1/game/auth/login",
        json={"email": "dave@test.com", "password": "WrongPass1"},
    )
    assert resp.status_code == 401


async def test_get_me(client: AsyncClient) -> None:
    headers = await auth_headers(client, "eve")
    resp = await client.get("/api/v1/game/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "eve"
