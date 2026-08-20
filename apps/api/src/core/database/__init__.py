"""Async engine and session management.

The DATABASE_URL comes from the environment (see core.config); no credentials
are ever hardcoded here. Phase 4 wires the session factory and the FastAPI
dependency; no route uses it yet.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.exc import InterfaceError, OperationalError
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


def _is_connection_failure(exc: BaseException) -> bool:
    """Whether an exception means "never got a usable connection".

    Checked by walking the ``__cause__`` chain, because the shape differs by
    where the failure happens. A statement that fails mid-session surfaces as a
    SQLAlchemy ``OperationalError``; a failure during pool connect surfaces as
    the *raw driver* exception, since SQLAlchemy's DBAPI-error wrapping has not
    engaged yet. Only checking the SQLAlchemy types misses the second case
    entirely - which is the common one on a fresh checkout, where the password
    is wrong and no connection is ever established.

    Deliberately does not treat every database error as unavailability: a
    ProgrammingError or IntegrityError means the query was wrong, which is a
    server bug and must keep its 500.
    """
    seen: set[int] = set()
    current: BaseException | None = exc

    while current is not None and id(current) not in seen:
        seen.add(id(current))

        if isinstance(current, (OperationalError, InterfaceError, ConnectionError, OSError)):
            return True

        # Driver exceptions, matched by module rather than by import so the API
        # does not have to depend on asyncpg's exception taxonomy directly.
        module = type(current).__module__
        if module.startswith("asyncpg"):
            name = type(current).__name__
            if name in _DRIVER_CONNECTION_ERRORS or "Connection" in name:
                return True

        current = current.__cause__

    return False


#: asyncpg errors that mean the connection could not be established at all.
#: Anything else from asyncpg is a real query or data problem.
_DRIVER_CONNECTION_ERRORS = frozenset(
    {
        "InvalidPasswordError",
        "InvalidAuthorizationSpecificationError",
        "InvalidCatalogNameError",
        "CannotConnectNowError",
        "TooManyConnectionsError",
        "ConnectionDoesNotExistError",
        "ConnectionFailureError",
    }
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session per request.

    Commits on success, rolls back on any exception, always closes. Routes never
    manage the transaction boundary themselves.

    A connection failure is translated to a 503 here rather than being allowed
    to reach the catch-all handler as a 500. "The database is not configured" is
    not a bug in this server, and reporting it as one sends anyone setting the
    project up looking for a defect that does not exist. /health/ready already
    reports the same condition as 503; this makes every other endpoint agree.
    """
    from src.core.exceptions import AppError

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            try:
                await session.rollback()
            except Exception:  # noqa: BLE001 - rollback on a dead connection also fails
                pass

            if _is_connection_failure(exc):
                # The driver's message carries the user and connection details;
                # never echo it.
                raise AppError(
                    503,
                    "DATABASE_UNAVAILABLE",
                    "The database is not reachable. "
                    "See docs/getting-started/LOCAL_SETUP.md.",
                ) from exc
            raise


async def dispose_engine() -> None:
    """Close the pool. Called on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
