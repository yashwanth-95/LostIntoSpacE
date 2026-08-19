"""Conversation and message schemas - the P2/P4 AI persistence boundary.

P4 owns generation (prompting, RAG, embeddings, provider calls). P2 owns
storage and authorization. Nothing here calls a model: P4 produces an
assistant reply and POSTs it to be stored.

`grounding` carries references to the deterministic data an answer is based on
(simulation runs, failure events, lessons, space objects). It exists to
enforce ARCHITECTURE.md principle #2 - "AI explains, models calculate" - so an
assistant message is traceable to a source rather than asserted on its own
authority. The backend stores it without interpreting it.

`context_ref` is a soft link, not an FK: a conversation can be about a
mission, a run, or a lesson, and should survive deletion of whatever it was
about. Readers must tolerate a dangling reference.

MESSAGES CARRY NO user_id (DATABASE_CONTRACT.md §2.6). Ownership is inherited
through the conversation; a denormalized owner column could contradict its
parent.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ConversationContextType = Literal["general", "tutor", "failure_analysis", "recommendation"]
ConversationStatus = Literal["active", "archived"]
MessageRole = Literal["user", "assistant", "system"]


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    context_type: ConversationContextType = "general"
    context_ref: dict[str, Any] | None = None


class ConversationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    status: ConversationStatus | None = None
    context_ref: dict[str, Any] | None = None

    def changed_fields(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str = Field(min_length=1, max_length=100_000)
    grounding: list[Any] = Field(default_factory=list)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    grounding: list[Any]
    created_at: datetime


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str | None
    context_type: str
    context_ref: dict[str, Any] | None
    status: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(ConversationResponse):
    """Conversation plus its full transcript, oldest first."""

    messages: list[MessageResponse] = Field(default_factory=list)
