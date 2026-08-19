"""Public content catalogs: space objects and lessons.

Both are unowned - readable by anyone, writable only by seed loaders
(DATABASE_CONTRACT.md §5). Content is authored by P4 in data/seeds and
data/fallback; the idempotent loaders that push it into PostgreSQL are P2's and
live in database/seeds (DECISION_LOG #18).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Computed, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.learning import LearningProgress

# Full-text search vectors are PostgreSQL GENERATED columns (PG12+), not
# triggers: the database maintains them, and SQLAlchemy knows never to write
# them. `to_tsvector` with a literal regconfig is IMMUTABLE, which is what makes
# it legal in a generated column.
SPACE_OBJECT_TSV = "to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, ''))"
LESSON_TSV = (
    "to_tsvector('english', coalesce(title, '') || ' ' || "
    "coalesce(summary, '') || ' ' || coalesce(content, ''))"
)


class SpaceObject(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "space_objects"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    physical_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    orbital_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    discovery: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    images: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # Provenance: every record traces to its source (ARCHITECTURE.md principle 4).
    source: Mapped[str | None] = mapped_column(String(100))
    source_id: Mapped[str | None] = mapped_column(String(200))
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(SPACE_OBJECT_TSV, persisted=True)
    )

    __table_args__ = (
        Index("idx_spaceobj_category", "category"),
        Index("idx_spaceobj_search", "search_vector", postgresql_using="gin"),
        # Partial unique: this is what makes re-running a seed loader an upsert
        # rather than a duplicate-insert. Bundled records without a source_id are
        # exempt.
        Index(
            "idx_spaceobj_source",
            "source",
            "source_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL"),
        ),
    )


class Lesson(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Learning content.

    `category` + `sort_order` + `prerequisites` already express sequencing, which
    is why no `learning_paths` or `courses` table exists (DECISION_LOG #22).
    """

    __tablename__ = "lessons"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    category: Mapped[str | None] = mapped_column(String(50))
    difficulty: Mapped[str | None] = mapped_column(String(20))
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # Markdown
    equations: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    related_objects: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    related_lessons: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    prerequisites: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(LESSON_TSV, persisted=True)
    )

    progress: Mapped[list["LearningProgress"]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("idx_lessons_category", "category"),
        Index("idx_lessons_search", "search_vector", postgresql_using="gin"),
    )
