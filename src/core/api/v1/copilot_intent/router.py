"""Copilot Intent Parser composite router -- assembles parse sub-router.

Migrated from src/core/api/copilot_endpoints.py (SP-API-006 Dag 1).
"""

from fastapi import APIRouter

from .parse_router import router as parse_router

router = APIRouter()
router.include_router(parse_router)
