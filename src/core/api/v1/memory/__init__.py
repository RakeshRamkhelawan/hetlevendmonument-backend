"""
Memory domain -- RAG configuration and document indexing.

Migrated from src/core/api/memory_endpoints.py (SP-API-003 Dag 5).
"""

from fastapi import APIRouter

from src.core.api.v1.memory.router import router as memory_composite_router

domain_router = APIRouter(prefix="/api/v1", tags=["Memory"])
domain_router.include_router(memory_composite_router)

__all__ = ["domain_router"]
