import re
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from backend.app.config import settings

# Engine configuration
db_url = settings.DATABASE_URL
connect_args = {}

if "sqlite" in db_url:
    connect_args["check_same_thread"] = False
elif "asyncpg" in db_url:
    # asyncpg expects ssl argument in connect_args rather than libpq sslmode query string
    if "sslmode=" in db_url or "neon.tech" in db_url:
        connect_args["ssl"] = "require"
        # Disable prepared statement caching for PgBouncer transaction pooling on Neon
        connect_args["prepared_statement_cache_size"] = 0
        connect_args["statement_cache_size"] = 0
        # Clean libpq query parameters that asyncpg rejects
        db_url = re.sub(r"[?&]sslmode=[^&]+", "", db_url)
        db_url = re.sub(r"[?&]channel_binding=[^&]+", "", db_url)
        if "?" not in db_url and "&" in db_url:
            db_url = db_url.replace("&", "?", 1)

from sqlalchemy.pool import NullPool

engine = create_async_engine(
    db_url,
    echo=False,
    connect_args=connect_args,
    poolclass=NullPool,
    future=True,
)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
