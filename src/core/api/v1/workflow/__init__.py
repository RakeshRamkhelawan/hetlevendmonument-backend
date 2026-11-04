"""
Workflow domain package (ADR-033 Laag 2).

Exports domain_router for use by registries/workflows.py.
"""

from fastapi import APIRouter

from src.core.api.v1.workflow.router import router as workflow_composite_router

domain_router = APIRouter()
domain_router.include_router(workflow_composite_router)

__all__ = ["domain_router"]
