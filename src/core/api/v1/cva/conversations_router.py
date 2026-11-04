"""CVA conversation history endpoints (ADR-033 Laag 1)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import Response

from src.core.auth.api_deps import UserResponse, get_current_user_dependency as get_current_user

if TYPE_CHECKING:
    from src.core.api.v1.cva.dependencies import CVAService  # own-domain -- ADR-033

from src.core.api.v1.cva.dependencies import (
    cva_chat_limit,
    get_cva_service_dependency,
    handle_cva_value_error,
)

logger = logging.getLogger(__name__)

conversations_router = APIRouter(prefix="/api/v1/cva", tags=["cva"])


@conversations_router.get("/conversations")
@cva_chat_limit
async def list_conversations(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    cva_service: CVAService = Depends(get_cva_service_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    List user's conversations with pagination.

    Phase 2 Implementation - Returns user's conversation history:
    - Paginated results (default 20 per page)
    - Ordered by most recent first (updated_at DESC)
    - Tenant isolation enforced
    """
    try:
        result = await cva_service.list_conversations(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            limit=limit,
            offset=offset,
        )

        return result

    except Exception as e:
        logger.exception("Error listing conversations: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversations",
        )


@conversations_router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: int,
    current_user: UserResponse = Depends(get_current_user),
    cva_service: CVAService = Depends(get_cva_service_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get single conversation with all messages.

    Phase 2 Implementation - Returns complete conversation:
    - All messages in chronological order
    - Full metadata (tokens used, model, timestamps)
    - Tenant isolation enforced
    """
    try:
        result = await cva_service.get_conversation(
            conversation_id=conversation_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )

        return result

    except ValueError as e:
        raise handle_cva_value_error(e, f"retrieving conversation {conversation_id}")

    except Exception as e:
        logger.exception("Error retrieving conversation %s: %s", conversation_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversation",
        )


@conversations_router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_conversation(
    conversation_id: int,
    current_user: UserResponse = Depends(get_current_user),
    cva_service: CVAService = Depends(get_cva_service_dependency),
) -> Response:
    """
    Soft delete conversation (set is_active=False).

    Phase 2 Implementation - Soft Delete:
    - Sets is_active=False (messages remain in database)
    - Idempotent (can be called multiple times safely)
    - Tenant isolation enforced
    """
    try:
        await cva_service.delete_conversation(
            conversation_id=conversation_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except ValueError as e:
        raise handle_cva_value_error(e, f"deleting conversation {conversation_id}")

    except Exception as e:
        logger.exception("Error deleting conversation %s: %s", conversation_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation",
        )


@conversations_router.delete(
    "/conversations/{conversation_id}/messages",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_conversation_messages(
    conversation_id: int,
    current_user: UserResponse = Depends(get_current_user),
    cva_service: CVAService = Depends(get_cva_service_dependency),
) -> Response:
    """
    Delete all messages from a conversation (GDPR Article 17 - Right to Erasure).

    Permanently removes all messages belonging to the conversation.
    The conversation record itself remains (soft state preserved).
    Tenant isolation enforced.
    """
    try:
        await cva_service.hard_delete_conversation(
            conversation_id=conversation_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except ValueError as e:
        raise handle_cva_value_error(e, f"deleting messages for conversation {conversation_id}")

    except Exception as e:
        logger.exception("Error deleting messages for conversation %s: %s", conversation_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation messages",
        )
