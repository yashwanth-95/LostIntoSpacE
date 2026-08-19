"""User and refresh-token models.

Contract: docs/backend/DATABASE_CONTRACT.md §4.1, docs/architecture/DATABASE.md
Decision: DECISION_LOG #16 (only refresh tokens are persisted; access tokens
stay stateless, so logout/revocation has something real to act on).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.conversation import Conversation, SearchHistory
    from src.models.learning import LearningProgress
    from src.models.project import Project

USER_ROLES = ("student", "educator", "admin")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # Never stores a raw password. Hashing is implemented in Phase 5 (auth).
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="student")
    # Accounts are deactivated, never hard-deleted: deleting a user cascades all
    # the way down to simulation results (DATABASE_CONTRACT.md §6, SD-8).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Phase 6. A column on `users`, NOT a `profiles` table - SD-3 rejected that
    # split. Key semantics belong to P1 (theme, units, ...); the backend only
    # bounds size/shape, so a UI toggle never needs a migration.
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    learning_progress: Mapped[list["LearningProgress"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    search_history: Mapped[list["SearchHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(f"role IN {USER_ROLES}", name="role_valid"),
        Index("idx_users_email", "email"),
    )


class RefreshToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One row per issued refresh token.

    A token is valid only while `revoked_at IS NULL AND expires_at > now()`.
    Logout sets `revoked_at`; refresh rotates by issuing a new row and pointing
    the old row's `replaced_by` at it.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # A hash of the token, never the token itself - same rule as password_hash.
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))  # 45 = max IPv6 text length

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        Index("idx_refresh_tokens_hash", "token_hash", unique=True),
        Index("idx_refresh_tokens_user", "user_id"),
    )
