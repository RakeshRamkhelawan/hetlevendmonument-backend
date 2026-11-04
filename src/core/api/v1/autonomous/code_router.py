"""Dynamic Code Generation sub-router (ADR-033 Laag 1)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from src.core.api.dependencies import require_admin_user

from src.core.auth.api_deps import UserResponse, require_scopes, OAuth2Scope
from src.core.api.autonomous_endpoints import CodeGenerationRequest
from src.core.generation.dynamic_code_generator import get_code_generator

logger = logging.getLogger(__name__)

code_router = APIRouter(prefix="/api/v1/autonomous")


@code_router.post("/code/generate")
async def generate_code(
    request: CodeGenerationRequest,
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Generate code dynamically based on requirements. Requires: AGENTS_WRITE

    Uitgeschakeld sinds ADR-036 D12.5 (CRITICAL/P0,
    docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md): genereert code
    zonder ooit GovernanceContract.is_action_permitted() aan te roepen.
    Zelfde onderliggende oorzaak als D12.5, ontdekt tijdens de Gate 2-
    doc-review van die fix.
    """
    raise HTTPException(
        status_code=503,
        detail=(
            "Dynamic code generation is temporarily disabled pending a governance "
            "review (ADR-036 D12.5)."
        ),
    )


@code_router.get("/code/templates")
async def get_code_templates(
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get available code generation templates. Requires: AGENTS_READ"""
    try:
        code_generator = get_code_generator()
        templates = await code_generator.get_templates()
        return {"templates": templates, "count": len(templates)}
    except Exception as e:
        logger.error("Failed to get code templates: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@code_router.get("/code/metrics")
async def get_generation_metrics(
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get code generation performance metrics. Requires: AGENTS_READ"""
    try:
        code_generator = get_code_generator()
        metrics = await code_generator.get_generation_metrics()
        return {
            "total_generations": metrics.get("total_generations", 0),
            "successful_generations": metrics.get("successful_generations", 0),
            "success_rate": metrics.get("success_rate", 0.0),
            "avg_generation_time": metrics.get("avg_generation_time", 0.0),
            "code_types_generated": metrics.get("code_type_distribution", {}),
            "quality_metrics": metrics.get("quality_summary", {}),
            "recent_generations": metrics.get("recent_generations", []),
        }
    except Exception as e:
        logger.error("Failed to get generation metrics: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e
