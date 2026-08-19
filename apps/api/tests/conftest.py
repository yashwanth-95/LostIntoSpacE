"""Shared test fixtures.

Most of the suite needs no database: models are compiled to PostgreSQL DDL with
a dialect object rather than a connection. Tests that genuinely need a live
server use the `db_session` fixture, which SKIPS when TEST_DATABASE_URL is unset
rather than failing - so `pytest` stays green on a machine with no PostgreSQL,
while still running for real in CI or on a developer machine that has one.
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import build_engine, build_session_factory, get_db
from src.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _test_database_url() -> str | None:
    return get_settings().test_database_url


requires_db = pytest.mark.skipif(
    _test_database_url() is None,
    reason="TEST_DATABASE_URL is not set; skipping tests that need a live PostgreSQL",
)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """A session against the TEST database, rolled back after each test.

    Never points at `database_url` - a test must not be able to touch
    development data even by misconfiguration.
    """
    url = _test_database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")

    settings = get_settings().model_copy(update={"database_url": url})
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            yield session
            await session.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def live_client() -> AsyncGenerator[TestClient, None]:
    """A TestClient wired to TEST_DATABASE_URL via a get_db dependency
    override, for full HTTP-level integration tests. Skips without
    TEST_DATABASE_URL, same as db_session.

    Unlike production get_db (which commits), this ALWAYS rolls back at the
    end of the request - never at the end of the test. Routes still see their
    own writes within the request (flush() makes them visible mid-transaction)
    so multi-step flows like register -> login work, but nothing persists
    between test runs, so re-running the suite can never hit a stale
    UNIQUE-constraint conflict from a previous run's leftover data.
    """
    url = _test_database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")

    settings = get_settings().model_copy(update={"database_url": url})
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
