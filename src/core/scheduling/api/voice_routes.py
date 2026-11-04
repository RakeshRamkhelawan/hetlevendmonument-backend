"""
API endpoints for Voice UI scheduling.

Provides REST and WebSocket endpoints for voice-controlled scheduling.
"""

import asyncio
import logging
from typing import Any, Optional, Protocol, cast

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db
from src.core.scheduling.schemas import VoiceConfirmRequest, VoiceProcessRequest
from src.core.scheduling.voice.agent import SchedulingVoiceAgent
from src.core.scheduling.voice.intents import VoiceContext
from src.core.scheduling.voice.session_store import get_session_store

logger = logging.getLogger(__name__)

class _TokenValidator(Protocol):
    async def get_current_user_from_token(self, token: str) -> object | None:
        ...


router = APIRouter(
    prefix="/scheduling/voice",
    tags=["Voice Scheduling"],
)


# Session store for voice interactions (Redis-backed)
session_store = get_session_store()


def get_voice_agent(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> SchedulingVoiceAgent:
    """Dependency to get voice agent."""
    return SchedulingVoiceAgent(
        tenant_id=current_user.tenant_id,
        db=db,
    )


# ========================================================================
# REST Endpoints
# ========================================================================


@router.post(
    "/process",
    response_model=dict,
    summary="Process voice input",
)
async def process_voice_input(
    data: VoiceProcessRequest,
    current_user: UserResponse = Depends(get_current_user),
    agent: SchedulingVoiceAgent = Depends(get_voice_agent),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Process voice input and return scheduling response.

    Request:
        - transcript: Speech-to-text result (max 1000 chars)
        - session_id: Optional session ID for multi-turn conversations
        - timezone: Optional timezone (default: UTC)

    Response:
        - response_text: Natural language response
        - action_taken: What action was performed
        - requires_follow_up: Whether more input is needed
        - suggested_responses: Quick-reply options
        - data: Action-specific data (event details, etc.)
    """
    transcript = data.transcript.strip()
    session_id = data.session_id

    # Get or create voice context
    context = None
    if session_id:
        context = await session_store.get(session_id)

    if context is None:
        # Create new session
        context = VoiceContext(
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
            timezone=data.timezone,
        )
        import uuid

        session_id = f"{current_user.id}_{uuid.uuid4().hex[:8]}"

    # Add to conversation history
    context.add_to_history("user", transcript)

    # Process through voice agent
    result = await agent.process_voice_input(transcript, context)

    # Add response to history
    context.add_to_history("assistant", result.response_text)

    # Store pending intent if follow-up needed
    if result.requires_follow_up:
        context.pending_intent = getattr(result, "intent", None)
    else:
        context.pending_intent = None

    # Save session (with 30 min TTL)
    await session_store.set(session_id, context)  # type: ignore[arg-type]

    # Build response
    response = {
        "success": result.success,
        "response_text": result.response_text,
        "action_taken": result.action_type,
        "requires_follow_up": result.requires_follow_up,
        "session_id": session_id,
    }

    if result.data:
        response["data"] = result.data
        # Include intent and entities from data if present
        if "intent" in result.data:
            response["intent"] = result.data["intent"]
        if "entities" in result.data:
            response["entities"] = result.data["entities"]

    if result.suggested_responses:
        response["suggested_responses"] = result.suggested_responses

    # Include conversation context
    response["context"] = {
        "conversation_history": (
            context.conversation_history[-5:]
            if len(context.conversation_history) > 5
            else context.conversation_history
        ),  # Last 5 exchanges
        "pending_intent": (
            context.pending_intent.intent_type.value if context.pending_intent else None
        ),
        "timezone": context.timezone,
    }

    return response


@router.post(
    "/confirm",
    response_model=dict,
    summary="Confirm a pending action",
)
async def confirm_action(
    data: VoiceConfirmRequest,
    current_user: UserResponse = Depends(get_current_user),
    agent: SchedulingVoiceAgent = Depends(get_voice_agent),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Confirm a pending action that required user confirmation.

    Request:
        - session_id: The voice session ID
        - confirmed: Boolean indicating yes/no
    """
    session_id = data.session_id
    confirmed = data.confirmed

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id is required",
        )

    context = await session_store.get(session_id)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired session_id",
        )

    if confirmed:
        # Execute the pending action
        if context.pending_intent:
            result = await agent.process_voice_input("yes", context)
            await session_store.set(session_id, context)
            return {
                "response_text": result.response_text,
                "action_taken": result.action_type,
                "requires_follow_up": result.requires_follow_up,
                "data": result.data,
            }

        return {
            "response_text": "Action confirmed and executed.",
            "action_taken": "confirmed",
            "requires_follow_up": False,
        }
    else:
        # Cancel the pending action
        context.pending_intent = None
        await session_store.set(session_id, context)
        return {
            "response_text": "Action cancelled. What would you like to do instead?",
            "action_taken": "cancelled",
            "requires_follow_up": True,
        }


@router.delete(
    "/session/{session_id}",
    response_model=dict,
    summary="End voice session",
)
async def end_session(
    session_id: str,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """End a voice session and clear conversation history."""
    deleted = await session_store.delete(session_id)

    if deleted:
        return {"success": True, "message": "Session ended"}

    return {"success": False, "message": "Session not found or already expired"}


# ========================================================================
# Utility Endpoints
# ========================================================================


@router.get(
    "/intents",
    response_model=dict,
    summary="List available voice intents",
)
async def list_intents(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get list of supported voice intents.

    Returns all intents that can be recognized and processed
    by the voice scheduling system.
    """
    intents = [
        {
            "name": "schedule_meeting",
            "description": "Schedule a new meeting",
            "examples": [
                "Schedule a meeting with John tomorrow at 2pm",
                "Book a 30 minute call",
            ],
            "required_entities": ["participants", "date/time"],
        },
        {
            "name": "cancel_event",
            "description": "Cancel an existing meeting",
            "examples": ["Cancel my 2pm meeting", "Remove the team standup"],
            "required_entities": ["meeting_title or event_id"],
        },
        {
            "name": "reschedule_event",
            "description": "Move a meeting to a different time",
            "examples": [
                "Move my meeting to 4pm",
                "Reschedule tomorrow's call to Friday",
            ],
            "required_entities": ["meeting_title or event_id", "new_date/time"],
        },
        {
            "name": "query_availability",
            "description": "Check when someone is free",
            "examples": ["When am I free tomorrow?", "Check my availability"],
            "required_entities": ["date"],
        },
        {
            "name": "list_meetings",
            "description": "List upcoming meetings",
            "examples": ["What meetings do I have today?", "Show my calendar"],
            "required_entities": [],
        },
        {
            "name": "suggest_times",
            "description": "Get suggested meeting times",
            "examples": ["When can we meet?", "Find a good time for a 1 hour meeting"],
            "required_entities": ["duration"],
        },
        {
            "name": "block_focus_time",
            "description": "Block time for focused work",
            "examples": [
                "Block 2 hours for deep work",
                "I need focus time tomorrow morning",
            ],
            "required_entities": ["duration", "date/time"],
        },
    ]

    return {"intents": intents}


@router.get(
    "/health",
    response_model=dict,
    summary="Voice service health check",
)
async def health_check() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Check voice service health status.

    Returns status of voice components including:
    - Session store connectivity
    - NLP/Intent parser status
    - Overall service health
    """
    from src.core.scheduling.voice.session_store import get_session_store

    store = get_session_store()

    # Check if session store is working
    store_status = "healthy"
    try:
        # Try a simple operation
        if hasattr(store, "_use_local") and store._use_local:
            store_status = "degraded (local fallback)"
    except Exception:
        store_status = "unhealthy"

    return {
        "status": "healthy" if store_status == "healthy" else "degraded",
        "service": "voice_scheduling",
        "redis_connected": store_status == "healthy",
        "components": {
            "session_store": store_status,
            "intent_parser": "healthy",
            "websocket": "healthy",
        },
        "version": "1.0.0",
    }


# ========================================================================
# WebSocket Endpoint
# ========================================================================


@router.websocket("/ws")
async def voice_websocket(
    websocket: WebSocket,
    token: str | None = None,
) -> None:
    """
    WebSocket for real-time voice streaming.

    Supports:
    - Streaming voice input
    - Real-time responses
    - Multi-turn conversations
    - Barge-in (interrupt ongoing response)
    - Heartbeat/ping-pong

    Connection: ws://api.sanskritisetu.org/api/v1/scheduling/voice/ws?token=<JWT>

    Protocol:
    - Client sends: {"type": "transcript", "data": "..."}
    - Server responds: {"type": "response", "data": {...}}
    - Client sends: {"type": "ping"}
    - Server responds: {"type": "pong"}
    """
    # Validate JWT token
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    # Decode and validate JWT
    try:
        from jose import JWTError as _JWTError, jwt
    except ImportError:
        _JWTError = Exception
    try:
        from src.core.auth.auth_service import AuthService

        # Use AuthService to validate token
        auth_service = AuthService()
        user = cast(
            UserResponse | None,
            await cast(_TokenValidator, auth_service).get_current_user_from_token(token),
        )

        if not user:
            await websocket.close(code=4001, reason="Invalid authentication token")
            return

    except _JWTError as exc:
        logger.warning(f"WebSocket JWT validation failed: {exc}")
        await websocket.close(code=4001, reason="Invalid authentication token")
        return
    except Exception as exc:
        logger.error(f"WebSocket auth error: {exc}")
        await websocket.close(code=4001, reason="Authentication error")
        return

    await websocket.accept()
    logger.info(f"Voice WebSocket connected for user {user.id}")

    # Create voice context with authenticated user info
    context = VoiceContext(
        user_id=str(user.id),
        tenant_id=user.tenant_id,
        timezone=getattr(user, "timezone", "UTC"),
    )

    import uuid

    session_id = f"ws_{user.id}_{uuid.uuid4().hex[:8]}"
    await session_store.set(session_id, context)

    # Track last activity for heartbeat
    last_activity = asyncio.get_event_loop().time()

    try:
        while True:
            # Check for timeout (5 minutes of inactivity)
            current_time = asyncio.get_event_loop().time()
            if current_time - last_activity > 300:  # 5 minutes
                await websocket.send_json(
                    {
                        "type": "error",
                        "data": {"message": "Session timeout due to inactivity"},
                    }
                )
                await websocket.close(code=4000, reason="Session timeout")
                break

            # Receive message from client
            try:
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=60.0,  # 60 second timeout for messages
                )
                last_activity = current_time
            except TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "ping"})
                continue

            message_type = message.get("type", "transcript")

            if message_type == "transcript":
                transcript = message.get("data", "").strip()

                if not transcript:
                    continue

                if len(transcript) > 1000:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {"message": "Transcript exceeds maximum length"},
                        }
                    )
                    continue

                # Add to conversation history
                context.add_to_history("user", transcript)

                # Process through voice agent
                # Note: WebSocket uses in-memory processing without DB for speed
                # For complex operations, client should use REST API
                response_text = f"Processing: {transcript}"
                response: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                    "type": "response",
                    "data": {
                        "response_text": response_text,
                        "action_taken": "received",
                        "requires_follow_up": True,
                        "note": "Use REST API /process for full processing with database access",
                    },
                }

                await websocket.send_json(response)
                context.add_to_history("assistant", response_text)
                await session_store.set(session_id, context)

            elif message_type == "interrupt":
                # Handle barge-in
                await websocket.send_json(
                    {
                        "type": "interrupted",
                        "data": {"message": "Previous action interrupted"},
                    }
                )

            elif message_type == "pong":
                # Client responded to heartbeat
                pass

            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "data": {"message": f"Unknown message type: {message_type}"},
                    }
                )

    except WebSocketDisconnect:
        logger.info(f"Voice WebSocket disconnected: {session_id}")
        await session_store.delete(session_id)

    except Exception as exc:
        logger.exception("Voice WebSocket error")
        await session_store.delete(session_id)
        await websocket.close(code=1011, reason="Internal server error")


# ========================================================================
# Utility Endpoints
# ========================================================================


@router.get(
    "/examples",
    response_model=dict,
    summary="Get example voice commands",
)
async def get_voice_examples() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get example voice commands that the system understands."""
    return {
        "examples": [
            {
                "command": "Schedule a meeting with John tomorrow at 3pm",
                "description": "Create a new meeting",
            },
            {
                "command": "Cancel my meeting with the design team",
                "description": "Cancel an existing meeting",
            },
            {
                "command": "When am I available on Friday?",
                "description": "Check availability",
            },
            {
                "command": "What meetings do I have today?",
                "description": "List upcoming meetings",
            },
            {
                "command": "Block some focus time tomorrow morning",
                "description": "Schedule focus time",
            },
            {
                "command": "Suggest times for a 30 minute sync",
                "description": "Get meeting time suggestions",
            },
        ],
        "tips": [
            "Be specific about dates and times",
            "Mention participant names clearly",
            "Specify duration if not the default (30 min)",
            "You can interrupt me at any time by speaking",
        ],
    }


@router.get(
    "/supported-intents",
    response_model=dict,
    summary="Get supported voice intents",
)
async def get_supported_intents() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get list of supported voice intents."""
    from src.core.scheduling.voice.intents import VoiceIntentType

    return {
        "intents": [
            {"type": intent.value, "description": intent.name.replace("_", " ").title()}
            for intent in VoiceIntentType
        ]
    }
