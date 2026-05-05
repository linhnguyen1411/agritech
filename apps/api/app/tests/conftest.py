"""Pytest fixtures for the FastAPI test suite.

Uses an in-memory SQLite database (via aiosqlite) so no Postgres needed
for unit / integration tests.
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.main import app
from app.models.base import Base

# ── In-memory test database ───────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
_TestSession = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables() -> None:  # type: ignore[misc]
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:  # type: ignore[misc]
    async with _TestSession() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:  # type: ignore[misc]
    """HTTP test client with overridden DB dependency."""

    async def _override_db():  # type: ignore[no-untyped-def]
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def register_user(
    client: AsyncClient, username: str = "tester", password: str = "Tester123"
) -> dict:
    """Register and return token response dict."""
    resp = await client.post(
        "/api/v1/game/auth/register",
        json={"username": username, "email": f"{username}@test.com", "password": password},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def auth_headers(client: AsyncClient, username: str = "tester") -> dict:
    data = await register_user(client, username)
    return {"Authorization": f"Bearer {data['access_token']}"}
