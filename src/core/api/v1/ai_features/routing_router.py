# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""AI Features -- Intelligent Routing sub-router (ADR-033 Laag 1)."""

from typing import cast

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.ai.intelligent_routing import (
    IntelligentRouter,
    RequestContext,
    RequestPriority,
)
from src.core.auth.api_deps import UserResponse, get_current_user, require_scopes, OAuth2Scope
from src.core.container import Container
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)

router = APIRouter()


class RoutingRequest(BaseModel):
    """Request model voor intelligent routing."""

    request_id: str = Field(description="Unique request identifier")
    user_id: str | None = None
    request_type: str = Field(description="Type of request")
    complexity_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Request complexity")
    priority: str = Field(
        default="normal", description="Request priority (low/normal/high/critical)"
    )
    estimated_compute_time: float = Field(
        default=1.0, description="Estimated compute time in seconds"
    )
    required_capabilities: list[str] = Field(default_factory=list)
    user_preferences: dict[str, object] = Field(default_factory=dict)
    session_context: dict[str, object] = Field(default_factory=dict)


class RoutingDecisionResponse(BaseModel):
    """Response model voor routing decisions."""

    request_id: str
    selected_route: dict[str, object]
    confidence: float
    reasoning: list[str]
    alternative_routes: list[dict[str, object]]
    decision_time_ms: float
    predicted_performance: dict[str, float]


@router.post("/routing/route", response_model=RoutingDecisionResponse)
@inject
async def route_request(
    request: RoutingRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    router_instance: IntelligentRouter = Depends(Provide[Container.intelligent_router]),
) -> RoutingDecisionResponse:
    """
    Get intelligent routing decision for a request.
    Requires: WRITE permission (EDITOR level).
    """
    try:
        logger.info(
            "User %s requesting route for: request_id=%s, type=%s",
            current_user.id,
            request.request_id,
            request.request_type,
        )

        request_context = RequestContext(
            request_id=request.request_id,
            user_id=request.user_id or str(current_user.id),
            session_id=cast("str | None", request.session_context.get("session_id")),
            request_type=request.request_type,
            priority=RequestPriority(request.priority),
            payload_size=cast(int, request.session_context.get("payload_size", 0)),
            expected_complexity=cast(
                str, request.session_context.get("expected_complexity", "medium")
            ),
            metadata={
                "complexity_score": request.complexity_score,
                "estimated_compute_time": request.estimated_compute_time,
                "required_capabilities": request.required_capabilities,
                "user_preferences": request.user_preferences,
                **request.session_context,
            },
        )

        decision = await router_instance.route(request_context)
        if decision is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Router returned no decision",
            )

        return RoutingDecisionResponse(
            request_id=request.request_id,
            selected_route=decision.selected_route.to_dict(),
            confidence=decision.confidence,
            reasoning=[decision.reasoning],
            alternative_routes=[alt.to_dict() for alt in decision.alternative_routes],
            decision_time_ms=decision.decision_time * 1000,
            predicted_performance={},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error routing request: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to route request",
        ) from e
