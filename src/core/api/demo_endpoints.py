# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
"""
Demo API endpoints for unauthenticated playground access.

TASK-001.2: Interactive Demo Playground
Allows visitors to test platform without account.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


class DemoWorkflow(BaseModel):
    """Demo workflow model for playground."""

    id: str
    name: str
    description: str
    category: str


# Pre-defined demo workflows
DEMO_WORKFLOWS = [
    DemoWorkflow(
        id="demo-1",
        name="Donor Churn Analysis",
        description="Analyze donor retention patterns and predict churn risk",
        category="analytics",
    ),
    DemoWorkflow(
        id="demo-2",
        name="Content Generation",
        description="Generate cultural heritage content using AI",
        category="content",
    ),
    DemoWorkflow(
        id="demo-3",
        name="Heritage Translation",
        description="Translate heritage texts between Dutch and Hindi",
        category="translation",
    ),
]


@router.get("/workflows", response_model=list[DemoWorkflow])
async def get_demo_workflows() -> list[DemoWorkflow]:
    """
    Get available demo workflows for playground.

    No authentication required.
    Returns: List[Any] of demo workflows  # TODO(TYPE): replace Any with concrete type
    """
    logger.info("Demo workflows requested")
    return DEMO_WORKFLOWS


@router.post("/execute/{workflow_id}")
async def execute_demo_workflow(workflow_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Execute a demo workflow (simulated).

    No authentication required.
    Rate limited by session (handled in frontend).

    Args:
        workflow_id: ID of demo workflow to execute

    Returns:
        Simulated execution result
    """
    valid_ids = [wf.id for wf in DEMO_WORKFLOWS]
    if workflow_id not in valid_ids:
        raise HTTPException(status_code=404, detail="Demo workflow not found")

    workflow = next(wf for wf in DEMO_WORKFLOWS if wf.id == workflow_id)
    logger.info(f"Demo workflow executed: {workflow_id}")

    # Simulated results based on workflow type
    results = {
        "demo-1": {
            "churn_risk_score": 0.23,
            "at_risk_donors": 15,
            "recommendation": "Focus on re-engagement campaign for Q1 donors",
        },
        "demo-2": {
            "generated_content": "The rich tapestry of Indo-Dutch cultural exchange...",
            "word_count": 250,
            "sentiment": "positive",
        },
        "demo-3": {
            "original": "Cultureel erfgoed verbindt gemeenschappen",
            "translated": "Cultural heritage connects communities",
            "confidence": 0.95,
        },
    }

    return {
        "status": "completed",
        "workflow_id": workflow_id,
        "workflow_name": workflow.name,
        "result": results.get(workflow_id, {}),
        "message": f"Demo execution of '{workflow.name}' completed successfully",
    }
