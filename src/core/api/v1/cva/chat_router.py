# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""CVA chat endpoints -- POST /chat and POST /chat/stream (ADR-033 Laag 1)."""

import json
import logging
import os
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from src.core.api.v1.cva.dependencies import CVAService  # own-domain -- ADR-033
    from src.core.api.v1.cva.dependencies import LLMService  # own-domain -- ADR-033
import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency as get_current_user,
    has_scopes,
    OAuth2Scope,
)
from src.core.ai.prompt_guard import PromptGuard as _SyncPromptGuard
from src.core.exceptions import GovernanceVetoError, PromptInjectionError
from src.core.schemas.cva_schemas import ChatRequest, ChatResponse, ExplainResponse
from src.core.api.v1.cva.dependencies import (
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
    build_cva_service,
    cva_chat_limit,
    get_cva_service_dependency,
    get_db,
    get_llm_service_dependency,
    get_system_prompt,
    handle_cva_value_error,
)

logger = logging.getLogger(__name__)

_prompt_guard = _SyncPromptGuard()

chat_router = APIRouter(prefix="/api/v1/cva", tags=["cva"])


@chat_router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
@cva_chat_limit
async def chat_endpoint(  # type: ignore[no-untyped-def]
    request: ChatRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    llm_service=Depends(get_llm_service_dependency),
) -> ChatResponse:
    """
    Process chat message with CVA Agent.

    Phase 2 Implementation - Uses CVA Service with:
    - Conversation persistence
    - Multi-tenant isolation
    - LLM abstraction layer
    - Error handling
    """
    try:
        _prompt_guard.sanitize(request.message, tenant_id=current_user.tenant_id)
    except PromptInjectionError:
        logger.warning("prompt_injection_blocked: tenant_id=%s", current_user.tenant_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": {"code": "INPUT_REJECTED", "message": "Input rejected", "details": {}},
            },
        )

    try:
        cva_service = build_cva_service(db, llm_service)

        logger.info(
            "CVA chat: LLM_PROVIDER=%s, LLM_MODEL=%s, provider=%s",
            os.getenv("LLM_PROVIDER"),
            os.getenv("LLM_MODEL"),
            llm_service.provider.__class__.__name__,
        )

        if request.system_prompt:
            if not has_scopes(current_user, [OAuth2Scope.ADMIN_ALL]):
                logger.warning(
                    "User %s attempted system prompt override without admin scope",
                    current_user.id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin privileges required for system prompt override",
                )
            system_prompt: str | None = request.system_prompt
        else:
            effective_model: str = cast(str, request.model or os.getenv("LLM_MODEL", ""))
            system_prompt = get_system_prompt(
                platform_name="SanskritiSetu",
                tenant_id=str(current_user.tenant_id),
                user_language="en",
                model_id=effective_model,
            )

        result = await cva_service.chat(
            message=request.message,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            conversation_id=request.conversation_id,
            system_prompt=system_prompt,
            model=request.model,
        )

        return ChatResponse(**result)

    except ValueError as e:
        raise handle_cva_value_error(e, "processing chat")

    except TimeoutError as e:
        logger.error("LLM service timeout: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service timeout",
        )

    except LLMTimeoutError as e:
        logger.error(
            "LLM timeout for user %s: %s: %s", current_user.id, type(e).__name__, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service timed out. Please retry your request.",
        )

    except LLMRateLimitError as e:
        logger.warning("LLM rate limit for user %s: %s", current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="LLM rate limit exceeded. Please wait and try again.",
        )

    except LLMServiceError as e:
        logger.error(
            "LLM service error for user %s: %s: %s",
            current_user.id,
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service error. Please try again.",
        )

    except GovernanceVetoError:
        raise  # sanskriti_error_handler vertaalt naar HTTP 403

    except HTTPException:
        raise

    except Exception as e:
        if "RateLimitError" in type(e).__name__:
            logger.error("LLM rate limit exceeded: %s: %s", type(e).__name__, e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="LLM rate limit exceeded. Please try again later.",
            )
        logger.exception("Unexpected error in chat endpoint: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during chat processing",
        )


@chat_router.post("/chat/stream", response_class=StreamingResponse)
@cva_chat_limit
async def chat_with_cva_streaming(  # type: ignore[no-untyped-def]
    request: ChatRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    llm_service=Depends(get_llm_service_dependency),
) -> Any:  # TODO(TYPE): replace Any with concrete type
    """
    Chat with CVA using real LLM streaming (Server-Sent Events).

    Emits SSE lines: data: {"conversation_id": N}, then data: {"content": "..."}
    tokens as they arrive from the LLM, then data: [DONE].
    User message is persisted before streaming; assistant message is committed
    after streaming completes (or on client disconnect via try/finally).
    """
    try:
        _prompt_guard.sanitize(request.message, tenant_id=current_user.tenant_id)
    except PromptInjectionError:
        logger.warning("prompt_injection_blocked: tenant_id=%s", current_user.tenant_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": {"code": "INPUT_REJECTED", "message": "Input rejected", "details": {}},
            },
        )

    # Scope-check system prompt before spawning the generator (same as /chat)
    if request.system_prompt:
        if not has_scopes(current_user, [OAuth2Scope.ADMIN_ALL]):
            logger.warning(
                "User %s attempted system prompt override without admin scope (stream)",
                current_user.id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required for system prompt override",
            )
        effective_system_prompt: str | None = request.system_prompt
    else:
        effective_model: str = cast(str, request.model or os.getenv("LLM_MODEL", ""))
        effective_system_prompt = get_system_prompt(
            platform_name="SanskritiSetu",
            tenant_id=str(current_user.tenant_id),
            user_language="en",
            model_id=effective_model,
        )

    cva_service = build_cva_service(db, llm_service)

    async def generate() -> AsyncGenerator[str, None]:
        try:
            with anyio.fail_after(120):
                async for chunk in cva_service.chat_stream(
                    message=request.message,
                    user_id=current_user.id,
                    tenant_id=current_user.tenant_id,
                    conversation_id=request.conversation_id,
                    system_prompt=effective_system_prompt,
                    model=request.model,
                ):
                    yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except TimeoutError:
            yield f"data: {json.dumps({'error': 'Stream timed out after 120 seconds'})}\n\n"
            yield "data: [DONE]\n\n"
        except LLMTimeoutError as e:
            logger.error(
                "LLM timeout during streaming for user %s: %s: %s",
                current_user.id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            yield f"data: {json.dumps({'error': 'LLM service timed out. Please retry.'})}\n\n"
            yield "data: [DONE]\n\n"
        except LLMRateLimitError as e:
            logger.warning("LLM rate limit during streaming for user %s: %s", current_user.id, e)
            yield f"data: {json.dumps({'error': 'LLM rate limit exceeded. Please wait and retry.'})}\n\n"
            yield "data: [DONE]\n\n"
        except LLMServiceError as e:
            logger.error(
                "LLM service error during streaming for user %s: %s: %s",
                current_user.id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            yield f"data: {json.dumps({'error': 'LLM service error. Please retry.'})}\n\n"
            yield "data: [DONE]\n\n"
        except GovernanceVetoError as e:
            yield f"data: {json.dumps({'error': e.message, 'code': 'GOVERNANCE_BLOCKED', 'decision_id': e.details.get('decision_id')})}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as e:
            logger.error(
                "Chat processing value error during streaming: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            yield f"data: {json.dumps({'error': 'Chat processing error. Please retry.'})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("CVA streaming chat error: %s", e)
            yield f"data: {json.dumps({'error': 'An error occurred during streaming'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@chat_router.get(
    "/explain",
    response_model=ExplainResponse,
    status_code=status.HTTP_200_OK,
    summary="Get council explanation for a CVA decision (EU AI Act Art. 13)",
)
async def get_cva_explain(  # type: ignore[no-untyped-def]
    decision_id: str = Query(..., min_length=1, max_length=36),
    current_user: UserResponse = Depends(get_current_user),
    cva_service=Depends(get_cva_service_dependency),
) -> ExplainResponse:
    """Return the governance council explanation for a specific decision_id."""
    result = await cva_service.get_explain_for_decision(
        decision_id=decision_id,
        tenant_id=current_user.tenant_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Decision not found",
        )
    return ExplainResponse(**result)
