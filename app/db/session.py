from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

engine = (
    # Serverless: an instance may be frozen between requests, so don't keep connections.
    create_async_engine(settings.database_url, poolclass=NullPool, connect_args=settings.database_connect_args)
    if settings.serverless
    else create_async_engine(settings.database_url, pool_pre_ping=True, connect_args=settings.database_connect_args)
)

AsyncSessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
