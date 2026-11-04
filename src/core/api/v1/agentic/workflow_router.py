"""Workflow router -- AUDIT-DB14a ADR-033 compliant (geen directe DB-imports)."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.core.api.v1.agentic.dependencies import get_agentic_orchestration_service
from src.core.api.v1.agentic.orchestration_service import (
    AgenticOrchestrationService,
    AgenticWorkflowConfig,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow", tags=["agentic-workflow"])


@router.post("/start")
async def start_workflow(
    config: AgenticWorkflowConfig,
    svc: AgenticOrchestrationService = Depends(get_agentic_orchestration_service),
) -> dict[str, object]:
    try:
        result = await svc.start_workflow(config)
    except RuntimeError as exc:
        logger.error("Workflow dispatch mislukt in router: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Workflow dispatch mislukt") from exc
    return {"success": True, "data": result}


@router.get("/{task_id}/status")
async def get_workflow_status(
    task_id: str,
    svc: AgenticOrchestrationService = Depends(get_agentic_orchestration_service),
) -> dict[str, object]:
    result = await svc.get_workflow_status(task_id)
    return {"success": True, "data": result}


@router.post("/{task_id}/step")
async def advance_workflow_step(
    task_id: str,
    svc: AgenticOrchestrationService = Depends(get_agentic_orchestration_service),
) -> dict[str, object]:
    result = await svc.advance_workflow_step(task_id)
    return {"success": True, "data": result}


@router.delete("/{task_id}")
async def cancel_workflow(
    task_id: str,
    svc: AgenticOrchestrationService = Depends(get_agentic_orchestration_service),
) -> dict[str, object]:
    result = await svc.cancel_workflow(task_id)
    return {"success": True, "data": result}
