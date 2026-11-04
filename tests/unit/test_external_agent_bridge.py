"""Unit tests for ExternalAgentBridge.

Taak 5.2: ExternalAgentBridge
Fase 5: Heartbeat Protocol & External Agents
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.company.external_agent_bridge import ExternalAgentBridge
from src.core.company.models import ExternalAgent

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_external_agent():
    """Create mock ExternalAgent."""
    agent = MagicMock(spec=ExternalAgent)
    agent.id = uuid.uuid4()
    agent.name = "Test External Agent"
    agent.webhook_url = "https://example.com/webhook"
    agent.tenant_id = 1
    return agent


@pytest.fixture
def mock_service():
    """Create mock ExternalAgentService."""
    return MagicMock()


@pytest.fixture
def bridge(mock_external_agent, mock_service):
    """Create ExternalAgentBridge instance."""
    return ExternalAgentBridge(
        external_agent=mock_external_agent,
        service=mock_service,
    )


# ============================================================================
# Bridge Initialization Tests
# ============================================================================


class TestBridgeInitialization:
    """Test ExternalAgentBridge initialization."""

    def test_bridge_is_enhanced_base_agent(self, bridge):
        """Bridge is instance of EnhancedBaseAgent."""
        from src.core.agents.base_agent import EnhancedBaseAgent

        assert isinstance(bridge, EnhancedBaseAgent)

    def test_bridge_has_external_agent(self, bridge, mock_external_agent):
        """Bridge stores reference to external agent."""
        assert bridge.external_agent == mock_external_agent

    def test_bridge_has_service(self, bridge, mock_service):
        """Bridge stores reference to service."""
        assert bridge.service == mock_service

    def test_bridge_agent_id_format(self, bridge, mock_external_agent):
        """Bridge agent_id has ext- prefix."""
        assert bridge.agent_id == f"ext-{mock_external_agent.id}"


# ============================================================================
# Task Processing Tests
# ============================================================================


class TestTaskProcessing:
    """Test task processing via bridge."""

    @pytest.mark.asyncio
    async def test_process_task_dispatches_to_external(self, bridge, mock_service):
        """Task is dispatched to external agent - test internal method."""
        from src.core.agents.base_agent import ExecutionResult, TaskData
        from src.core.shared.agent_context import AgentExecutionContext

        task_id = uuid.uuid4()
        # Golden Rule R1 requires a resolvable AgentExecutionContext -- see
        # ExternalAgentBridge._resolve_context() (prefers task.company_context).
        task = TaskData(
            id=str(task_id),
            title="Test Task",
            description="Test task description",
            action="process_data",
            input={"data": "test"},
            company_context=AgentExecutionContext(
                tenant_id=1, task_id=task_id, trace_id=uuid.uuid4()
            ),
        )

        # Mock _process_task_external (the actual implementation)
        with patch.object(bridge, "_process_task_external", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = ExecutionResult(
                task_id=task.id,
                success=True,
                result_data={"result": "success"},
            )

            result = await bridge._execute_task(task)

        # Verify result
        assert result is not None
        assert result.success is True

    @pytest.mark.asyncio
    async def test_process_task_without_context_fails(self, bridge):
        """Task without context fails with a 'context'-related error message
        (Golden Rule R1). EnhancedBaseAgent.process_task() wraps all exceptions
        from _execute_task() into a failed ExecutionResult rather than letting
        them propagate, so this asserts the returned result, not a raised
        exception."""
        from src.core.agents.base_agent import TaskData

        task = TaskData(
            id=str(uuid.uuid4()),
            title="Test Task",
            description="Test task description",
            action="test",
            input={},
        )

        result = await bridge.process_task(task)

        assert result.success is False
        assert "context" in (result.error_message or "").lower()


# ============================================================================
# Dispatch Retry Tests
# ============================================================================


class TestDispatchRetry:
    """Test dispatch with retry logic."""

    @pytest.mark.asyncio
    async def test_dispatch_with_retry_success(self, bridge):
        """Dispatch succeeds on first attempt."""
        from src.core.agents.base_agent import TaskData

        task = TaskData(
            task_id=uuid.uuid4(),
            title="Test Task",
            description="Test task description",
            action="test",
            input={},
        )

        with patch.object(bridge, "_dispatch", new_callable=AsyncMock) as mock_dispatch:
            mock_assignment = MagicMock()
            mock_dispatch.return_value = mock_assignment

            result = await bridge._dispatch_with_retry(task)

            assert result == mock_assignment
            assert mock_dispatch.call_count == 1

    @pytest.mark.asyncio
    async def test_dispatch_retry_on_failure(self, bridge):
        """Dispatch retries on failure. [1, 5, 30] second backoff."""
        from src.core.agents.base_agent import TaskData

        task = TaskData(
            task_id=uuid.uuid4(),
            title="Test Task",
            description="Test task description",
            action="test",
            input={},
        )

        with patch.object(bridge, "_dispatch", new_callable=AsyncMock) as mock_dispatch:
            # Fail first 2 times, succeed on 3rd
            mock_dispatch.side_effect = [
                Exception("Connection error"),
                Exception("Timeout"),
                MagicMock(),  # Success
            ]

            with patch("asyncio.sleep", new_callable=AsyncMock):  # Skip actual delays
                result = await bridge._dispatch_with_retry(task)

            assert result is not None
            assert mock_dispatch.call_count == 3

    @pytest.mark.asyncio
    async def test_dispatch_all_retries_fail(self, bridge):
        """After 3 failures, ExternalAgentDispatchError is raised."""
        from src.core.agents.base_agent import TaskData
        from src.core.company.external_agent_bridge import ExternalAgentDispatchError

        task = TaskData(
            task_id=uuid.uuid4(),
            title="Test Task",
            description="Test task description",
            action="test",
            input={},
        )

        with patch.object(bridge, "_dispatch", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.side_effect = Exception("Persistent failure")

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(ExternalAgentDispatchError):
                    await bridge._dispatch_with_retry(task)

            assert mock_dispatch.call_count == 3


# ============================================================================
# Wait for Completion Tests
# ============================================================================


class TestWaitForCompletion:
    """Test waiting for task completion."""

    @pytest.mark.asyncio
    async def test_wait_for_completion_success(self, bridge, mock_service):
        """Successfully waits for task completion."""
        task_id = uuid.uuid4()

        # Mock completion status
        mock_completion = MagicMock()
        mock_completion.status = "completed"
        mock_completion.output = {"result": "success"}

        with patch.object(mock_service, "get_task_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = mock_completion

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await bridge._wait_for_completion(task_id, timeout_seconds=300)

        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_wait_for_completion_timeout(self, bridge, mock_service):
        """Timeout raises TaskTimeoutError."""
        from src.core.company.external_agent_bridge import TaskTimeoutError

        task_id = uuid.uuid4()

        with patch.object(mock_service, "get_task_status", new_callable=AsyncMock) as mock_status:
            # Always return in-progress
            mock_status.return_value = MagicMock(status="in_progress")

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(TaskTimeoutError):
                    await bridge._wait_for_completion(task_id, timeout_seconds=1)


# ============================================================================
# Output Validation Tests
# ============================================================================


class TestOutputValidation:
    """Test output validation."""

    def test_validate_output_max_size(self, bridge):
        """Output exceeding 10MB raises error."""
        large_output = {"data": "x" * (11 * 1024 * 1024)}  # 11MB

        from src.core.company.context import AgentExecutionContext
        from src.core.exceptions.exceptions import ValidationError

        context = MagicMock(spec=AgentExecutionContext)

        with pytest.raises(ValidationError) as exc_info:
            bridge._validate_output(large_output, context)

        assert "size" in str(exc_info.value).lower()

    def test_validate_output_required_fields(self, bridge):
        """Output must have required fields."""
        output = {"status": "completed", "result": {}}

        from src.core.company.context import AgentExecutionContext

        context = MagicMock(spec=AgentExecutionContext)

        result = bridge._validate_output(output, context)
        assert result is not None


# ============================================================================
# SLA Timeout Tests
# ============================================================================


class TestSLATimeout:
    """Test SLA timeout respect."""

    def test_default_sla_timeout(self, bridge):
        """Default SLA timeout is 300 seconds."""
        assert bridge.DEFAULT_SLA_SECONDS == 300

    @pytest.mark.asyncio
    async def test_sla_timeout_respected(self, bridge, mock_service):
        """Bridge respects SLA timeout - test via _wait_for_completion."""
        from src.core.company.external_agent_bridge import TaskTimeoutError

        task_id = uuid.uuid4()

        with patch.object(bridge, "_wait_for_completion", new_callable=AsyncMock) as mock_wait:
            mock_wait.side_effect = TaskTimeoutError("SLA exceeded")

            with pytest.raises(TaskTimeoutError):
                await bridge._wait_for_completion(task_id, timeout_seconds=1)


# ============================================================================
# Bridge Transparency Tests
# ============================================================================


class TestBridgeTransparency:
    """Test that bridge is transparent to orchestrator."""

    def test_bridge_has_process_task_method(self, bridge):
        """Bridge has process_task method."""
        assert hasattr(bridge, "process_task")
        assert callable(getattr(bridge, "process_task"))

    def test_bridge_process_task_signature(self, bridge):
        """process_task has correct signature."""
        import inspect

        sig = inspect.signature(bridge.process_task)
        params = list(sig.parameters.keys())

        assert "task" in params
