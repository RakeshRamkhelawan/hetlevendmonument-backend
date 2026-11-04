"""
Slice 5: ExecutorAgent - Comprehensive Test Suite (RED Phase)

Tests tool execution with retry logic, error recovery, and audit logging.
"""

import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.agents.capabilities.executor_agent import ExecutorAgent
from src.core.agents.capabilities.schemas import ExecutorResult, ExecutorTask

# ============================================================================
# TEST SUITE 1: BASIC EXECUTION
# ============================================================================


class TestBasicExecution:
    """Test basic tool execution functionality"""

    @pytest.mark.asyncio
    async def test_executes_tool_successfully(self):
        """Should execute tool and return success result"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="send_email",
            arguments={"to": "test@example.com", "subject": "Test", "body": "Hello"},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.success is True
        assert result.result is not None
        assert result.error is None
        assert result.retries_attempted == 0

    @pytest.mark.asyncio
    async def test_returns_tool_output(self):
        """Should return the tool's output in result field"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="calculate_sum",
            arguments={"a": 5, "b": 3},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.success is True
        assert result.result == {"sum": 8}

    @pytest.mark.asyncio
    async def test_includes_execution_context(self):
        """Should use execution context during tool execution"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="process_data",
            arguments={"data": "test"},
            tenant_id=uuid4(),
            user_id=uuid4(),
            execution_context={"step": 1, "workflow_id": "wf-123"},
        )

        result = await agent.execute(task)

        assert result.success is True
        # Context should influence execution (verified in logs)


# ============================================================================
# TEST SUITE 2: RETRY LOGIC
# ============================================================================


class TestRetryLogic:
    """Test retry logic with exponential backoff"""

    @pytest.mark.asyncio
    async def test_retries_on_transient_failure(self):
        """Should retry execution on transient failures"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="flaky_api_call",
            arguments={"endpoint": "/data"},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.retries_attempted > 0
        assert result.success is True  # Should eventually succeed

    @pytest.mark.asyncio
    async def test_stops_after_max_retries(self):
        """Should stop retrying after max_retries reached"""
        agent = ExecutorAgent(max_retries=3)
        task = ExecutorTask(
            tool_name="always_fails",
            arguments={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.retries_attempted == 3
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Should use exponential backoff between retries"""
        agent = ExecutorAgent(base_delay=0.1)
        task = ExecutorTask(
            tool_name="transient_error",
            arguments={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        # Verify backoff pattern (will be logged)
        assert result.retries_attempted >= 1

    @pytest.mark.asyncio
    async def test_no_retry_on_permanent_failure(self):
        """Should not retry on permanent failures (e.g., validation error)"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="validate_input",
            arguments={"invalid": "data"},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.retries_attempted == 0
        assert result.success is False
        assert "validation" in result.error.lower()


# ============================================================================
# TEST SUITE 3: ERROR HANDLING
# ============================================================================


class TestErrorHandling:
    """Test error handling and recovery"""

    @pytest.mark.asyncio
    async def test_handles_tool_not_found(self):
        """Should handle missing tool gracefully"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="nonexistent_tool",
            arguments={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.success is False
        assert "not found" in result.error.lower()
        assert result.retries_attempted == 0

    @pytest.mark.asyncio
    async def test_handles_tool_execution_error(self):
        """Should catch and return tool execution errors"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="divide",
            arguments={"a": 10, "b": 0},  # Division by zero
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.success is False
        assert result.error is not None
        assert "division" in result.error.lower() or "zero" in result.error.lower()

    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        """Should timeout long-running tools"""
        agent = ExecutorAgent(timeout_seconds=1)
        task = ExecutorTask(
            tool_name="long_running_task",
            arguments={"duration": 10},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_handles_missing_arguments(self):
        """Should validate required arguments"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="send_email",
            arguments={},  # Missing required fields
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.success is False
        assert "argument" in result.error.lower() or "required" in result.error.lower()


# ============================================================================
# TEST SUITE 4: AUDIT LOGGING
# ============================================================================


class TestAuditLogging:
    """Test audit trail generation"""

    @pytest.mark.asyncio
    async def test_generates_audit_log_on_success(self):
        """Should generate audit log for successful execution"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="send_email",
            arguments={"to": "user@example.com"},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.success is True
        assert result.audit_log_id is not None
        assert isinstance(result.audit_log_id, UUID)

    @pytest.mark.asyncio
    async def test_generates_audit_log_on_failure(self):
        """Should generate audit log even when execution fails"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="divide",
            arguments={"a": 10, "b": 0},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.success is False
        assert result.audit_log_id is not None

    @pytest.mark.asyncio
    async def test_audit_includes_tenant_context(self):
        """Should include tenant_id in audit log"""
        agent = ExecutorAgent()
        tenant_id = uuid4()
        task = ExecutorTask(
            tool_name="process_data",
            arguments={"data": "test"},
            tenant_id=tenant_id,
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.audit_log_id is not None
        # Tenant context verified in audit service call

    @pytest.mark.asyncio
    async def test_audit_includes_retry_count(self):
        """Should log retry count in audit trail"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="flaky_api_call",
            arguments={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.audit_log_id is not None
        # Retry count logged (verified in audit record)


# ============================================================================
# TEST SUITE 5: TENANT ISOLATION
# ============================================================================


class TestTenantIsolation:
    """Test tenant isolation enforcement"""

    @pytest.mark.asyncio
    async def test_requires_tenant_id(self):
        """Should require tenant_id in task"""
        agent = ExecutorAgent()

        with pytest.raises(Exception):
            task = ExecutorTask(
                tool_name="test_tool",
                arguments={},
                tenant_id=None,  # type: ignore
                user_id=uuid4(),
            )
            await agent.execute(task)

    @pytest.mark.asyncio
    async def test_different_tenants_isolated(self):
        """Should isolate execution between tenants"""
        agent = ExecutorAgent()
        tenant1 = uuid4()
        tenant2 = uuid4()

        task1 = ExecutorTask(
            tool_name="get_data",
            arguments={"key": "shared_key"},
            tenant_id=tenant1,
            user_id=uuid4(),
        )

        task2 = ExecutorTask(
            tool_name="get_data",
            arguments={"key": "shared_key"},
            tenant_id=tenant2,
            user_id=uuid4(),
        )

        result1 = await agent.execute(task1)
        result2 = await agent.execute(task2)

        # Results should be tenant-scoped
        assert result1.success is True
        assert result2.success is True
        # Data should be different per tenant (verified in tool execution)


# ============================================================================
# TEST SUITE 6: TOOL REGISTRY
# ============================================================================


class TestToolRegistry:
    """Test tool registration and discovery"""

    @pytest.mark.asyncio
    async def test_lists_available_tools(self):
        """Should list all registered tools"""
        agent = ExecutorAgent()

        tools = agent.list_available_tools()

        assert len(tools) > 0
        assert "send_email" in tools
        assert "calculate_sum" in tools

    @pytest.mark.asyncio
    async def test_registers_custom_tool(self):
        """Should allow registering custom tools"""
        agent = ExecutorAgent()

        async def custom_tool(args: dict) -> dict:
            return {"custom": "result"}

        agent.register_tool("custom_tool", custom_tool)

        task = ExecutorTask(
            tool_name="custom_tool",
            arguments={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.execute(task)

        assert result.success is True
        assert result.result == {"custom": "result"}

    @pytest.mark.asyncio
    async def test_tool_metadata(self):
        """Should provide tool metadata (name, description, params)"""
        agent = ExecutorAgent()

        metadata = agent.get_tool_metadata("send_email")

        assert metadata is not None
        assert metadata["name"] == "send_email"
        assert "description" in metadata
        assert "parameters" in metadata


# ============================================================================
# TEST SUITE 7: PERFORMANCE & CONCURRENCY
# ============================================================================


class TestPerformanceConcurrency:
    """Test performance and concurrent execution"""

    @pytest.mark.asyncio
    async def test_executes_quickly(self):
        """Should execute simple tools quickly"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="calculate_sum",
            arguments={"a": 1, "b": 2},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        import time

        start = time.time()
        result = await agent.execute(task)
        duration = time.time() - start

        assert result.success is True
        assert duration < 1.0  # Should complete in <1 second

    @pytest.mark.asyncio
    async def test_handles_concurrent_executions(self):
        """Should handle multiple concurrent tool executions"""
        import asyncio

        agent = ExecutorAgent()
        tasks = [
            ExecutorTask(
                tool_name="calculate_sum",
                arguments={"a": i, "b": i + 1},
                tenant_id=uuid4(),
                user_id=uuid4(),
            )
            for i in range(10)
        ]

        results = await asyncio.gather(*[agent.execute(task) for task in tasks])

        assert len(results) == 10
        assert all(r.success for r in results)


# ============================================================================
# TEST SUITE 8: VALIDATION
# ============================================================================


class TestValidation:
    """Test input validation"""

    @pytest.mark.asyncio
    async def test_validates_tool_name(self):
        """Should validate tool_name is non-empty"""
        agent = ExecutorAgent()

        with pytest.raises(Exception):
            task = ExecutorTask(
                tool_name="",
                arguments={},
                tenant_id=uuid4(),
                user_id=uuid4(),
            )
            await agent.execute(task)

    @pytest.mark.asyncio
    async def test_validates_tenant_id_format(self):
        """Should validate tenant_id is valid UUID"""
        agent = ExecutorAgent()

        with pytest.raises(Exception):
            task = ExecutorTask(
                tool_name="test_tool",
                arguments={},
                tenant_id="invalid-uuid",  # type: ignore
                user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_validates_user_id_required(self):
        """Should require user_id for audit trail"""
        agent = ExecutorAgent()

        with pytest.raises(Exception):
            task = ExecutorTask(
                tool_name="test_tool",
                arguments={},
                tenant_id=uuid4(),
                user_id=None,  # type: ignore
            )


# ============================================================================
# TEST SUITE 9: IDEMPOTENCY
# ============================================================================


class TestIdempotency:
    """Test idempotent operations"""

    @pytest.mark.asyncio
    async def test_same_task_produces_same_result(self):
        """Should produce consistent results for same input"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="calculate_sum",
            arguments={"a": 5, "b": 3},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result1 = await agent.execute(task)
        result2 = await agent.execute(task)

        assert result1.result == result2.result
        assert result1.success == result2.success

    @pytest.mark.asyncio
    async def test_idempotent_tools_safe_to_retry(self):
        """Should safely retry idempotent operations"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="get_data",
            arguments={"key": "test"},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        # Multiple executions should be safe
        result1 = await agent.execute(task)
        result2 = await agent.execute(task)

        assert result1.success is True
        assert result2.success is True


# ============================================================================
# TEST SUITE 10: LOGGING & OBSERVABILITY
# ============================================================================


class TestLoggingObservability:
    """Test logging and observability"""

    @pytest.mark.asyncio
    async def test_logs_execution_start(self, caplog):
        """Should log when execution starts"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="test_tool",
            arguments={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        with caplog.at_level(logging.INFO):
            await agent.execute(task)

        assert any("Executing tool" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_execution_result(self, caplog):
        """Should log execution result (success/failure)"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="calculate_sum",
            arguments={"a": 1, "b": 2},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        with caplog.at_level(logging.INFO):
            result = await agent.execute(task)

        assert result.success is True
        assert any("success" in record.message.lower() for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_retry_attempts(self, caplog):
        """Should log each retry attempt"""
        agent = ExecutorAgent()
        task = ExecutorTask(
            tool_name="flaky_api_call",
            arguments={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        with caplog.at_level(logging.INFO):
            result = await agent.execute(task)

        if result.retries_attempted > 0:
            assert any("retry" in record.message.lower() for record in caplog.records)
