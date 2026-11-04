"""
Async Workers for Background Task Processing
============================================

This module provides Dramatiq-based async workers for:
- Workflow execution (C.7 engine)
- Task execution (parallel task processing)
- Scheduled jobs and maintenance tasks
- Pack health aggregation

Usage:
    # Start worker
    dramatiq src.workers.workflow_worker -p 4 -t 4
    dramatiq src.workers.actors -p 2 -t 4  # For maintenance tasks

    # Enqueue task programmatically
    from src.workers import execute_workflow_task
    execute_workflow_task.send(execution_id="abc-123")

    # Or use the actors module directly
    from src.workers.actors import run_pack_health_aggregation
    run_pack_health_aggregation.send()
"""

from typing import Any

from .workflow_worker import execute_task_task, execute_workflow_task

# Pre-declare with Any so the except branch can assign _DummySender without type error
run_pack_health_aggregation: Any = None
run_daily_maintenance: Any = None

# Import actors if available
try:
    from .actors import run_daily_maintenance, run_pack_health_aggregation
except ImportError:
    # Actors might not be available if dependencies are missing
    class _DummySender:
        """Dummy object with .send() method for compatibility."""

        def send(self, *args: Any, **kwargs: Any) -> Any:
            return None

    run_pack_health_aggregation = _DummySender()
    run_daily_maintenance = _DummySender()

__all__ = [
    "execute_workflow_task",
    "execute_task_task",
    "run_pack_health_aggregation",
    "run_daily_maintenance",
]
