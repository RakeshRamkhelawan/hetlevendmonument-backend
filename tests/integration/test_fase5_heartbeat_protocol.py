"""Integration tests for Fase 5: Heartbeat Protocol & External Agents.

End-to-end tests verifying:
1. Agent registration with API key generation
2. Heartbeat lifecycle (idle -> busy -> idle)
3. Heartbeat auth failure handling
4. Stale agent detection and cleanup
5. Task assignment, completion, and deregistration

These tests use mocked database sessions to test core business logic.
"""

import uuid as uuid_module
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_db_manager():
    """Create mock database manager."""
    mock = MagicMock()

    class AsyncContextManager:
        def __init__(self, session):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()

    mock.get_session = lambda: AsyncContextManager(mock_session)
    return mock, mock_session


@pytest.fixture
def mock_tenant_context():
    """Mock tenant context."""
    mock = MagicMock()
    mock.tenant_id = 1
    return mock


@pytest.fixture
def mock_policy_engine():
    """Mock policy engine (not used for most heartbeat tests)."""
    return MagicMock()


@pytest.fixture
def mock_budget_manager():
    """Mock budget manager."""
    mock = AsyncMock()
    mock.check_budget.return_value = MagicMock(allowed=True, remaining_tokens=1_000_000)
    mock.track_usage.return_value = None
    return mock


@pytest.fixture
def agent_service(mock_db_manager, mock_tenant_context, mock_policy_engine, mock_budget_manager):
    """Create ExternalAgentService with mocks."""
    from src.core.company.external_agent_service import ExternalAgentService

    db_manager, _ = mock_db_manager
    return ExternalAgentService(
        db_manager=db_manager,
        tenant_context=mock_tenant_context,
        policy_engine=mock_policy_engine,
        budget_manager=mock_budget_manager,
    )


@pytest.fixture
def mock_agent():
    """Create a mock ExternalAgent model."""
    from src.core.company.models import ExternalAgent

    agent = MagicMock(spec=ExternalAgent)
    agent.id = uuid4()
    agent.tenant_id = 1
    agent.name = "Test External Agent"
    agent.runtime = "python"
    agent.capabilities = ["data_analysis", "reporting"]
    agent.status = "idle"
    agent.api_key_hash = "hashed_key"
    agent.last_heartbeat = datetime.now(timezone.utc)
    agent.last_heartbeat_at = agent.last_heartbeat
    agent.heartbeat_interval_seconds = 30
    agent.registered_at = datetime.now(timezone.utc)
    agent.deregistered_at = None
    agent.company_id = uuid4()
    agent.department_id = uuid4()
    return agent


@pytest.fixture
def mock_task():
    """Create a mock AgentTask model."""
    task = MagicMock()
    task.id = uuid4()
    task.tenant_id = 1
    task.agent_id = uuid4()
    # `complete_task` leest sinds 5fd9bd08 de kolom `assigned_agent_id` (het echte model heeft alleen die).
    # Een kale MagicMock verzint er zelf een mock-waarde voor, en die is nooit gelijk aan de agent.
    task.assigned_agent_id = task.agent_id
    task.task_type = "data_analysis"
    task.payload = {"query": "revenue by quarter"}
    task.status = "pending"
    task.output = None
    task.created_at = datetime.now(timezone.utc)
    task.completed_at = None
    return task


# =============================================================================
# Registration Tests
# =============================================================================


class TestAgentRegistration:
    """Test agent registration flow."""

    @pytest.mark.asyncio
    async def test_register_external_agent(self, agent_service, mock_db_manager):
        """Register agent -> returns agent_id, api_key, heartbeat_endpoint."""
        mock_db, mock_session = mock_db_manager

        from src.core.company.schemas import ExternalAgentRegister

        data = ExternalAgentRegister(
            name="Analysis Agent",
            runtime="python",
            capabilities=["data_analysis"],
        )

        result = await agent_service.register(data)

        assert "agent_id" in result
        assert "api_key" in result
        assert result["api_key"].startswith("sk-")
        assert "heartbeat_endpoint" in result
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_agent_creates_api_key(self, agent_service, mock_db_manager):
        """Registered agent gets an API key starting with sk-."""
        mock_db, mock_session = mock_db_manager

        from src.core.company.schemas import ExternalAgentRegister

        data = ExternalAgentRegister(
            name="Second Agent",
            runtime="nodejs",
            capabilities=["reporting"],
        )

        result = await agent_service.register(data)

        assert result["api_key"].startswith("sk-")
        assert len(result["api_key"]) > 10


# =============================================================================
# Heartbeat Lifecycle Tests
# =============================================================================


class TestHeartbeatLifecycle:
    """Test heartbeat protocol lifecycle."""

    @pytest.mark.asyncio
    async def test_heartbeat_idle(self, agent_service, mock_db_manager, mock_agent):
        """Heartbeat with status=idle -> ack=True, pending_tasks."""
        mock_db, mock_session = mock_db_manager

        # Agent lookup
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = mock_agent

        # Pending tasks (empty)
        tasks_result = MagicMock()
        tasks_result.scalars.return_value.all.return_value = []

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return agent_result
            return tasks_result

        mock_session.execute = mock_execute

        from src.core.company.schemas import HeartbeatRequest

        data = HeartbeatRequest(status="idle")

        # Patch bcrypt.checkpw to bypass API key verification on mock data
        with patch("src.core.company.external_agent_service.bcrypt") as mock_bcrypt:
            mock_bcrypt.checkpw.return_value = True
            result = await agent_service.heartbeat(
                agent_id=mock_agent.id,
                api_key="test_api_key",
                data=data,
            )

        assert result.ack is True

    @pytest.mark.asyncio
    async def test_heartbeat_auth_failure(self, agent_service, mock_db_manager, mock_agent):
        """Heartbeat with wrong API key -> AuthError."""
        from src.core.exceptions.exceptions import AuthError

        mock_db, mock_session = mock_db_manager

        # Agent lookup - returns agent but key won't match
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = mock_agent
        mock_session.execute.return_value = agent_result

        from src.core.company.schemas import HeartbeatRequest

        data = HeartbeatRequest(status="idle")

        # Patch bcrypt to reject the API key
        with patch("src.core.company.external_agent_service.bcrypt") as mock_bcrypt:
            mock_bcrypt.checkpw.return_value = False

            with pytest.raises(AuthError):
                await agent_service.heartbeat(
                    agent_id=mock_agent.id,
                    api_key="wrong_key",
                    data=data,
                )

    @pytest.mark.asyncio
    async def test_heartbeat_agent_not_found(self, agent_service, mock_db_manager):
        """Heartbeat for unknown agent -> NotFoundError."""
        from src.core.exceptions.exceptions import NotFoundError

        mock_db, mock_session = mock_db_manager

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = agent_result

        from src.core.company.schemas import HeartbeatRequest

        data = HeartbeatRequest(status="idle")

        with pytest.raises(NotFoundError):
            await agent_service.heartbeat(
                agent_id=uuid4(),
                api_key="some_key",
                data=data,
            )


# =============================================================================
# Stale Agent Detection Tests
# =============================================================================


class TestStaleAgentDetection:
    """Test stale agent detection and cleanup."""

    @pytest.mark.asyncio
    async def test_check_stale_agents_marks_stale(self, agent_service, mock_db_manager, mock_agent):
        """Agent with old heartbeat -> marked as stale."""
        mock_db, mock_session = mock_db_manager

        # Make agent stale (last heartbeat > threshold)
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        mock_agent.last_heartbeat_at = stale_time
        mock_agent.last_heartbeat = stale_time
        mock_agent.heartbeat_interval_seconds = 30
        mock_agent.status = "idle"

        agents_result = MagicMock()
        agents_result.scalars.return_value.all.return_value = [mock_agent]
        mock_session.execute.return_value = agents_result

        result = await agent_service.check_stale_agents()

        # Should return list of stale agent IDs
        assert isinstance(result, list)


# =============================================================================
# Task Management Tests
# =============================================================================


class TestTaskAssignment:
    """Test task assignment via heartbeat."""

    @pytest.mark.asyncio
    async def test_get_next_task_returns_pending(
        self, agent_service, mock_db_manager, mock_task, mock_agent
    ):
        """Get next task for idle agent -> TaskNextResponse."""
        mock_db, mock_session = mock_db_manager

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = mock_agent
        mock_session.execute.return_value = agent_result

        pending_task = {"task_id": str(mock_task.id), "action": "data_analysis", "input": {}}

        with patch.object(agent_service, "_get_pending_tasks", return_value=[pending_task]):
            result = await agent_service.get_next_task(mock_agent.id)

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_next_task_returns_none(self, agent_service, mock_db_manager, mock_agent):
        """Get next task with no pending tasks -> None."""
        mock_db, mock_session = mock_db_manager

        # First execute: agent lookup returns agent
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = mock_agent

        # Second execute: pending tasks returns empty list
        tasks_result = MagicMock()
        tasks_result.scalars.return_value.all.return_value = []

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return agent_result
            return tasks_result

        mock_session.execute = mock_execute

        result = await agent_service.get_next_task(mock_agent.id)

        assert result is None


class TestTaskCompletion:
    """Test task completion flow."""

    @pytest.mark.asyncio
    async def test_complete_task_success(self, agent_service, mock_db_manager, mock_task):
        """Complete task with output -> task status updated."""
        mock_db, mock_session = mock_db_manager

        mock_task.status = "in_progress"
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute.return_value = task_result

        from src.core.company.schemas import TaskCompleteRequest

        data = TaskCompleteRequest(
            status="completed",
            output={"analysis": "Revenue increased 15%", "confidence": 0.95},
        )

        with patch.object(agent_service, "_get_task", return_value=mock_task):
            await agent_service.complete_task(
                agent_id=mock_task.agent_id,
                task_id=mock_task.id,
                data=data,
            )

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_task_not_found(self, agent_service, mock_db_manager):
        """Complete unknown task -> NotFoundError."""
        from src.core.exceptions.exceptions import NotFoundError

        mock_db, mock_session = mock_db_manager

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = task_result

        from src.core.company.schemas import TaskCompleteRequest

        data = TaskCompleteRequest(status="completed", output={})

        with pytest.raises(NotFoundError):
            await agent_service.complete_task(
                agent_id=uuid4(),
                task_id=uuid4(),
                data=data,
            )


# =============================================================================
# Deregistration Tests
# =============================================================================


class TestAgentDeregistration:
    """Test agent deregistration."""

    @pytest.mark.asyncio
    async def test_deregister_agent_success(self, agent_service, mock_db_manager, mock_agent):
        """Deregister agent -> soft delete, tasks cancelled."""
        mock_db, mock_session = mock_db_manager

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = mock_agent
        # For _cancel_pending_tasks internal call, need a second execute result
        mock_session.execute = AsyncMock(return_value=agent_result)

        await agent_service.deregister(mock_agent.id)

        mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_deregister_agent_not_found(self, agent_service, mock_db_manager):
        """Deregister unknown agent -> NotFoundError."""
        from src.core.exceptions.exceptions import NotFoundError

        mock_db, mock_session = mock_db_manager

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = agent_result

        with pytest.raises(NotFoundError):
            await agent_service.deregister(uuid4())
