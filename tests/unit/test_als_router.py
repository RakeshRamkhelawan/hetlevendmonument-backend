import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.core.api.v1.als.shared import TaskRequest
from src.core.api.v1.als.als_health_router import get_system_health
from src.core.api.v1.als.als_tasks_router import broadcast_message, delegate_task
from src.core.shared.interfaces import ExecutionResult


@pytest.fixture
def mock_orchestrator():
    orchestrator = Mock()
    orchestrator.delegate_task = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            task_id="task_1",
            result_data={"assigned_agent": "agent-alpha"},
        )
    )
    orchestrator.get_system_health = AsyncMock(
        return_value={
            "tenant_id": 42,
            "total_agents": 3,
            "healthy": 2,
            "stressed": 1,
            "health_percentage": 66.67,
            "active_tasks": 1,
        }
    )
    orchestrator.broadcast_to_all = AsyncMock(return_value=["signal-1"])
    return orchestrator


@pytest.fixture
def mock_user():
    """Mock UserResponse — required after AI Act governance gate was added (ADR-031)."""
    user = Mock()
    user.id = 1
    return user


@pytest.fixture
def mock_db():
    """Mock AsyncSession — required after council governance was wired to delegate_task."""
    return AsyncMock()


class TestAlsRouter:
    @pytest.mark.asyncio
    async def test_delegate_task_success_maps_error_contract(
        self, mock_orchestrator, mock_user, mock_db
    ):
        with (
            patch(
                "src.core.api.v1.als.als_tasks_router.get_orchestrator",
                return_value=mock_orchestrator,
            ),
            patch(
                "src.core.api.v1.als.als_tasks_router.build_council",
                new=AsyncMock(return_value=AsyncMock()),
            ),
            patch(
                "src.core.api.v1.als.als_tasks_router.require_council_approval",
                new=AsyncMock(),
            ),
        ):
            response = await delegate_task(
                request=TaskRequest(task_type="analysis", payload={"topic": "risk"}),
                tenant_id=42,
                db=mock_db,
                current_user=mock_user,
            )

        assert response.success is True
        assert response.task_id == "task_1"
        assert response.assigned_agent == "agent-alpha"
        assert response.error is None

    @pytest.mark.asyncio
    async def test_delegate_task_timeout_returns_504(self, mock_orchestrator, mock_user, mock_db):
        async def slow_delegate(*_args, **_kwargs):
            await asyncio.sleep(0.05)

        mock_orchestrator.delegate_task.side_effect = slow_delegate

        with (
            patch(
                "src.core.api.v1.als.als_tasks_router.get_orchestrator",
                return_value=mock_orchestrator,
            ),
            patch(
                "src.core.api.v1.als.als_tasks_router.ALS_ORCHESTRATOR_TIMEOUT_SECONDS",
                0.001,
            ),
            patch(
                "src.core.api.v1.als.als_tasks_router.build_council",
                new=AsyncMock(return_value=AsyncMock()),
            ),
            patch(
                "src.core.api.v1.als.als_tasks_router.require_council_approval",
                new=AsyncMock(),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delegate_task(
                    request=TaskRequest(task_type="analysis", payload={"topic": "risk"}),
                    tenant_id=42,
                    db=mock_db,
                    current_user=mock_user,
                )

        assert exc_info.value.status_code == 504
        assert exc_info.value.detail == "ALS task delegation timed out"

    @pytest.mark.asyncio
    async def test_health_timeout_returns_504(self, mock_orchestrator):
        async def slow_health():
            await asyncio.sleep(0.05)

        mock_orchestrator.get_system_health.side_effect = slow_health

        with (
            patch(
                "src.core.api.v1.als.als_health_router.get_orchestrator",
                return_value=mock_orchestrator,
            ),
            patch(
                "src.core.api.v1.als.als_health_router.ALS_ORCHESTRATOR_TIMEOUT_SECONDS",
                0.001,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_system_health(tenant_id=42)

        assert exc_info.value.status_code == 504
        assert exc_info.value.detail == "ALS health check timed out"

    @pytest.mark.asyncio
    async def test_broadcast_timeout_returns_504(self, mock_orchestrator, mock_user, mock_db):
        async def slow_broadcast(*_args, **_kwargs):
            await asyncio.sleep(0.05)

        mock_orchestrator.broadcast_to_all.side_effect = slow_broadcast

        with (
            patch(
                "src.core.api.v1.als.als_tasks_router.get_orchestrator",
                return_value=mock_orchestrator,
            ),
            patch(
                "src.core.api.v1.als.als_tasks_router.ALS_ORCHESTRATOR_TIMEOUT_SECONDS",
                0.001,
            ),
            patch(
                "src.core.api.v1.als.als_tasks_router.build_council",
                new=AsyncMock(return_value=AsyncMock()),
            ),
            patch(
                "src.core.api.v1.als.als_tasks_router.require_council_approval",
                new=AsyncMock(),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await broadcast_message(
                    message_type="system",
                    payload={"message": "hello"},
                    tenant_id=42,
                    db=mock_db,
                    current_user=mock_user,
                )

        assert exc_info.value.status_code == 504
        assert exc_info.value.detail == "ALS broadcast timed out"
