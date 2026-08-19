"""Seed entrypoint: `python database/seeds/seed_all.py`

STRUCTURE ONLY - Phase 4 defines the contract and the idempotency mechanism;
it loads nothing, because the content it would load does not exist yet.
P4 authors that content in `data/seeds/` and `data/fallback/` (DECISION_LOG #18).

Each loader added here must:
  1. read from `data/seeds/` or `data/fallback/` - never embed data inline
  2. upsert, never plain-insert, so re-running is safe
  3. report how many rows it created vs. updated
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import build_engine, build_session_factory

logger = logging.getLogger("seeds")

# P4-owned content directories (DECISION_LOG #18).
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_SEEDS_DIR = REPO_ROOT / "data" / "seeds"
DATA_FALLBACK_DIR = REPO_ROOT / "data" / "fallback"


class SeedResult:
    def __init__(self, name: str, created: int = 0, updated: int = 0, skipped: str | None = None):
        self.name = name
        self.created = created
        self.updated = updated
        self.skipped = skipped

    def __str__(self) -> str:
        if self.skipped:
            return f"{self.name}: skipped ({self.skipped})"
        return f"{self.name}: {self.created} created, {self.updated} updated"


async def seed_space_objects(session: AsyncSession) -> SeedResult:
    """Upsert on (source, source_id) - see idx_spaceobj_source.

    Not implemented: waiting on P4's content in data/seeds/.
    """
    if not DATA_SEEDS_DIR.exists() or not any(DATA_SEEDS_DIR.glob("*.json")):
        return SeedResult("space_objects", skipped="no content in data/seeds/ yet (P4)")
    raise NotImplementedError(
        "Content found in data/seeds/ but no loader is implemented yet. "
        "Implement the upsert here rather than letting seeding silently no-op."
    )


async def seed_lessons(session: AsyncSession) -> SeedResult:
    """Upsert on `slug` (unique).

    Not implemented: waiting on P4's content in data/seeds/.
    """
    if not DATA_SEEDS_DIR.exists() or not any(DATA_SEEDS_DIR.glob("*.json")):
        return SeedResult("lessons", skipped="no content in data/seeds/ yet (P4)")
    raise NotImplementedError("Content found in data/seeds/ but no loader is implemented yet.")


SEEDERS: tuple[Callable[[AsyncSession], Awaitable[SeedResult]], ...] = (
    seed_space_objects,
    seed_lessons,
)


async def run_all() -> list[SeedResult]:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    results: list[SeedResult] = []
    try:
        async with session_factory() as session:
            for seeder in SEEDERS:
                result = await seeder(session)
                results.append(result)
                logger.info("%s", result)
            await session.commit()
    finally:
        await engine.dispose()
    return results


def main() -> None:
    # run_all() already logs one line per seeder; printing them again here would
    # duplicate every line.
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run_all())


if __name__ == "__main__":
    main()
