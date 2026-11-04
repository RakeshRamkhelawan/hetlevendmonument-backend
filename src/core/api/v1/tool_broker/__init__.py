"""Tool Broker domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from src.core.api.v1.tool_broker.router import router as tb_composite_router

domain_router = APIRouter(tags=["Tool Broker"])
domain_router.include_router(tb_composite_router)

__all__ = ["domain_router"]
