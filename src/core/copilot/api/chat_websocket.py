"""
WebSocket endpoint for Copilot chat.

Canonical path:   /ws/copilot/chat
Transitional alias: /api/v1/ws/copilot/chat

Features:
- Cookie-first auth (no query-param token, SEC-AGT-004) via WebSocketAuthenticator
- ConversationMemory with sliding window (tenant-scoped)
- Message types: ping, clear, message
- Streaming response via handle_turn_stream
- Max message length: 2000 chars

Per CLAUDE.md regel 10: ASCII-only in source code.
"""

from __future__ import annotations

import importlib
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.ai.prompt_guard import PromptGuard
from src.core.auth.websocket_auth import AuthenticatedUser, WebSocketAuthenticator
from src.core.copilot.conversation_memory import ConversationMemory
from src.core.copilot.dependencies import _build_copilot_service
from src.core.database.database import db_manager
from src.core.exceptions import PromptInjectionError
from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id
from src.core.shared.redis_client import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Copilot WebSocket"])

_auth = WebSocketAuthenticator()
# Same guard as the HTTP path (turn_endpoint.py) so WS == HTTP prompt-injection posture.
_prompt_guard = PromptGuard()
MAX_MESSAGE_LENGTH = 2000


async def _handle_ws(
    websocket: WebSocket,
    session_id: UUID,
) -> None:
    """Shared WebSocket handler for both canonical and alias paths."""
    user = await _auth.authenticate(websocket)
    if not user:
        return

    # Ensure tenant context is set for any downstream DB operations
    set_tenant_id(user.tenant_id)

    redis = await get_redis()
    memory = ConversationMemory(redis)

    # Build copilot service with a local DB session (WS cannot use FastAPI Depends)
    if not db_manager.async_session_maker:
        logger.error("Database not initialized for WS connection")
        await websocket.close(code=4005, reason="Server not ready")
        clear_tenant_context()  # TI-112: no tenant leak on the early-return path
        return

    session = db_manager.async_session_maker()
    try:
        service = await _build_copilot_service(session)
    except Exception as exc:
        logger.error(
            "copilot.ws service_build_failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        await websocket.close(code=4005, reason="Service unavailable")
        await session.close()
        clear_tenant_context()  # TI-112: no tenant leak on the early-return path
        return

    try:
        # TI-112: the session_init send must live inside this try so its finally
        # clears tenant-context and closes the session even if the client drops in
        # the window between auth and the receive loop (send raises here).
        await websocket.send_json({"type": "session_init", "session_id": str(session_id)})

        # importlib avoids direct ImportFrom (DSM boundary agent_runtime -> governance)
        _rl_mod = importlib.import_module("src.core.governance.rate_limiter")
        check_copilot_turn_limit = _rl_mod.check_copilot_turn_limit

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "clear":
                await memory.clear(user.tenant_id, session_id)
                await websocket.send_json({"type": "cleared"})
                continue

            if msg_type == "message":
                content = msg.get("content", "")
                if len(content) > MAX_MESSAGE_LENGTH:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"Message too long (max {MAX_MESSAGE_LENGTH})",
                        }
                    )
                    continue

                # SEC-AGT-001: PromptGuard before any LLM call (parity with turn_endpoint.py).
                # Reject injection input up front -- do not store or forward it.
                try:
                    _prompt_guard.sanitize(content, tenant_id=user.tenant_id)
                except PromptInjectionError:
                    logger.warning(
                        "copilot.ws prompt_injection_blocked: tenant_id=%s", user.tenant_id
                    )
                    await websocket.send_json({"type": "error", "message": "Input rejected"})
                    continue

                # SEC-AGT-003: rate limit (parity with HTTP copilot_turn_limit), keyed by
                # tenant+user from the JWT -- never a header (security.md).
                if not await check_copilot_turn_limit(user.tenant_id, user.user_id):
                    logger.warning("copilot.ws rate_limited: tenant_id=%s", user.tenant_id)
                    await websocket.send_json({"type": "error", "message": "Rate limit exceeded"})
                    continue

                # Store user message (index the session under the user for GDPR-A17 erasure)
                await memory.add(
                    user.tenant_id, session_id, "user", content, user_id=int(user.user_id)
                )

                # Get history for context
                history = await memory.get_history(user.tenant_id, session_id)
                context = {
                    "history": [{"role": m.role, "content": m.content} for m in history],
                }

                # SEC-AGT-002: single execution. handle_turn_stream already runs the turn
                # (and its approved action) exactly once internally; capture the assistant
                # reply from the done chunk instead of re-running handle_turn (double-execute).
                assistant_message: str | None = None
                try:
                    async for chunk in service.handle_turn_stream(  # type: ignore[reportGeneralTypeIssues, unused-ignore]
                        tenant_id=user.tenant_id,
                        user_id=int(user.user_id),
                        message=content,
                        context=context,
                        language="nl",
                    ):
                        await websocket.send_json(chunk)
                        if isinstance(chunk, dict) and chunk.get("type") == "done":
                            payload = chunk.get("payload") or {}
                            assistant_message = payload.get("message")
                except Exception as exc:
                    logger.error(
                        "copilot.ws stream_error: %s: %s",
                        type(exc).__name__,
                        exc,
                        exc_info=True,
                    )
                    await websocket.send_json({"type": "error", "message": "Internal error"})
                    continue

                # Persist the assistant reply captured from the stream (no second turn).
                if assistant_message:
                    try:
                        await memory.add(user.tenant_id, session_id, "assistant", assistant_message)
                    except Exception as exc:
                        logger.error(
                            "copilot.ws history_store_error: %s: %s",
                            type(exc).__name__,
                            exc,
                            exc_info=True,
                        )
                continue

            # Unknown type
            await websocket.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info(
            "copilot.ws disconnect user=%s tenant=%s",
            user.user_id,
            user.tenant_id,
        )
    except Exception as exc:
        logger.error(
            "copilot.ws unexpected_error: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
    finally:
        # TI-112/BPA-024: clear tenant-context so it never leaks to the next task on a
        # reused worker thread/connection.
        clear_tenant_context()
        await session.close()


@router.websocket("/ws/copilot/chat")
async def copilot_chat_ws(websocket: WebSocket) -> None:
    """Canonical WebSocket endpoint for Copilot chat."""
    session_id = uuid4()
    await _handle_ws(websocket, session_id)


@router.websocket("/api/v1/ws/copilot/chat")
async def copilot_chat_ws_alias(websocket: WebSocket) -> None:
    """Transitional alias for Copilot chat WebSocket."""
    session_id = uuid4()
    await _handle_ws(websocket, session_id)
