from __future__ import annotations

from itertools import count
from typing import Any

from src.core.agents.learning_loop import LearningSource, LearningType

_task_counter = count(1)


def next_task_id(prefix: str = "phase7-task") -> str:
    return f"{prefix}-{next(_task_counter)}"


def make_observation_context(
    *,
    tenant_id: int,
    agent_id: str,
    agent_type: str,
    task_type: str = "analysis",
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "task_type": task_type,
    }


def make_observation_payload(index: int) -> dict[str, Any]:
    return {
        "task_title": f"Phase 7 task {index}",
        "task_description": "End-to-end validation task",
        "result_data": {"index": index, "status": "ok"},
        "error_message": None,
    }


def make_outcome_metrics(index: int, success: float = 1.0) -> dict[str, float]:
    return {
        "execution_time": 0.01 * float(index + 1),
        "success": success,
        "success_rate": success,
        "error_count": 0.0 if success >= 0.5 else 1.0,
    }


def make_tool_event_data(index: int, tenant_id: int) -> dict[str, Any]:
    return {
        "tool_name": "test__echo",
        "agent_id": "python-pro-agent",
        "payload": {"index": index},
        "result": {"ok": True, "index": index},
        "duration_seconds": 0.01,
        "success": True,
        "tenant_id": tenant_id,
    }


def learning_defaults() -> dict[str, Any]:
    return {
        "source": LearningSource.TASK_EXECUTION,
        "learning_type": LearningType.PATTERN_RECOGNITION,
    }
