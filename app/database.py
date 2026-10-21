"""
SQLAlchemy 2.x Async Database Engine and Session Factory
=========================================================
Uses asyncpg driver. All models import Base from here.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


_engine = None
_async_session_factory = None


def init_db(database_url: str) -> None:
    """Initialize the async engine. Call once at application startup."""
    global _engine, _async_session_factory

    if database_url.startswith("sqlite"):
        _engine = create_async_engine(
            database_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
    else:
        _engine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


async def ensure_db_tables() -> None:
    """Create all database tables and seed initial settings if not present."""
    if _engine is None:
        raise RuntimeError("Database not initialised – call init_db() first.")

    # Import models so Base.metadata knows about them
    import app.models  # noqa: F401

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Ensure a default service_settings row exists
    from sqlalchemy import select
    from app.models import ServiceSettings
    async with _async_session_factory() as session:
        result = await session.execute(select(ServiceSettings).where(ServiceSettings.id == 1))
        if not result.scalar_one_or_none():
            session.add(ServiceSettings(id=1, enabled=True, auto_publish=False))
            await session.commit()



async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a database session and commits/rollbacks."""
    if _async_session_factory is None:
        raise RuntimeError("Database not initialised – call init_db() first.")
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncSession:
    """Returns a new session for use outside of FastAPI dependency injection."""
    if _async_session_factory is None:
        raise RuntimeError("Database not initialised – call init_db() first.")
    return _async_session_factory()


def get_engine():
    if _engine is None:
        raise RuntimeError("Database not initialised – call init_db() first.")
    return _engine
