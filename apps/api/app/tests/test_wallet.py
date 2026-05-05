import pytest
from httpx import AsyncClient

from app.tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio


async def test_get_wallet(client: AsyncClient) -> None:
    headers = await auth_headers(client, "wallet_user")
    resp = await client.get("/api/v1/game/wallet/", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["level"] == 1
    # Welcome bonus should be credited
    assert float(data["ftk_balance"]) >= 100.0


async def test_wallet_history(client: AsyncClient) -> None:
    headers = await auth_headers(client, "hist_user")
    resp = await client.get("/api/v1/game/wallet/history", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    # At least the welcome bonus entry
    assert len(body["data"]["items"]) >= 1
