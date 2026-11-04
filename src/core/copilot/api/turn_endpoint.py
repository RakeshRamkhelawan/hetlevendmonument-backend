"""
POST /api/v1/copilot/turn endpoint.

HTTP entry point for Co-Pilot turns with optional SSE streaming.
Per CLAUDE.md:
  - regel 6.2: no ?token= query param on HTTP flows
  - regel 11: structured logging with exc_info
  - regel 12: response format {"success", "data"} / {"success", "error"}
  - M-3 fix: rate-limit bucket keyed by request.state.tenant_id

Per ADR-027 paragraaf 11.1: HTTP contract for copilot turn.
"""

import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.core.ai.prompt_guard import PromptGuard as _SyncPromptGuard
from src.core.api.auth.dependencies import validate_csrf_token
from src.core.auth.dependencies import UserResponse, get_current_user
from src.core.copilot.dependencies import get_copilot_service
from src.core.exceptions import PromptInjectionError
from src.core.copilot.service import DeliberationInProgressError
from src.core.copilot.schemas import (
    CopilotTurnRequest,
    CopilotTurnResponse,
    ProactiveResponseRequest,
    ProactiveResponseResponse,
)
from src.core.config.feature_flags import check_copilot_rollout
from src.core.copilot.service import CopilotService
from src.core.governance.rate_limiter import copilot_turn_limit  # SP-SEC-RL-001: Redis-backed
from src.core.middleware.tenant_context import require_tenant_id

logger = logging.getLogger(__name__)

_prompt_guard = _SyncPromptGuard()

router = APIRouter()


@router.post("/turn", response_model=None)
@copilot_turn_limit(max_requests=30, window_seconds=60)
async def copilot_turn(
    request: Request,
    payload: CopilotTurnRequest,
    current_user: UserResponse = Depends(get_current_user),
    service: CopilotService = Depends(get_copilot_service),
    _rollout: None = Depends(check_copilot_rollout),
    _csrf: None = Depends(validate_csrf_token),
) -> CopilotTurnResponse | StreamingResponse:
    tenant_id = require_tenant_id()
    request.state.tenant_id = tenant_id
    request.state.user_id = current_user.id

    try:
        _prompt_guard.sanitize(payload.message, tenant_id=tenant_id)
    except PromptInjectionError:
        logger.warning("prompt_injection_blocked: tenant_id=%s", tenant_id)
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": {"code": "INPUT_REJECTED", "message": "Input rejected", "details": {}},
            },
        )

    logger.info(
        "copilot.turn started",
        extra={
            "tenant_id": tenant_id,
            "user_id": current_user.id,
            "stream": payload.stream,
            "language": payload.language,
        },
    )

    if payload.stream:

        async def event_stream() -> AsyncIterator[bytes]:
            try:
                async for chunk in service.handle_turn_stream(  # type: ignore[reportGeneralTypeIssues, unused-ignore]
                    tenant_id=tenant_id,
                    user_id=current_user.id,
                    message=payload.message,
                    context=payload.context,
                    language=payload.language,
                ):
                    yield f"data: {json.dumps(chunk)}\n\n".encode()
                yield b"data: [DONE]\n\n"
            except Exception as exc:
                logger.error(
                    "copilot.turn stream_error: %s: %s",
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                    extra={"tenant_id": tenant_id, "user_id": current_user.id},
                )
                err = {"type": "error", "message": "Internal error"}
                yield f"data: {json.dumps(err)}\n\n".encode()

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        return await service.handle_turn(
            tenant_id=tenant_id,
            user_id=current_user.id,
            message=payload.message,
            context=payload.context,
            language=payload.language,
        )
    except DeliberationInProgressError:
        raise HTTPException(
            status_code=429,
            detail={
                "success": False,
                "error": {
                    "code": "DELIBERATION_IN_PROGRESS",
                    "message": "Duplicate request detected. Retry after 5 seconds.",
                },
            },
            headers={"Retry-After": "5"},
        )


@router.post(
    "/proactive/{signal_id}/respond",
    response_model=ProactiveResponseResponse,
    summary="User reageert op een proactief signaal",
    description=(
        "Accepteert een user-actie (confirm/cancel/snooze/dismiss/navigate) "
        "op een eerder geleverd Co-Pilot signaal. Audit-logt via "
        "hash chain (ADR-019)."
    ),
)
async def respond_to_proactive_signal(
    signal_id: UUID,
    request: ProactiveResponseRequest,
    current_user: UserResponse = Depends(get_current_user),
    copilot: CopilotService = Depends(get_copilot_service),
    _rollout: None = Depends(check_copilot_rollout),
    _csrf: None = Depends(validate_csrf_token),
) -> ProactiveResponseResponse:
    tenant_id = require_tenant_id()
    # no-prompt-guard: params is enum-bounded action type, never raw LLM input
    try:
        return await copilot.handle_proactive_response(
            signal_id=signal_id,
            tenant_id=tenant_id,
            user_id=current_user.id,
            action_type=request.action_type,
            params=request.params,
        )
    except ValueError as exc:
        logger.warning(
            "proactive_response_rejected: %s",
            exc,
            extra={
                "tenant_id": tenant_id,
                "user_id": current_user.id,
                "signal_id": str(signal_id),
                "action_type": request.action_type,
            },
        )
        raise HTTPException(status_code=422, detail="Ongeldige invoer.") from exc
