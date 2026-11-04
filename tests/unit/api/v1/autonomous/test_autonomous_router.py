"""Unit tests for autonomous workflows router (src/core/api/v1/autonomous/router.py).

Covers:
- POST /workflows/{workflow_id}/execute
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.routing import APIRoute

from src.core.api.v1.autonomous.router import (
    ExecuteWorkflowRequest,
    execute_workflow,
    router,
)


class DummyUser:
    def __init__(self, id: int = 1, tenant_id: int = 42) -> None:
        self.id = id
        self.tenant_id = tenant_id


def test_routes_registered() -> None:
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/api/v1/autonomous/workflows/{workflow_id}/execute" in paths


@pytest.mark.asyncio
async def test_execute_workflow_success() -> None:
    user = DummyUser(id=7, tenant_id=99)
    req = ExecuteWorkflowRequest(workflow_id="wf-100", initial_data={"param": "value"})

    mock_step = MagicMock()

    with patch.dict("sys.modules", {"src.core.tasks.workflow_tasks": MagicMock(execute_workflow_step=mock_step)}):
        resp = await execute_workflow(
            workflow_id="wf-100",
            request=req,
            current_user=user,
        )
        assert resp.status == "queued"
        assert resp.execution_id is not None
        assert "progress" in resp.stream_key
        mock_step.send.assert_called_once()
        sent_data = mock_step.send.call_args[0][0]
        assert sent_data["workflow_id"] == "wf-100"
        assert sent_data["tenant_id"] == 99
        assert sent_data["user_id"] == 7
        assert sent_data["data"] == {"param": "value"}
