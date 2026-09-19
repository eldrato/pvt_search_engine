import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import logger


class Base(DeclarativeBase):
    pass


_engine = None
_sessionmaker = None
_active_db_type = "postgres"


def get_engine():
    global _engine, _sessionmaker, _active_db_type
    if _engine is not None:
        return _engine

    try:
        # First attempt primary PostgreSQL URL
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
        _sessionmaker = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )
        _active_db_type = "postgres"
        logger.info(f"Database configured with primary URL: {settings.DATABASE_URL.split('@')[-1]}")
    except Exception as e:
        if settings.USE_SQLITE_FALLBACK:
            logger.warning(f"Failed to configure primary database ({e}). Falling back to local SQLite: {settings.FALLBACK_SQLITE_URL}")
            _engine = create_async_engine(
                settings.FALLBACK_SQLITE_URL,
                echo=False
            )
            _sessionmaker = async_sessionmaker(
                bind=_engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False
            )
            _active_db_type = "sqlite"
        else:
            raise

    return _engine


def get_sessionmaker():
    global _sessionmaker
    if _sessionmaker is None:
        get_engine()
    return _sessionmaker


def get_active_db_type() -> str:
    global _active_db_type
    return _active_db_type


async def init_db():
    """Ensure all tables are created in the active database."""
    global _engine, _sessionmaker, _active_db_type
    engine = get_engine()
    # Test if primary connection works or switch to SQLite
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as err:
        if settings.USE_SQLITE_FALLBACK and _active_db_type == "postgres":
            logger.warning(f"PostgreSQL probe failed ({err}). Switching active engine to SQLite.")
            _engine = create_async_engine(
                settings.FALLBACK_SQLITE_URL,
                echo=False
            )
            _sessionmaker = async_sessionmaker(
                bind=_engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False
            )
            _active_db_type = "sqlite"
            engine = _engine

    # Import models so Base.metadata has all table definitions
    import app.models.document  # noqa: F401
    import app.models.crawler   # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"Database schema initialized successfully [Engine: {_active_db_type}]")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
        except Exception as exc:
            logger.error(f"Database session error: {exc}")
            await session.rollback()
            raise
        finally:
            await session.close()
