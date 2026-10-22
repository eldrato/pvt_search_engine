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
        # First attempt primary PostgreSQL/SQLite URL
        is_sqlite = "sqlite" in settings.DATABASE_URL
        engine_kwargs = {"echo": False}
        if not is_sqlite:
            engine_kwargs.update({"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20})

        _engine = create_async_engine(
            settings.DATABASE_URL,
            **engine_kwargs
        )
        _sessionmaker = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )
        _active_db_type = "sqlite" if is_sqlite else "postgres"
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
    import app.models.source    # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Check and add privacy_tier to documents table if missing
        try:
            if engine.dialect.name == "sqlite" or _active_db_type == "sqlite":
                col_check = await conn.execute(text("PRAGMA table_info(documents)"))
                cols = [row[1] for row in col_check.fetchall()]
                if cols and "privacy_tier" not in cols:
                    await conn.execute(text("ALTER TABLE documents ADD COLUMN privacy_tier VARCHAR(32) DEFAULT 'private'"))
                    logger.info("Migrated SQLite 'documents' table: added 'privacy_tier' column.")
            else:
                await conn.execute(text(
                    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS privacy_tier VARCHAR(32) DEFAULT 'private'"
                ))
        except Exception as col_err:
            logger.warning(f"Column check for privacy_tier: {col_err}")

        # Seed default source configurations if table is empty
        try:
            from app.models.source import SourceConfig
            check_sources = await conn.execute(text("SELECT COUNT(*) FROM source_configs"))
            count = check_sources.scalar() or 0
            if count == 0:
                defaults = [
                    ("upload", "Documents", True, "private", "Uploaded PDFs, Word documents, Markdown and text files", "FileText"),
                    ("note", "Personal Notes", True, "private", "Captured personal notes, ideas and thoughts", "BookOpen"),
                    ("code", "Source Code", True, "private", "Ingested code repositories, scripts and notebooks", "Code2"),
                    ("web", "Web Crawls", True, "public", "Allowlisted web pages and crawler extractions", "Globe"),
                ]
                for st, dn, en, pt, desc, icon in defaults:
                    await conn.execute(text(
                        "INSERT INTO source_configs (source_type, display_name, enabled, default_privacy_tier, description, icon, created_at, updated_at) "
                        "VALUES (:st, :dn, :en, :pt, :desc, :icon, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ), {"st": st, "dn": dn, "en": 1 if en else 0, "pt": pt, "desc": desc, "icon": icon})
                logger.info("Seeded default source configurations for Phase 6 Knowledge Engine.")
        except Exception as seed_err:
            logger.debug(f"Source seeding check: {seed_err}")

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
