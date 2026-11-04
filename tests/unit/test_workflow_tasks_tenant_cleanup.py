"""Unit tests for workflow_tasks tenant context cleanup.

Regression test for AUDIT-003: if AutonomousAgent construction fails,
set_tenant_id(None) must still run so a pooled Dramatiq thread does not
keep the previous tenant_id.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.tasks.workflow_tasks import execute_workflow_step


def test_cleanup_runs_when_agent_init_fails() -> None:
    """When agent construction raises, tenant ContextVar must still be cleared."""
    tenant_id = 42
    task_data: dict[str, object] = {"tenant_id": tenant_id, "task_id": "task-1"}
    cleanup_calls: list[object] = []

    def fake_set_tenant_id(value: object) -> None:
        cleanup_calls.append(value)

    class FailingAgent:
        """Stand-in AutonomousAgent whose __init__ always raises."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("agent init failed")

    with (
        patch("src.core.tasks.workflow_tasks.AutonomousAgent", FailingAgent),
        patch("src.core.tasks.workflow_tasks.set_tenant_id", side_effect=fake_set_tenant_id),
    ):
        with pytest.raises(RuntimeError, match="agent init failed"):
            execute_workflow_step(task_data)

    # set_tenant_id should be called twice: once with tenant_id, once with None.
    assert cleanup_calls == [tenant_id, None]
