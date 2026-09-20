from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from nexusflow.config import settings


engine = create_async_engine(
    settings.database_url,

    # ----------------------------------------------------------
    # Connection reliability
    # ----------------------------------------------------------

    pool_pre_ping=True,

    # ----------------------------------------------------------
    # Connection pool
    # ----------------------------------------------------------

    pool_size=settings.db_pool_size,

    max_overflow=settings.db_max_overflow,

    pool_timeout=settings.db_pool_timeout,

    pool_recycle=settings.db_pool_recycle,

    # ----------------------------------------------------------
    # Development SQL logging
    # ----------------------------------------------------------

    echo=settings.debug,
)


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session