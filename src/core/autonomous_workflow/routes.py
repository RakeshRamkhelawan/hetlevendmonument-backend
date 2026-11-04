"""Autonomous workflow router and integration."""

from typing import Any, Optional

from fastapi import APIRouter, Depends
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.autonomous_workflow.feedback import FeedbackService
from src.core.database import get_session

# Metrics
WORKFLOW_REQUESTS = Counter("workflow_requests_total", "Total workflow requests")
FEEDBACK_PROCESSING_TIME = Histogram(
    "feedback_processing_seconds", "Time spent processing feedback"
)

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/feedback")
async def submit_workflow_feedback(
    feedback_data: dict[str, Any], session: AsyncSession = Depends(get_session)  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Submit feedback for workflow execution."""
    WORKFLOW_REQUESTS.inc()

    with FEEDBACK_PROCESSING_TIME.time():
        feedback_service = FeedbackService(session)
        experience = await feedback_service.process_feedback(
            workflow_type=feedback_data["workflow_type"],
            input_data=feedback_data["input_data"],
            output_data=feedback_data["output_data"],
            feedback_score=feedback_data.get("feedback_score"),
        )

    return {"status": "success", "experience_id": experience.id}


@router.get("/statistics")
async def get_workflow_statistics(
    workflow_type: str | None = None, session: AsyncSession = Depends(get_session)
) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Get feedback and training statistics."""
    feedback_service = FeedbackService(session)
    return await feedback_service.get_feedback_statistics(workflow_type)
