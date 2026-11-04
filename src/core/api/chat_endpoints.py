# orphan:exempt -- legacy shim, pre-migration flat endpoint
import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException

from src.core.api.setup.app_state import app_state
from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.shared.interfaces import TaskData

logger = logging.getLogger(__name__)
router = APIRouter(tags=["CVA Chat"])


def _build_conversation_context(
    conversation_history: list[dict[str, str]],
) -> str:
    """Build conversation context string from history for CVA agent"""
    if not conversation_history:
        return "This is a new conversation with no previous context."
    recent_history = conversation_history[-5:]
    context_parts = ["Previous conversation context:"]
    for msg in recent_history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if role == "user":
            context_parts.append(f"User: {content}")
        elif role == "assistant":
            context_parts.append(f"CVA: {content}")
    context_parts.append(f"\nTotal conversation length: {len(conversation_history)} messages")
    return "\n".join(context_parts)


@router.post(
    "/api/v1/cva/strategy",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    dependencies=[Depends(get_current_user)],
)
async def request_strategy(
    request: dict[str, Any], current_user: UserResponse = Depends(get_current_user)  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not app_state["cva_agent"]:
        raise HTTPException(status_code=503, detail="CVA agent not initialized")
    try:
        task = TaskData(
            title="Strategic Analysis",
            description=request.get("description", ""),
            metadata={
                "type": "strategic_planning",
                "context": request.get("context", {}),
                "objectives": request.get("objectives", []),
            },
        )
        result = await app_state["cva_agent"].process_task(task)
        return {
            "task_id": task.id,
            "strategy": result.result_data,
            "success": result.success,
            "execution_time": result.execution_time,
        }
    except Exception as e:
        logger.error(f"Strategy request error: {e}")
        raise HTTPException(status_code=500, detail="Strategy generation failed")


@router.get(
    "/api/v1/llm/metrics",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    dependencies=[Depends(get_current_user)],
)
async def get_llm_metrics(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not app_state["cva_agent"]:
        raise HTTPException(status_code=503, detail="CVA agent not initialized")
    try:
        if hasattr(app_state["cva_agent"], "get_cva_metrics"):
            return cast(
                dict[str, Any], app_state["cva_agent"].get_cva_metrics()  # TODO(TYPE): replace Any with concrete type
            )  # TODO(TYPE): replace Any with concrete type
        return {"status": "metrics_not_available"}
    except Exception as e:
        logger.error(f"Error getting LLM metrics: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")
