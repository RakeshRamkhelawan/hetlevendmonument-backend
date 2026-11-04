"""CVA legacy chat endpoint -- POST /chat/legacy (ADR-033 Laag 1)."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import traceback
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.core.api.v1.cva.dependencies import (
    AsyncSession,
    execute_cva_council_gate,
    get_cva_council_dependency,
    get_db,
    get_optional_conversation_memory,
)
from src.core.api.v1.cva.state import get_cva_agent
from src.core.auth.api_deps import UserResponse, get_current_user_dependency as get_current_user

if TYPE_CHECKING:
    from src.core.api.v1.cva.dependencies import ConversationMemory  # own-domain -- ADR-033

logger = logging.getLogger(__name__)

legacy_router = APIRouter(prefix="/api/v1/cva", tags=["cva"])


class CVAChatRequest(BaseModel):
    """Request model for CVA legacy chat."""

    message: str
    conversation_history: list[dict[str, str]] | None = []
    user_id: str | None = "anonymous"
    context: dict[str, Any] | None = {}  # TODO(TYPE): replace Any with concrete type
    model: str | None = None


class CVAChatResponse(BaseModel):
    """Response model for CVA legacy chat."""

    response: str
    success: bool
    confidence: float
    execution_time: float
    suggestions: list[str]
    llm_provider_used: str | None = None
    orchestration_used: bool = False
    performance_metrics: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    conversation_id: str | None = None
    actions: list[dict[str, Any]] | None = None  # TODO(TYPE): replace Any with concrete type
    decision_id: str | None = None


@legacy_router.post("/chat/legacy", response_model=CVAChatResponse)
async def chat_with_cva(
    request: CVAChatRequest,
    current_user: UserResponse = Depends(get_current_user),
    memory: ConversationMemory | None = Depends(get_optional_conversation_memory),
    council: Any = Depends(get_cva_council_dependency),  # TODO(TYPE): replace Any with concrete type
    db: AsyncSession = Depends(get_db),
) -> CVAChatResponse:
    """
    Chat with the Ultimate CVA Agent (LEGACY - use /chat instead).
    """
    # Council gate: must run before any LLM/agent invocation (ADR-015/031, RC-002)
    decision = await execute_cva_council_gate(
        council=council,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_params={"message_preview": request.message[:100]},
        reasoning=request.message[:500],
        model_id=request.model or "unknown",
        db=db,
    )
    decision_id = str(decision.decision_id)

    try:
        logger.info("User %s chatting with CVA: %s...", current_user.id, request.message[:50])
        start_time = time.time()

        try:
            if memory is not None:
                await memory.add_message(
                    int(current_user.id), {"role": "user", "content": request.message}
                )
        except Exception as mem_error:
            logger.warning("Failed to persist user message: %s", mem_error)

        cva_agent = await get_cva_agent(tenant_id=current_user.tenant_id)

        logger.info("[TIMEOUT] CVA processing with 30s timeout...")
        try:
            result = await asyncio.wait_for(
                cva_agent.process_command(
                    user_input=request.message,
                    context={
                        "conversation_history": request.conversation_history,
                        "user_id": request.user_id,
                        "model": request.model,
                        **(request.context or {}),
                    },
                ),
                timeout=90.0,
            )
        except TimeoutError:
            elapsed = time.time() - start_time
            logger.error("CVA processing timeout after %.1fs", elapsed)
            return CVAChatResponse(
                response=(
                    f"[TIMEOUT] CVA processing timed out after {elapsed:.0f} seconds. "
                    "The LLM service may be slow or unreachable."
                ),
                success=False,
                confidence=0.0,
                execution_time=elapsed,
                suggestions=[
                    "Verify your API keys are valid",
                    "Check internet connection to LLM service",
                    "Try a simpler request",
                ],
                llm_provider_used="timeout",
                orchestration_used=False,
                decision_id=decision_id,
            )

        conversation_id = f"conv_{uuid.uuid4().hex[:8]}"

        actions_list: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        response_content: str

        response_dict: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
        if isinstance(result.response, dict):
            response_dict = result.response

        if response_dict is not None:
            if response_dict.get("needs_clarification"):
                response_content = response_dict.get(
                    "clarification", "Please clarify your request."
                )
                action = response_dict.get("action")
                if action is not None:
                    actions_list.append(
                        action if isinstance(action, dict) else {"action": str(action)}
                    )
            else:
                response_content = response_dict.get(
                    "llm_analysis",
                    response_dict.get(
                        "message",
                        response_dict.get(
                            "response",
                            response_dict.get("content", str(result.response)),
                        ),
                    ),
                )
        else:
            response_content = str(result.response)

        if isinstance(response_content, str):
            response_content = response_content.encode("ascii", errors="replace").decode("ascii")

        try:
            if memory is not None:
                await memory.add_message(
                    int(current_user.id),
                    {"role": "assistant", "content": response_content},
                )
        except Exception as mem_error:
            logger.warning("Failed to persist assistant message: %s", mem_error)

        return CVAChatResponse(
            response=response_content,
            success=result.success,
            confidence=result.confidence,
            execution_time=result.execution_time,
            suggestions=result.suggestions,
            llm_provider_used=result.llm_provider_used,
            orchestration_used=result.orchestration_used,
            performance_metrics=result.performance_metrics,
            conversation_id=conversation_id,
            actions=actions_list if actions_list else None,
            decision_id=decision_id,
        )

    except Exception as e:
        sys.stderr.write("CRITICAL CVA ERROR: %s\n" % e)
        traceback.print_exc(file=sys.stderr)
        if "RateLimitError" in type(e).__name__:
            logger.error("LLM rate limit exceeded: %s", e)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="LLM rate limit exceeded. Please try again later.",
            )

        logger.exception("CVA chat error: %s", e)
        raise HTTPException(
            status_code=500,
            detail="CVA chat service error. Please try again later.",
        )
