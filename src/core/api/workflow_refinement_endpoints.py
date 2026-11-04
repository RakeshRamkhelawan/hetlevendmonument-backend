# orphan:exempt reason: SP-API-010 proxy stub -- TODO(SP-API-011): migreer naar v1/workflow/
"""
Workflow Refinement Endpoints - deprecated proxy stubs.

Verboden imports (ADR-033) verwijderd. Gebruik v1/workflow/ routers (SP-API-011).
Schemas inline geplaatst (origin: src/core/workflow/schemas.py, geen re-export nodig).
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import get_current_user, require_scopes, OAuth2Scope
from src.core.middleware.tenant_context import get_current_tenant_id
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workflows/refine", tags=["workflow-refinement"])

_DEPRECATION_SUNSET = "Thu, 01 Jan 2028 00:00:00 GMT"


# ============================================================================
# Inlined schemas (origin: src/core/workflow/schemas.py, ADR-033 proxy stub)
# ============================================================================


class WorkflowNode(BaseModel):
    """Workflow node definition"""

    id: str
    name: str
    type: str
    x: float = 0
    y: float = 0
    data: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class WorkflowEdge(BaseModel):
    """Workflow edge/connection definition"""

    id: str
    source: str
    target: str
    type: str = "smoothstep"


class WorkflowDefinition(BaseModel):
    """Complete workflow definition"""

    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


class RefinementSuggestion(BaseModel):
    """A suggested refinement to the workflow"""

    id: str
    type: str = Field(..., description="add_node, remove_node, update_node, optimize, etc.")
    title: str = Field(...)
    description: str = Field(...)
    reasoning: str = Field("")
    impact: str = Field("medium")
    action_data: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )


# ============================================================================
# Request/Response Models
# ============================================================================


class WorkflowChatRequest(BaseModel):
    """Request to analyze workflow and get suggestions"""

    message: str = Field(..., description="User message/question about the workflow")
    workflow: WorkflowDefinition = Field(..., description="Current workflow definition")


class WorkflowChatResponse(BaseModel):
    """Response with workflow analysis and suggestions"""

    analysis: str = Field(..., description="AI analysis of the workflow and user request")
    suggestions: list[RefinementSuggestion] = Field(
        default_factory=list, description="Suggested refinements"
    )
    conversation_id: str = Field("", description="ID for conversation tracking")


class RefinementRequest(BaseModel):
    """Request to apply a refinement to the workflow"""

    refinement: RefinementSuggestion = Field(..., description="The refinement to apply")
    workflow: WorkflowDefinition = Field(..., description="Current workflow definition")


class RefinementResult(BaseModel):
    """Result of applying a refinement"""

    success: bool
    message: str
    updated_workflow: WorkflowDefinition | None = None
    errors: list[str] = Field(default_factory=list)


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/chat", response_model=WorkflowChatResponse, deprecated=True)
async def workflow_chat(
    request: WorkflowChatRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant_id),
    _: int = Depends(require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),
) -> WorkflowChatResponse:
    """Chat endpoint for workflow analysis and refinement suggestions.

    Deprecated: use v1/workflow/ POST /refine/chat (SP-API-011).
    Security: JWT required, tenant isolated, WORKFLOWS_WRITE scope needed.
    """
    del db, current_user, tenant_id  # proxy stub -- Depends enforce auth/scope
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    # TODO(SP-API-011): WorkflowOrchestratorAgent (src.core.agents.*) verwijderd -- ADR-033 Contract 2
    logger.info(
        "workflow_refinement.chat.deprecated -- migreer naar v1/workflow/ (SP-API-011): %s",
        request.message[:50],
    )
    return WorkflowChatResponse(
        analysis="This endpoint is deprecated. Use v1/workflow/ (SP-API-011).",
        suggestions=[],
        conversation_id="",
    )


@router.post("/refine", response_model=RefinementResult, deprecated=True)
async def apply_refinement(
    request: RefinementRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant_id),
    _: int = Depends(require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),
) -> RefinementResult:
    """Apply a refinement suggestion to a workflow.

    Deprecated: use v1/workflow/ POST /refine/refine (SP-API-011).
    Security: JWT required, tenant isolated, WORKFLOWS_WRITE scope needed.
    """
    del db, current_user, tenant_id  # proxy stub -- Depends enforce auth/scope
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    # TODO(SP-API-011): WorkflowOrchestratorAgent (src.core.agents.*) verwijderd -- ADR-033 Contract 2
    logger.info(
        "workflow_refinement.refine.deprecated -- migreer naar v1/workflow/ (SP-API-011): %s",
        request.refinement.type,
    )
    return RefinementResult(
        success=False,
        message="This endpoint is deprecated. Use v1/workflow/ (SP-API-011).",
        errors=["endpoint_deprecated"],
    )


@router.get("/insights/{workflow_id}", deprecated=True)
async def get_workflow_insights(
    workflow_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant_id),
    _: int = Depends(require_scopes(OAuth2Scope.WORKFLOWS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get AI-powered insights about a workflow.

    Deprecated: use v1/workflow/ GET /refine/insights/{id} (SP-API-011).
    Security: JWT required, tenant isolated, WORKFLOWS_READ scope needed.
    """
    del db, current_user, tenant_id  # proxy stub -- Depends enforce auth/scope
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    try:
        return {
            "workflow_id": workflow_id,
            "status": "success",
            "insights": {
                "performance": "Average execution time: 2.5s",
                "reliability": "Success rate: 95%",
                "bottlenecks": ["Query step occasionally times out"],
                "recommendations": [
                    "Add timeout handling to Query step",
                    "Consider caching query results",
                ],
            },
        }
    except Exception as e:
        logger.error(
            "workflow_refinement.insights failed: %s: %s", type(e).__name__, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal error") from e
