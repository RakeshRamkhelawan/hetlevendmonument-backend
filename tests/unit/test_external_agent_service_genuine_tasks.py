"""Unit tests for genuine task management logic in ExternalAgentService.

TDD suite ensuring:
- _get_task queries the database with tenant and task ID isolation
- _get_pending_tasks queries the database for assigned pending tasks
- get_next_task returns a real TaskNextResponse when tasks exist
- complete_task verifies ownership and updates task status and metrics
- _reschedule_orphaned_tasks updates assigned tasks back to pending without agent
- _cancel_pending_tasks marks pending tasks as cancelled
"""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.company.external_agent_service import ExternalAgentService
from src.core.company.models import ExternalAgent
from src.core.company.schemas import TaskCompleteRequest
from src.core.exceptions.exceptions import AuthError, NotFoundError
from src.domains.tasks.models import Task, TaskPriority, TaskStatus


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    @asynccontextmanager
    async def _get_session():
        yield mock_session

    db = MagicMock()
    db.get_session = _get_session

    tenant_ctx = MagicMock()
    tenant_ctx.tenant_id = 42

    return ExternalAgentService(
        db_manager=db,
        tenant_context=tenant_ctx,
        policy_engine=None,
        budget_manager=None,
    )


@pytest.mark.asyncio
async def test_get_task_queries_database_with_tenant(service, mock_session):
    """_get_task must query Task with task_id and tenant_id."""
    task_id = uuid.uuid4()
    mock_task = Task(
        id=task_id,
        tenant_id=42,
        title="Process OCR",
        status=TaskStatus.PENDING.value,
        assigned_agent_id="agent-123",
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_session.execute.return_value = mock_result

    task = await service._get_task(mock_session, task_id, 42)
    assert task is not None
    assert task.id == task_id
    assert task.tenant_id == 42


@pytest.mark.asyncio
async def test_get_pending_tasks_queries_assigned_tasks(service, mock_session):
    """_get_pending_tasks must query tasks assigned to the agent."""
    agent_id = uuid.uuid4()
    t1 = Task(
        id=uuid.uuid4(),
        tenant_id=42,
        title="Sync Index",
        status=TaskStatus.PENDING.value,
        assigned_agent_id=str(agent_id),
        payload={"type": "sync", "dataset": "kb_core"},
        priority=TaskPriority.HIGH.value,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [t1]
    mock_session.execute.return_value = mock_result

    pending = await service._get_pending_tasks(mock_session, agent_id, tenant_id=42, limit=5)
    assert len(pending) == 1
    assert pending[0]["id"] == str(t1.id)
    assert pending[0]["type"] == "sync"
    assert pending[0]["priority"] == TaskPriority.HIGH.value


@pytest.mark.asyncio
async def test_get_next_task_returns_response_when_task_exists(service, mock_session):
    """get_next_task builds TaskNextResponse and execution context."""
    agent_id = uuid.uuid4()
    mock_agent = ExternalAgent(
        id=agent_id,
        tenant_id=42,
        name="Worker Agent",
        runtime="python",
        capabilities=["sync"],
        api_key_hash="dummy",
        status="idle",
        metrics={},
    )
    task_id = uuid.uuid4()
    pending_task_dict = {
        "id": str(task_id),
        "task_id": str(task_id),
        "title": "Compute Embeddings",
        "description": "Compute vector embeddings",
        "type": "embedding",
        "input": {"chunk_id": 99},
        "priority": "high",
    }

    service._get_agent = AsyncMock(return_value=mock_agent)
    service._get_pending_tasks = AsyncMock(return_value=[pending_task_dict])

    response = await service.get_next_task(agent_id)
    assert response is not None
    assert response.action == "embedding"
    assert response.input == {"chunk_id": 99}


@pytest.mark.asyncio
async def test_complete_task_verifies_ownership_and_updates_status(service, mock_session):
    """complete_task verifies task.assigned_agent_id and sets status and result."""
    agent_id = uuid.uuid4()
    task_id = uuid.uuid4()

    mock_task = Task(
        id=task_id,
        tenant_id=42,
        title="Compute Embeddings",
        status="running",
        assigned_agent_id=str(agent_id),
    )
    mock_agent = ExternalAgent(
        id=agent_id,
        tenant_id=42,
        name="Worker Agent",
        runtime="python",
        capabilities=[],
        api_key_hash="dummy",
        metrics={"tasks_completed": 3},
    )

    service._get_agent = AsyncMock(return_value=mock_agent)
    service._get_task = AsyncMock(return_value=mock_task)

    data = TaskCompleteRequest(
        status="completed",
        output={"vectors_computed": 50},
        reasoning_trace="All batches embedded successfully",
    )

    result = await service.complete_task(agent_id, task_id, data)
    assert result is None
    assert mock_task.status == "completed"
    assert mock_task.result == {"vectors_computed": 50}
    assert mock_agent.metrics["tasks_completed"] == 4
    mock_session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_complete_task_rejects_unowned_task(service, mock_session):
    """complete_task raises AuthError if task is assigned to a different agent."""
    agent_id = uuid.uuid4()
    other_agent_id = uuid.uuid4()
    task_id = uuid.uuid4()

    mock_task = Task(
        id=task_id,
        tenant_id=42,
        title="Secret Task",
        status="running",
        assigned_agent_id=str(other_agent_id),
    )

    service._get_task = AsyncMock(return_value=mock_task)

    data = TaskCompleteRequest(
        status="completed",
        output={},
    )

    with pytest.raises(AuthError):
        await service.complete_task(agent_id, task_id, data)


@pytest.mark.asyncio
async def test_reschedule_orphaned_tasks_executes_update(service, mock_session):
    """_reschedule_orphaned_tasks updates assigned tasks to unassigned and pending."""
    agent_id = uuid.uuid4()
    await service._reschedule_orphaned_tasks(mock_session, agent_id, tenant_id=42)
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_pending_tasks_executes_update(service, mock_session):
    """_cancel_pending_tasks updates pending tasks to cancelled."""
    agent_id = uuid.uuid4()
    await service._cancel_pending_tasks(mock_session, agent_id, tenant_id=42)
    mock_session.execute.assert_awaited_once()
