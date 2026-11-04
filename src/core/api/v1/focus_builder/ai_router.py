"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
FocusBuilder AI-Assisted Flow Generation sub-router (ADR-033 Laag 1).

Routes:
- POST /ai/suggest
- POST /ai/generate
"""

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response

if TYPE_CHECKING:
    from src.core.api.v1.focus_builder.dependencies import AgentCouncil  # own-domain -- ADR-033
    from src.domains.flows.service import FocusBuilderService
from loguru import logger

from src.core.api.v1.focus_builder.shared import (
    _track_focus_builder_action,
    create_error_response,
    enrich_span,
    get_focus_builder_service,
    limiter,
)
from src.core.api.v1.focus_builder.dependencies import get_focus_builder_council
from src.core.auth.api_deps import get_current_user_dependency
from src.core.middleware.tenant_context import get_current_tenant_id
from src.core.api.v1.focus_builder.dependencies import (  # own-domain -- ADR-033
    FocusSuggestionService,
    SuggestionRequest,
    SuggestionResponse,
)

ai_router = APIRouter()


@ai_router.post("/ai/suggest", response_model=SuggestionResponse)
@limiter.limit("3/minute")
async def suggest_nodes(
    request: Request,
    response: Response,
    payload: SuggestionRequest,
    tenant_id: int = Depends(get_current_tenant_id),
    current_user: Any = Depends(get_current_user_dependency),  # TODO(TYPE): replace Any with concrete type
    council: "AgentCouncil" = Depends(get_focus_builder_council),
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
) -> SuggestionResponse:
    """
    AI-powered workflow node suggestions.
    Governed by AgentCouncil deliberation before LLM call (ADR-031).
    Rate limit: 3 requests per minute (LLM-backed).
    """
    from src.core.api.v1.focus_builder.dependencies import (
        require_council_approval,
    )  # own-domain -- ADR-033

    enrich_span(
        request,
        current_user.id,
        operation="ai_suggest",
        prompt_length=len(payload.prompt),
    )
    logger.info("ai_suggest_request", user_id=current_user.id, tenant_id=tenant_id)

    await require_council_approval(
        council=council,
        tenant_id=tenant_id,
        user_id=current_user.id,
        action_type="focus_builder.ai_suggest",
        action_params={
            "prompt_length": len(payload.prompt),
        },
        reasoning="User requested AI-powered workflow node suggestions.",
        confidence=1.0,
        db=service.db,
    )

    suggestion_service = FocusSuggestionService(tenant_id=tenant_id)
    result = await suggestion_service.get_suggestions(payload)
    logger.info(
        "ai_suggest_completed",
        user_id=current_user.id,
        suggestion_count=len(result.suggestions),
    )
    return result


@ai_router.post("/ai/generate")
@limiter.limit("3/minute")
async def generate_flow_ai(
    request: Request,
    response: Response,
    payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: Any = Depends(get_current_user_dependency),  # TODO(TYPE): replace Any with concrete type
    council: "AgentCouncil" = Depends(get_focus_builder_council),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Generate a complete flow from natural language prompt using AI.
    Governed by AgentCouncil deliberation before generation (ADR-031).
    Rate limit: 3 requests per minute (LLM-backed, expensive).
    """
    from src.core.api.v1.focus_builder.dependencies import (
        require_council_approval,
    )  # own-domain -- ADR-033
    from src.domains.flows.agentic_service import AgenticFlowService

    enrich_span(request, current_user.id, operation="ai_generate")
    logger.info("ai_generate_request", user_id=current_user.id)
    prompt = payload.get("prompt", "")
    if not prompt:
        raise HTTPException(
            status_code=400,
            detail=create_error_response("VALIDATION_ERROR", "prompt is required"),
        )

    await require_council_approval(
        council=council,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="focus_builder.ai_generate",
        action_params={
            "prompt_length": len(prompt),
        },
        reasoning="User requested AI workflow generation from natural language prompt.",
        confidence=1.0,
        db=service.db,
    )

    agentic_service = AgenticFlowService(tenant_id=current_user.tenant_id)
    result: dict[str, Any] = cast(  # TODO(TYPE): replace Any with concrete type
        dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        await agentic_service.generate_flow_from_prompt(
            prompt=prompt,
            tenant_id=current_user.tenant_id,
        ),
    )

    if not result.get("success", False):
        error = result.get("error", {})
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                error.get("code", "GENERATION_ERROR"),
                error.get("message", "AI generation failed"),
            ),
        )

    react_flow_graph = result.get("data", {}).get("react_flow_graph", {})
    node_count = len(react_flow_graph.get("nodes", []))
    logger.info("ai_generate_completed", user_id=current_user.id, node_count=node_count)
    await _track_focus_builder_action(
        db=service.db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        session_id=request.headers.get("x-session-id", f"fb_{current_user.id}"),
        behavior_type="focus_builder.ai_generate",
        context={"prompt_length": len(prompt), "node_count": node_count},
    )
    return result
