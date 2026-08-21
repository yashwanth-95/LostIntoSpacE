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
from sqlalchemy import text
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
    # No pool: an asyncpg connection belongs to the loop that opened it, and
    # TestClient does not share a loop with this fixture. See build_engine.
    engine = build_engine(settings, pooled=False)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            yield session
            await session.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def live_client() -> AsyncGenerator[TestClient, None]:
    """A TestClient wired to TEST_DATABASE_URL, for HTTP-level integration tests.

    Skips without TEST_DATABASE_URL, same as `db_session`.

    ## Why this commits, and cleans up afterwards

    The obvious design — roll back at the end of every request — works only if
    every request shares one connection, because an uncommitted write is
    invisible to any other connection. That made multi-request flows like
    register → login → read pass, but only by accident: it depended on the pool
    handing the same connection back each time.

    It also made the suite unrunnable. An asyncpg connection belongs to the loop
    that opened it, `TestClient` runs the application in its own loop, and a
    pooled connection crossing between them fails with "got Future attached to a
    different loop". CI was the first place this surfaced, because the tests
    were being skipped everywhere else.

    So requests commit, exactly as they do in production, and the tables are
    truncated afterwards. Each request is then independent — which is what it is
    in production too — and nothing persists between tests, so re-running the
    suite can never hit a stale UNIQUE-constraint conflict from a previous run.

    Truncation only ever touches TEST_DATABASE_URL. `database_url` is not
    reachable from here at all, so a misconfiguration cannot wipe development
    data.
    """
    url = _test_database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")

    settings = get_settings().model_copy(update={"database_url": url})
    # No pool: an asyncpg connection belongs to the loop that opened it, and
    # TestClient does not share a loop with this fixture. See build_engine.
    engine = build_engine(settings, pooled=False)
    session_factory = build_session_factory(engine)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        await _truncate_all(engine)
        await engine.dispose()


#: Tables the seeded catalog owns. Truncating them would make every test that
#: follows run against an empty catalog, and the failure would look like a bug
#: in whatever ran next rather than in the cleanup.
_PRESERVED_TABLES = ("alembic_version", "space_objects", "lessons")


async def _truncate_all(engine) -> None:
    """Empty every per-user table in the test database.

    One `TRUNCATE ... CASCADE` rather than per-table deletes: it respects
    foreign keys without needing them ordered, and it resets the tables in a
    single statement.
    """
    excluded = ", ".join("'{0}'".format(name) for name in _PRESERVED_TABLES)
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename NOT IN ({0})".format(excluded)
            )
        )
        tables = [row[0] for row in result]
        if tables:
            await connection.execute(
                text(
                    "TRUNCATE TABLE {0} RESTART IDENTITY CASCADE".format(
                        ", ".join('"{0}"'.format(name) for name in tables)
                    )
                )
            )
