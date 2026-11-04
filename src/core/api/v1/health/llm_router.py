"""Health check sub-router: LLM provider status.

ADR-033 Laag 1 sub-router (max 200 lines).
"""

from fastapi import APIRouter

from src.core.api.health_endpoints import LLMHealthResponse

router = APIRouter()


@router.get("/llm", response_model=LLMHealthResponse, tags=["Health"])
async def llm_health_check() -> LLMHealthResponse:
    """LLM provider health status. Delegates to health_endpoints."""
    from src.core.api.health_endpoints import llm_health_check as _llm_health_check

    return await _llm_health_check()
