"""
Unit tests: workflow task rejects missing tenant_id (TI-004 CRITICAL).
"""

import pytest


def test_workflow_task_rejects_missing_tenant_id():
    from src.core.tasks.workflow_tasks import execute_workflow_step

    with pytest.raises(ValueError, match="tenant_id missing"):
        execute_workflow_step({"task_id": "x"})


def test_workflow_task_rejects_none_tenant_id():
    from src.core.tasks.workflow_tasks import execute_workflow_step

    with pytest.raises(ValueError, match="tenant_id missing"):
        execute_workflow_step({"task_id": "x", "tenant_id": None})
