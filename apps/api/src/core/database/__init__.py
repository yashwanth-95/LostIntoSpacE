"""Async engine and session management.

The DATABASE_URL comes from the environment (see core.config); no credentials
are ever hardcoded here. Phase 4 wires the session factory and the FastAPI
dependency; no route uses it yet.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import Settings, get_settings
from src.core.database.base import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

__all__ = [
    "Base",
    "CreatedAtMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "build_engine",
    "build_session_factory",
    "get_db",
    "get_engine",
    "get_session_factory",
]


def build_engine(settings: Settings) -> AsyncEngine:
    """Create an async engine. Separate from the module-level singleton so tests
    can build a throwaway engine against a different database.
    """
    return create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,  # drop dead connections rather than failing a request
        future=True,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,  # keep attributes usable after commit in request handlers
        autoflush=False,
    )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Lazily-created process-wide engine.

    Lazy on purpose: importing this module must not open a connection pool, so
    that model imports, Alembic, and the test suite stay usable with no database
    running.
    """
    global _engine
    if _engine is None:
        _engine = build_engine(get_settings())
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = build_session_factory(get_engine())
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session per request.

    Commits on success, rolls back on any exception, always closes. Routes never
    manage the transaction boundary themselves.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close the pool. Called on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
