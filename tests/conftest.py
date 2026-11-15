"""Integration tests against a real Postgres database.

Uses $TEST_POSTGRES_DB (default "terminator_test"); it is created if missing and
its tables are dropped/recreated on every run, so it must never be a real DB.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Callable

os.environ["POSTGRES_DB"] = os.environ.get("TEST_POSTGRES_DB", "terminator_test")
os.environ["ENVIRONMENT"] = "local"
os.environ["DEV_LOGIN_ENABLED"] = "true"
os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
os.environ["SPOTIFY_CLIENT_ID"] = ""
os.environ["ADMIN_EMAILS"] = ""

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import pool, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core import security  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User  # noqa: E402

assert settings.POSTGRES_DB.endswith("_test"), "refusing to run tests against a non-test database"

engine = create_async_engine(settings.database_url, poolclass=pool.NullPool)
TestSession = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def _override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


async def _prepare_database() -> None:
    url = settings.database_url
    conn = await asyncpg.connect(
        host=url.host, port=url.port, user=url.username, password=url.password, database="postgres"
    )
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database):
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database():
    asyncio.run(_prepare_database())


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def _clean_tables():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as c:
        await c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def client(_clean_tables) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def make_user(_clean_tables) -> Callable:
    async def _make(email: str = "sarah@example.com", name: str = "Sarah Connor") -> dict:
        async with TestSession() as s:
            user = User(email=email, full_name=name)
            s.add(user)
            await s.commit()
            token = security.create_access_token(user.id)
            return {"id": user.id, "headers": {"Authorization": f"Bearer {token}"}}

    return _make


@pytest.fixture
async def user(make_user) -> dict:
    return await make_user()
