"""Autonomous domain package (ADR-033 Laag 2).

NIET opnemen: router.py (exec) + progress_ws.py -- al via agentic.py geregistreerd.
"""

from fastapi import APIRouter

from .agents_router import agents_router
from .code_router import code_router
from .emergence_router import emergence_router
from .healing_router import healing_router

domain_router = APIRouter(tags=["Autonomous Systems"])
domain_router.include_router(agents_router)
domain_router.include_router(healing_router)
domain_router.include_router(code_router)
domain_router.include_router(emergence_router)

__all__ = ["domain_router"]
