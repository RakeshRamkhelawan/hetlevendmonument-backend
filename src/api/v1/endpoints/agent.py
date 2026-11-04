"""
Agent API Router - FastAPI endpoints for the agentic chat system.

Endpoints:
- POST /chat - Process a chat message
- GET /chat/stream - SSE streaming chat
- GET /sessions/{id} - Get session info
- GET /sessions/{id}/history - Get session history
- DELETE /sessions/{id} - End a session
- POST /feedback - Submit feedback
- GET /features - List available features
"""

import logging
from datetime import datetime
from typing import Any, Optional
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db
from src.core.models.rbac_models import User
from src.core.noodstop.guard import KlantStilgezet
from src.domains.agentic.services import (
    ChatRequest,
    create_chat_service,
    get_feature_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class ChatMessageRequest(BaseModel):
    """Request to send a chat message."""

    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = Field(None, description="Session ID for continuity")
    feature_context: str | None = Field(None, description="Explicit feature context")
    locale: str | None = Field(None, description="User locale (e.g., en_US)")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")  # TODO(TYPE): replace Any with concrete type


class ToolCall(BaseModel):
    """Tool call information."""

    tool_name: str | None = None
    parameters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    result: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    success: bool = True
    error: str | None = None


class ChatMessageResponse(BaseModel):
    """Response from chat endpoint."""

    response: str
    session_id: str
    feature_context: str
    tool_calls: list[ToolCall] = []
    suggestions: list[str] = []
    metadata: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


class SessionInfo(BaseModel):
    """Session information."""

    session_id: str
    user_id: int
    tenant_id: int  # noqa: tenant-id-body -- response model, niet request body
    current_feature: str | None
    message_count: int
    created_at: datetime
    last_activity: datetime


class MessageInfo(BaseModel):
    """Message information."""

    role: str
    content: str
    feature_context: str | None
    timestamp: datetime


class SessionHistoryResponse(BaseModel):
    """Session history response."""

    session_id: str
    messages: list[MessageInfo]


class FeedbackRequest(BaseModel):
    """Feedback submission."""

    session_id: str
    message_index: int | None = None
    rating: int = Field(..., ge=1, le=5)
    feedback_type: str = Field(..., pattern="^(helpful|unhelpful|incorrect|inappropriate)$")
    comment: str | None = Field(None, max_length=1000)


class FeatureInfo(BaseModel):
    """Feature information for listing."""

    id: str
    category: str
    display_name: str
    description: str
    is_available: bool = True


class FeatureListResponse(BaseModel):
    """List of available features."""

    features: list[FeatureInfo]
    total: int


# ============================================================================
# Dependencies
# ============================================================================

_chat_service: Any = None


def get_chat_service() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Get or create chat service singleton."""
    global _chat_service
    if _chat_service is None:
        import os

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _chat_service = create_chat_service(redis_url=redis_url)
    return _chat_service


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/chat", response_model=ChatMessageResponse)
async def process_chat(
    request: ChatMessageRequest,
    x_feature_context: str | None = Header(None, description="Explicit feature"),
    x_route_path: str | None = Header(None, description="Client route path"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatMessageResponse:
    """
    Process a chat message and return agent response.

    The agent will:
    1. Detect the appropriate feature context
    2. Compose a domain-specific prompt
    3. Generate a response
    4. Execute tools if needed
    5. Return with suggestions for follow-up
    """
    try:
        chat_service = get_chat_service()

        chat_request = ChatRequest(
            message=request.message,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            session_id=request.session_id,
            feature_context=x_feature_context or request.feature_context,
            locale=request.locale,
            route_path=x_route_path,
            metadata=request.metadata,
        )

        response = await chat_service.process_chat(db, chat_request)

        return ChatMessageResponse(
            response=response.response,
            session_id=response.session_id,
            feature_context=response.feature_context,
            tool_calls=[
                ToolCall(
                    tool_name=tc.tool_name,
                    parameters=tc.parameters,
                    result=tc.result,
                    success=tc.success,
                    error=tc.error,
                )
                for tc in response.tool_calls
            ],
            suggestions=response.suggestions,
            metadata=response.metadata,
        )

    except KlantStilgezet as stop:
        # Noodstop (besluit A ronde 2): 403 als de klant stilstaat, 503 als dat niet vast te stellen is.
        raise HTTPException(
            status_code=503 if stop.onbekend else 403, detail=stop.bericht
        ) from stop
    except Exception as e:
        logger.error(f"Chat processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/chat/stream")
async def stream_chat(
    message: str = Query(..., min_length=1),
    session_id: str | None = Query(None),
    feature_context: str | None = Query(None),
    locale: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Stream chat response via Server-Sent Events (SSE).

    Returns chunks of response as they're generated for real-time display.

    Event types:
    - metadata: Initial session/feature info
    - chunk: Text chunk of response
    - tool_call: Tool execution info
    - done: Completion signal
    """
    chat_service = get_chat_service()

    chat_request = ChatRequest(
        message=message,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        session_id=session_id,
        feature_context=feature_context,
        locale=locale,
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        import json

        try:
            async for chunk in chat_service.process_chat_stream(db, chat_request):
                event_type = chunk.get("type", "chunk")
                data = json.dumps(chunk)
                yield f"event: {event_type}\ndata: {data}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            error_data = json.dumps({"type": "error", "error": "Er is een fout opgetreden."})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: str, current_user: User = Depends(get_current_user)
) -> SessionInfo:
    """Get information about a session."""
    chat_service = get_chat_service()
    session = await chat_service.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify ownership
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return SessionInfo(
        session_id=session.id,
        user_id=session.user_id,
        tenant_id=session.tenant_id,
        current_feature=session.current_feature,
        message_count=len(session.messages),
        created_at=session.created_at,
        last_activity=session.last_activity,
    )


@router.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str,
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
) -> SessionHistoryResponse:
    """Get message history for a session."""
    chat_service = get_chat_service()
    session = await chat_service.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    messages = session.messages[-limit:]

    return SessionHistoryResponse(
        session_id=session_id,
        messages=[
            MessageInfo(
                role=m.role,
                content=m.content,
                feature_context=m.feature_context,
                timestamp=m.timestamp,
            )
            for m in messages
        ],
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """End and delete a session."""
    chat_service = get_chat_service()
    session = await chat_service.session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    await chat_service.session_manager.delete_session(session_id)

    return {"status": "deleted", "session_id": session_id}


@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Submit feedback for a chat interaction.

    Used for prompt optimization and quality improvement.
    """
    chat_service = get_chat_service()
    session = await chat_service.session_manager.get_session(request.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # TODO: Store feedback for prompt optimization
    # This could update PromptMetrics or a dedicated feedback table

    logger.info(
        f"Feedback received: session={request.session_id}, "
        f"rating={request.rating}, type={request.feedback_type}"
    )

    return {
        "status": "received",
        "session_id": request.session_id,
        "feedback_type": request.feedback_type,
    }


@router.get("/features", response_model=FeatureListResponse)
async def list_features(
    category: str | None = Query(None),
    locale: str = Query("en"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeatureListResponse:
    """
    List available features for the current tenant.

    Features can be filtered by category.
    """
    registry = get_feature_registry()

    # Load features for tenant
    features = await registry.load_features(db, current_user.tenant_id)

    result: list[FeatureInfo] = []
    for fid, feature in features.items():
        # Filter by category if specified
        if category and feature.category != category:
            continue

        result.append(
            FeatureInfo(
                id=feature.id,
                category=feature.category,
                display_name=feature.get_display_name(locale),
                description=feature.get_description(locale),
                is_available=feature.is_active,
            )
        )

    return FeatureListResponse(features=result, total=len(result))


@router.get("/features/{feature_id}")
async def get_feature(
    feature_id: str,
    locale: str = Query("en"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get details about a specific feature."""
    registry = get_feature_registry()

    # Ensure features are loaded
    await registry.load_features(db, current_user.tenant_id)

    feature = registry.get_feature(current_user.tenant_id, feature_id)

    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    return {
        "id": feature.id,
        "category": feature.category,
        "display_name": feature.get_display_name(locale),
        "description": feature.get_description(locale),
        "domain_context": feature.domain_context,
        "available_tools": feature.available_tools,
        "is_active": feature.is_active,
    }
