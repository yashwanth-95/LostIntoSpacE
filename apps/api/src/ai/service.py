"""Conversation and message persistence.

P2 owns storage and authorization only. Nothing here calls a model, builds a
prompt, embeds text, or retrieves context - P4 owns all of that and posts the
finished assistant message here to be stored.

Ownership is direct (`conversations.user_id`); messages inherit it through
their conversation, so a message can only be read or written by someone who
already passed the conversation ownership check.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.authz import count_query, get_owned_conversation
from src.models.conversation import Conversation, Message
from src.schemas.common import PaginationParams


async def create_conversation(
    session: AsyncSession, *, user_id: uuid.UUID, payload: dict[str, Any]
) -> Conversation:
    conversation = Conversation(user_id=user_id, **payload)
    session.add(conversation)
    await session.flush()
    await session.refresh(conversation)
    return conversation


async def list_conversations(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    pagination: PaginationParams,
    status: str | None = None,
) -> tuple[list[Conversation], int]:
    statement = select(Conversation).where(Conversation.user_id == user_id)
    if status is not None:
        statement = statement.where(Conversation.status == status)

    total = await count_query(session, statement)
    result = await session.execute(
        statement.order_by(Conversation.updated_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return list(result.scalars().all()), total


async def get_conversation_detail(
    session: AsyncSession, *, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> Conversation:
    """Conversation with its full transcript, oldest message first."""
    await get_owned_conversation(session, conversation_id=conversation_id, user_id=user_id)
    result = await session.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one()
    # Chronological order is the transcript's meaning, not a display
    # preference - sorted here so every caller gets it right.
    conversation.messages.sort(key=lambda m: m.created_at)
    return conversation


async def update_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    changes: dict[str, Any],
) -> Conversation:
    conversation = await get_owned_conversation(
        session, conversation_id=conversation_id, user_id=user_id
    )
    for field, value in changes.items():
        setattr(conversation, field, value)
    await session.flush()
    await session.refresh(conversation)
    return conversation


async def delete_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Messages cascade with the conversation (ON DELETE CASCADE)."""
    conversation = await get_owned_conversation(
        session, conversation_id=conversation_id, user_id=user_id
    )
    await session.delete(conversation)
    await session.flush()


async def add_message(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    content: str,
    grounding: list[Any],
) -> Message:
    conversation = await get_owned_conversation(
        session, conversation_id=conversation_id, user_id=user_id
    )
    message = Message(
        conversation_id=conversation.id, role=role, content=content, grounding=grounding
    )
    session.add(message)
    # Touch the parent so conversation lists sort by real activity - otherwise
    # `updated_at` would only move when the title changed.
    conversation.updated_at = func.now()
    await session.flush()
    await session.refresh(message)
    return message


async def list_messages(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    pagination: PaginationParams,
) -> tuple[list[Message], int]:
    await get_owned_conversation(session, conversation_id=conversation_id, user_id=user_id)
    statement = select(Message).where(Message.conversation_id == conversation_id)
    total = await count_query(session, statement)
    result = await session.execute(
        statement.order_by(Message.created_at).offset(pagination.offset).limit(pagination.limit)
    )
    return list(result.scalars().all()), total
