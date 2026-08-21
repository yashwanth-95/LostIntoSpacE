"""Seed entrypoint: `python database/seeds/seed_all.py`

Loads the platform catalog into PostgreSQL. The catalog itself is authored in
`data/catalog/` — this module reads it and upserts, and contains no content of
its own (DECISION_LOG #18).

Each loader:
  1. reads from `data/catalog/` — never embeds data inline
  2. upserts on a natural key, so re-running is safe and mid-demo resets work
  3. reports how many rows it created versus updated

## Why the API does not read these tables for catalog content

The catalog is identical for every user and changes when someone edits a Python
module, so the API serves it from `data.catalog` directly and caches it per
worker. These tables exist so that the catalog is *queryable* — full-text search
over objects and lessons, joins from a user's project to the object it targets —
and so an operator can confirm what a deployment contains. The two cannot drift,
because this loader is the only writer and the module is the only source.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import build_engine, build_session_factory

logger = logging.getLogger("seeds")

# Content lives here, authored as Python modules (DECISION_LOG #18).
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_CATALOG_DIR = REPO_ROOT / "data" / "catalog"
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


def _properties_to_json(properties) -> dict:
    """Catalog `Property` records as a JSON object keyed by label.

    Keyed rather than a list because these columns are queried by name — "give
    me every body with a surface gravity below 1 m/s²" — and a list of objects
    makes that a scan.
    """
    out = {}
    for prop in properties:
        entry = {"label": prop.label}
        if prop.value is not None:
            entry["value"] = prop.value
        if prop.unit:
            entry["unit"] = prop.unit
        if prop.display:
            entry["display"] = prop.display
        if prop.note:
            entry["note"] = prop.note
        if prop.earth_ratio is not None:
            entry["earth_ratio"] = prop.earth_ratio
        out[prop.label] = entry
    return out


async def seed_space_objects(session: AsyncSession) -> SeedResult:
    """Upsert the object catalog on (source, source_id) — see idx_spaceobj_source."""
    from data.catalog.space_objects import build_space_objects

    created = updated = 0
    for obj in build_space_objects():
        images = []
        for image in ([obj.image] if obj.image else []) + list(obj.gallery):
            images.append(
                {
                    "url": image.url,
                    "title": image.title,
                    "credit": image.credit,
                    "alt": image.alt,
                    "nasa_id": image.nasa_id,
                    "instrument": image.instrument,
                }
            )

        row = {
            "name": obj.name,
            "category": obj.kind.value,
            "subcategory": obj.classification,
            "description": obj.overview,
            "physical_data": _properties_to_json(obj.physical),
            "orbital_data": _properties_to_json(obj.orbital),
            "discovery": {
                "designation": obj.designation,
                "tagline": obj.tagline,
                "facts": list(obj.facts),
                "parent_id": obj.parent_id,
                "mission_ids": list(obj.mission_ids),
                "concept_slugs": list(obj.concept_slugs),
                "appearance": obj.appearance.model_dump(mode="json"),
            },
            "images": images,
            "source": "bundled_catalog",
            "source_id": obj.id,
            "last_updated": datetime.now(timezone.utc),
        }

        existing = await session.execute(
            text("SELECT id FROM space_objects WHERE source = :source AND source_id = :sid"),
            {"source": row["source"], "sid": row["source_id"]},
        )
        if existing.scalar_one_or_none() is None:
            await session.execute(
                text(
                    """
                    INSERT INTO space_objects
                        (name, category, subcategory, description, physical_data,
                         orbital_data, discovery, images, source, source_id, last_updated)
                    VALUES
                        (:name, :category, :subcategory, :description,
                         CAST(:physical_data AS jsonb), CAST(:orbital_data AS jsonb),
                         CAST(:discovery AS jsonb), CAST(:images AS jsonb),
                         :source, :source_id, :last_updated)
                    """
                ),
                _as_json_params(row),
            )
            created += 1
        else:
            await session.execute(
                text(
                    """
                    UPDATE space_objects SET
                        name = :name, category = :category, subcategory = :subcategory,
                        description = :description,
                        physical_data = CAST(:physical_data AS jsonb),
                        orbital_data = CAST(:orbital_data AS jsonb),
                        discovery = CAST(:discovery AS jsonb),
                        images = CAST(:images AS jsonb),
                        last_updated = :last_updated
                    WHERE source = :source AND source_id = :source_id
                    """
                ),
                _as_json_params(row),
            )
            updated += 1

    return SeedResult("space_objects", created=created, updated=updated)


async def seed_lessons(session: AsyncSession) -> SeedResult:
    """Upsert the science library on `slug`."""
    from data.catalog.science import build_science_topics

    created = updated = 0
    for order, topic in enumerate(build_science_topics()):
        # The lessons table stores one text body; the topic is authored as
        # sections. Flattening keeps full-text search working over the whole
        # lesson, which is what this table is for.
        body_parts = []
        equations = []
        for section in topic.sections:
            body_parts.append("## {0}\n\n{1}".format(section.heading, section.body))
            if section.equation:
                equations.append({"heading": section.heading, "equation": section.equation})
            if section.worked_example:
                body_parts.append("Worked example:\n{0}".format(section.worked_example))
        if topic.interactive and topic.interactive.equation:
            equations.append(
                {"heading": topic.interactive.title, "equation": topic.interactive.equation}
            )

        row = {
            "title": topic.title,
            "slug": topic.slug,
            "category": topic.strand,
            "difficulty": topic.level,
            "summary": topic.summary,
            "content": "\n\n".join(body_parts),
            "equations": equations,
            "related_objects": list(topic.object_ids),
            "related_lessons": list(topic.experiment_ids),
            "prerequisites": list(topic.prerequisites),
            "sort_order": order,
        }

        existing = await session.execute(
            text("SELECT id FROM lessons WHERE slug = :slug"), {"slug": topic.slug}
        )
        if existing.scalar_one_or_none() is None:
            await session.execute(
                text(
                    """
                    INSERT INTO lessons
                        (title, slug, category, difficulty, summary, content, equations,
                         related_objects, related_lessons, prerequisites, sort_order)
                    VALUES
                        (:title, :slug, :category, :difficulty, :summary, :content,
                         CAST(:equations AS jsonb), CAST(:related_objects AS jsonb),
                         CAST(:related_lessons AS jsonb), CAST(:prerequisites AS jsonb),
                         :sort_order)
                    """
                ),
                _as_json_params(row),
            )
            created += 1
        else:
            await session.execute(
                text(
                    """
                    UPDATE lessons SET
                        title = :title, category = :category, difficulty = :difficulty,
                        summary = :summary, content = :content,
                        equations = CAST(:equations AS jsonb),
                        related_objects = CAST(:related_objects AS jsonb),
                        related_lessons = CAST(:related_lessons AS jsonb),
                        prerequisites = CAST(:prerequisites AS jsonb),
                        sort_order = :sort_order
                    WHERE slug = :slug
                    """
                ),
                _as_json_params(row),
            )
            updated += 1

    return SeedResult("lessons", created=created, updated=updated)


def _as_json_params(row: dict) -> dict:
    """Serialise the dict/list values so asyncpg can bind them as text.

    asyncpg will not adapt a Python dict to a parameter, and the SQL casts each
    of these to jsonb, so they have to arrive as JSON strings.
    """
    return {
        key: json.dumps(value) if isinstance(value, (dict, list)) else value
        for key, value in row.items()
    }


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
