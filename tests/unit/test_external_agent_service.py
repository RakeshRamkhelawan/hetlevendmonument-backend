"""Unit tests for ExternalAgentService.

Taak 5.1: ExternalAgentService
Fase 5: Heartbeat Protocol & External Agents
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.core.company.external_agent_service import ExternalAgentService
from src.core.company.schemas import ExternalAgentRegister, HeartbeatRequest, TaskCompleteRequest

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db_manager():
    """Create mock DatabaseManager."""
    return MagicMock()


@pytest.fixture
def mock_tenant_context():
    """Create mock TenantContext."""
    context = MagicMock()
    context.tenant_id = 1
    return context


@pytest.fixture
def mock_policy_engine():
    """Create mock PolicyEngine."""
    return MagicMock()


@pytest.fixture
def mock_budget_manager():
    """Create mock BudgetManager."""
    return MagicMock()


@pytest.fixture
def service(mock_db_manager, mock_tenant_context, mock_policy_engine, mock_budget_manager):
    """Create ExternalAgentService instance with mocks."""
    return ExternalAgentService(
        db_manager=mock_db_manager,
        tenant_context=mock_tenant_context,
        policy_engine=mock_policy_engine,
        budget_manager=mock_budget_manager,
    )


# ============================================================================
# Registration Tests
# ============================================================================


class TestAgentRegistration:
    """Test agent registration."""

    @pytest.mark.asyncio
    async def test_register_agent(self, service, mock_db_manager):
        """Register creates agent with API key."""
        # Mock session context manager properly
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_db_manager.get_session.return_value = mock_context

        data = ExternalAgentRegister(
            name="Test Agent",
            runtime="python",
            capabilities=["data_processing", "api_calls"],
            heartbeat_interval_seconds=30,
            webhook_url="https://example.com/webhook",
        )

        result = await service.register(data)

        # Verify result structure
        assert "agent_id" in result
        assert "api_key" in result
        assert "heartbeat_endpoint" in result

        # Verify API key format
        assert result["api_key"].startswith("sk-")
        assert len(result["api_key"]) > 20

    @pytest.mark.asyncio
    async def test_register_agent_without_webhook(self, service, mock_db_manager):
        """Register works without webhook URL."""
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_db_manager.get_session.return_value = mock_context

        data = ExternalAgentRegister(
            name="Minimal Agent",
            runtime="docker",
            capabilities=["task_execution"],
        )

        result = await service.register(data)

        assert "agent_id" in result
        assert "api_key" in result


# ============================================================================
# API Key Security Tests
# ============================================================================


class TestAPIKeySecurity:
    """Test API key security."""

    def test_api_key_format(self):
        """Generated API keys have correct format."""
        api_key = ExternalAgentService._generate_api_key()

        assert api_key.startswith("sk-")
        assert len(api_key) > 20
        # Should be alphanumeric with underscores
        assert api_key.replace("_", "").replace("-", "").isalnum()

    def test_api_key_uniqueness(self):
        """Generated API keys are unique."""
        keys = [ExternalAgentService._generate_api_key() for _ in range(10)]
        assert len(set(keys)) == 10  # All unique


# ============================================================================
# Service Configuration Tests
# ============================================================================


class TestServiceConfiguration:
    """Test service configuration and constants."""

    def test_stale_multiplier_constant(self):
        """Stale multiplier is configured."""
        assert ExternalAgentService.STALE_MULTIPLIER == 2

    def test_dead_misses_constant(self):
        """Dead misses threshold is configured."""
        assert ExternalAgentService.DEAD_MISSES == 3

    def test_max_output_size_constant(self):
        """Max output size is 10MB."""
        assert ExternalAgentService.MAX_OUTPUT_SIZE == 10 * 1024 * 1024


# ============================================================================
# Heartbeat Schema Tests
# ============================================================================


class TestHeartbeatSchemas:
    """Test heartbeat request/response schemas."""

    def test_heartbeat_request_creation(self):
        """Can create HeartbeatRequest."""
        req = HeartbeatRequest(
            status="idle",
            current_task_id=None,
            progress=0.5,
            metrics={"cpu": 0.5, "memory": 0.3},
        )

        assert req.status == "idle"
        assert req.progress == 0.5
        assert req.metrics["cpu"] == 0.5

    def test_heartbeat_request_valid_statuses(self):
        """Heartbeat accepts valid statuses."""
        for status in ["idle", "busy", "error"]:
            req = HeartbeatRequest(status=status)
            assert req.status == status


# ============================================================================
# Task Complete Schema Tests
# ============================================================================


class TestTaskCompleteSchemas:
    """Test task complete request schema."""

    def test_task_complete_request_creation(self):
        """Can create TaskCompleteRequest."""
        req = TaskCompleteRequest(
            status="completed",
            output={"result": "success", "data": [1, 2, 3]},
            reasoning_trace="Processed successfully",
        )

        assert req.status == "completed"
        assert req.output["result"] == "success"

    def test_task_complete_failed_status(self):
        """Can create failed task completion."""
        req = TaskCompleteRequest(
            status="failed",
            output={"error": "Timeout"},
            reasoning_trace="Task timed out after 30s",
        )

        assert req.status == "failed"


# ============================================================================
# External Agent Model Tests
# ============================================================================


class TestExternalAgentModel:
    """Test ExternalAgent model."""

    def test_agent_lifecycle_states(self):
        """Agent has correct lifecycle states."""
        from src.core.company.models import ExternalAgentStatus

        states = [
            ExternalAgentStatus.REGISTERED,
            ExternalAgentStatus.ACTIVE,
            ExternalAgentStatus.BUSY,
            ExternalAgentStatus.STALE,
            ExternalAgentStatus.DEAD,
        ]

        assert len(states) == 5
        assert ExternalAgentStatus.REGISTERED == "registered"
        assert ExternalAgentStatus.ACTIVE == "active"
        assert ExternalAgentStatus.BUSY == "busy"
        assert ExternalAgentStatus.STALE == "stale"
        assert ExternalAgentStatus.DEAD == "dead"

    def test_agent_capabilities_list(self):
        """Agent capabilities stored as list."""
        from src.core.company.models import ExternalAgent

        agent = ExternalAgent(
            id=uuid.uuid4(),
            tenant_id=1,
            name="Test Agent",
            runtime="python",
            capabilities=["data_processing", "api_calls"],
            api_key_hash="hash",
        )

        assert "data_processing" in agent.capabilities
        assert "api_calls" in agent.capabilities


# ============================================================================
# Service Method Existence Tests
# ============================================================================


class TestServiceMethods:
    """Test that service has required methods."""

    def test_service_has_register_method(self, service):
        """Service has register method."""
        assert hasattr(service, "register")
        assert callable(getattr(service, "register"))

    def test_service_has_heartbeat_method(self, service):
        """Service has heartbeat method."""
        assert hasattr(service, "heartbeat")
        assert callable(getattr(service, "heartbeat"))

    def test_service_has_get_next_task_method(self, service):
        """Service has get_next_task method."""
        assert hasattr(service, "get_next_task")
        assert callable(getattr(service, "get_next_task"))

    def test_service_has_complete_task_method(self, service):
        """Service has complete_task method."""
        assert hasattr(service, "complete_task")
        assert callable(getattr(service, "complete_task"))

    def test_service_has_check_stale_agents_method(self, service):
        """Service has check_stale_agents method."""
        assert hasattr(service, "check_stale_agents")
        assert callable(getattr(service, "check_stale_agents"))

    def test_service_has_list_agents_method(self, service):
        """Service has list_agents method."""
        assert hasattr(service, "list_agents")
        assert callable(getattr(service, "list_agents"))

    def test_service_has_deregister_method(self, service):
        """Service has deregister method."""
        assert hasattr(service, "deregister")
        assert callable(getattr(service, "deregister"))


# ============================================================================
# Tenant Isolation Tests
# ============================================================================


class TestTenantIsolation:
    """Test multi-tenant isolation in service."""

    def test_service_requires_tenant_context(self, service):
        """Service requires tenant context."""
        assert service.tenant_context is not None
        assert service.tenant_context.tenant_id == 1

    def test_db_manager_isolation(self, service):
        """Service uses db_manager for tenant isolation."""
        assert service.db_manager is not None
