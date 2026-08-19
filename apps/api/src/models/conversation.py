"""Conversations, messages, and search history.

Conversation ownership (DATABASE_CONTRACT.md §2.6, §5): `messages` deliberately
carries NO user_id. Ownership is inherited through conversation_id. Messages are
always fetched in conversation context, so the authorization join is on a path
already being taken; a denormalized owner column could contradict its parent.
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.user import User

CONVERSATION_CONTEXT_TYPES = ("general", "tutor", "failure_analysis", "recommendation")
CONVERSATION_STATUSES = ("active", "archived")
MESSAGE_ROLES = ("user", "assistant", "system")


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200))
    context_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="general")
    # Soft link, intentionally NOT a foreign key: a conversation can be about a
    # mission, a simulation run, or a lesson, and should survive deletion of
    # whatever it was about. Cost: readers must tolerate a dangling reference.
    # Shape: {"type": "simulation_run", "id": "..."}
    context_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(f"context_type IN {CONVERSATION_CONTEXT_TYPES}", name="context_type_valid"),
        CheckConstraint(f"status IN {CONVERSATION_STATUSES}", name="status_valid"),
        Index("idx_conversations_user", "user_id", text("updated_at DESC")),
    )


class Message(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # References to the deterministic data an answer is grounded in (runs,
    # failure events, lessons, space objects). Enforces "AI explains, models
    # calculate" (ARCHITECTURE.md principle 2): an AI message should be traceable
    # to a source, not asserted on its own authority.
    grounding: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint(f"role IN {MESSAGE_ROLES}", name="role_valid"),
        Index("idx_messages_conversation", "conversation_id", "created_at"),
    )


class SearchHistory(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """user_id is NULLABLE - API.md marks /search auth as Optional, so anonymous
    searches are recorded with no owner and are readable by nobody.
    """

    __tablename__ = "search_history"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    result_count: Mapped[int | None] = mapped_column(Integer)
    filters: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    user: Mapped["User | None"] = relationship(back_populates="search_history")

    __table_args__ = (Index("idx_searchhist_user", "user_id", text("created_at DESC")),)
