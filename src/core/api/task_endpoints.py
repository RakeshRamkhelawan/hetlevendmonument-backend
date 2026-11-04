# orphan:exempt -- legacy shim, pre-migration flat endpoint
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from src.core.api.setup.app_state import app_state
from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.shared.config import get_feature_flag
from src.core.shared.interfaces import TaskData

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Tasks"])


@router.post(
    "/api/v1/tasks",
    response_model=dict[str, str],
    dependencies=[Depends(get_current_user)],
)
async def create_task(
    task_request: dict[str, Any], current_user: UserResponse = Depends(get_current_user)  # TODO(TYPE): replace Any with concrete type
) -> dict[str, str]:
    try:
        task = TaskData(
            title=task_request.get("title", "Untitled Task"),
            description=task_request.get("description", ""),
            priority=task_request.get("priority", "MEDIUM"),
            metadata=task_request.get("metadata", {}),
        )
        app_state["task_queue"].append(task)
        if get_feature_flag("websocket_updates") and app_state["websocket_manager"]:
            await app_state["websocket_manager"].broadcast(
                {
                    "type": "task_created",
                    "task": task.dict() if hasattr(task, "dict") else task.__dict__,
                }
            )
        return {
            "task_id": task.id,
            "status": "created",
            "message": "Task created successfully",
        }
    except Exception as e:
        logger.error(f"Task creation error: {e}")
        raise HTTPException(status_code=500, detail="Task creation failed")


@router.get(
    "/api/v1/tasks",
    response_model=list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    dependencies=[Depends(get_current_user)],
)
async def list_tasks(
    status: str | None = None,
    limit: int = 50,
    current_user: UserResponse = Depends(get_current_user),
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    try:
        tasks = app_state["task_queue"]
        if status:
            tasks = [t for t in tasks if t.status.value == status]
        tasks = tasks[:limit]
        return [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status.value,
                "priority": t.priority.value,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]
    except Exception as e:
        logger.error(f"Task listing error: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.post(
    "/api/v1/tasks/{task_id}/execute",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    dependencies=[Depends(get_current_user)],
)
async def execute_task(
    task_id: str, current_user: UserResponse = Depends(get_current_user)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    try:
        task = next((t for t in app_state["task_queue"] if t.id == task_id), None)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        agent = app_state["cva_agent"]
        if not agent:
            raise HTTPException(status_code=503, detail="No agents available")
        app_state["active_tasks"][task_id] = task
        result = await agent.process_task(task)
        task.status = "completed" if result.success else "failed"
        app_state["active_tasks"].pop(task_id, None)
        if get_feature_flag("websocket_updates") and app_state["websocket_manager"]:
            await app_state["websocket_manager"].broadcast(
                {
                    "type": "task_completed",
                    "task_id": task_id,
                    "success": result.success,
                }
            )
        return {
            "task_id": task_id,
            "success": result.success,
            "result": result.result_data,
            "execution_time": result.execution_time,
        }
    except Exception as e:
        app_state["active_tasks"].pop(task_id, None)
        logger.error(f"Task execution error: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")
