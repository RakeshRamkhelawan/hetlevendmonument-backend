"""Agentic AI router composite (ADR-033 Laag 2)."""

from fastapi import APIRouter

from src.core.api.v1.agentic import agent_discovery, agents, learning, monitoring, router_debug
from src.core.api.v1.agentic.agentic_domain_router import agentic_domain_router
from src.core.api.v1.agentic.agentic_roi_router import agentic_roi_router
from src.core.api.v1.agentic.agentic_routing_router import agentic_routing_router
from src.core.api.v1.agentic.workflow_router import router as workflow_router

router = APIRouter(prefix="/agentic", tags=["Agentic AI"])

# Pre-existing sub-module routers
router.include_router(agents.router)
router.include_router(agent_discovery.router)
router.include_router(router_debug.router)
router.include_router(learning.router)
router.include_router(monitoring.router)

# Dag 5 Laag 1 sub-routers
router.include_router(agentic_routing_router)
router.include_router(agentic_domain_router)
router.include_router(agentic_roi_router)

# S5 AUDIT-DB14a: workflow orchestration service layer
router.include_router(workflow_router)
