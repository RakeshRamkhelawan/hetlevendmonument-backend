"""
Knowledge domain -- knowledge base management via agent task dispatch.

Migrated from src/core/api/knowledge_endpoints.py (SP-API-003 Dag 5).
Registered via agents registry with prefix /api/v1/agents.
"""

from fastapi import APIRouter

from src.core.api.v1.knowledge.router import router as knowledge_composite_router

# NOTE: domain_router has no /api/v1 prefix here because the agents registry
# injects prefix="/api/v1/agents" at include_router() time -- matching original behaviour.
domain_router = APIRouter(tags=["Knowledge"])
domain_router.include_router(knowledge_composite_router)

__all__ = ["domain_router"]
