"""Conversation + message routes. All Bearer-protected and owner-scoped.

Mounted at `/conversations` (Phase 12's paths). docs/api/API.md also lists
`GET /ai/conversations`; that alias is added in api_router so both work and
P4/P1 can use either without a contract break.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.service import (
    add_message,
    create_conversation,
    delete_conversation,
    get_conversation_detail,
    list_conversations,
    list_messages,
    update_conversation,
)
from src.auth.dependencies import get_current_user
from src.core.database import get_db
from src.core.envelope import success_envelope
from src.models.user import User
from src.schemas.common import (
    AUTH_ERROR_RESPONSES,
    OWNED_RESOURCE_RESPONSES,
    PaginatedResponse,
    PaginationParams,
    SuccessResponse,
    pagination_meta,
    pagination_params,
)
from src.schemas.conversation import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    ConversationStatus,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
)

router = APIRouter()


@router.post(
    "",
    status_code=201,
    response_model=SuccessResponse[ConversationResponse],
    responses=AUTH_ERROR_RESPONSES,
)
async def create(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await create_conversation(
        session, user_id=current_user.id, payload=body.model_dump()
    )
    return success_envelope(
        ConversationResponse.model_validate(conversation).model_dump(mode="json")
    )


@router.get(
    "", response_model=PaginatedResponse[ConversationResponse], responses=AUTH_ERROR_RESPONSES
)
async def list_(
    status: ConversationStatus | None = Query(default=None),
    pagination: PaginationParams = Depends(pagination_params),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    conversations, total = await list_conversations(
        session, user_id=current_user.id, pagination=pagination, status=status
    )
    return success_envelope(
        [ConversationResponse.model_validate(c).model_dump(mode="json") for c in conversations],
        meta=pagination_meta(pagination, total),
    )


@router.get(
    "/{conversation_id}",
    response_model=SuccessResponse[ConversationDetailResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def read(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await get_conversation_detail(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    return success_envelope(
        ConversationDetailResponse.model_validate(conversation).model_dump(mode="json")
    )


@router.patch(
    "/{conversation_id}",
    response_model=SuccessResponse[ConversationResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def update(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await update_conversation(
        session,
        conversation_id=conversation_id,
        user_id=current_user.id,
        changes=body.changed_fields(),
    )
    return success_envelope(
        ConversationResponse.model_validate(conversation).model_dump(mode="json")
    )


@router.delete("/{conversation_id}", status_code=204, responses=OWNED_RESOURCE_RESPONSES)
async def delete(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await delete_conversation(session, conversation_id=conversation_id, user_id=current_user.id)


@router.get(
    "/{conversation_id}/messages",
    response_model=PaginatedResponse[MessageResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def read_messages(
    conversation_id: uuid.UUID,
    pagination: PaginationParams = Depends(pagination_params),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    messages, total = await list_messages(
        session,
        conversation_id=conversation_id,
        user_id=current_user.id,
        pagination=pagination,
    )
    return success_envelope(
        [MessageResponse.model_validate(m).model_dump(mode="json") for m in messages],
        meta=pagination_meta(pagination, total),
    )


@router.post(
    "/{conversation_id}/messages",
    status_code=201,
    response_model=SuccessResponse[MessageResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def create_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """P4's persistence entry point: AI response -> here -> storage."""
    message = await add_message(
        session,
        conversation_id=conversation_id,
        user_id=current_user.id,
        role=body.role,
        content=body.content,
        grounding=body.grounding,
    )
    return success_envelope(MessageResponse.model_validate(message).model_dump(mode="json"))
