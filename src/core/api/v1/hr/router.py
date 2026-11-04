"""Composiet-router voor het `hr`-domein (BE-AGT-060, Fase 3 dag 3, ADR-033 Laag 1).

Importeert NOOIT direct database/governance/agents/workflow/llm -- alleen de twee
sub-routers, die zelf hun dependencies via `.dependencies` (Laag 2) betrekken.
"""

from __future__ import annotations

from fastapi import APIRouter

from .skills_import_router import router as skills_router
from .deadlines_router import router as deadlines_router
from .my_training_proposals_router import router as my_proposals_router
from .training_proposals_router import router as proposals_router
from .trainings_import_router import router as trainings_router

router = APIRouter(prefix="/api/v1/hr", tags=["HR"])
router.include_router(skills_router)
router.include_router(trainings_router)
router.include_router(proposals_router)
router.include_router(my_proposals_router)
router.include_router(deadlines_router)
