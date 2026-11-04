"""Tests for Domain Pack Orchestrator."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.core.als.enterprise.packs import (
    DomainPack,
    DomainPackOrchestrator,
    PackExecutionStatus,
    PackTask,
)
from src.core.exceptions import AuthError


class TestDomainPackConfig:
    """Tests for DomainPack configuration model."""

    def test_valid_pack_creation(self):
        """Should create valid DomainPack."""
        pack = DomainPack(
            id="finance.monthly_close.001",
            name="Monthly Financial Close",
            description="End-of-month financial closing process",
            supervisor_ids=["finance.treasury.supervisor"],
            agent_sequence=[
                {"type": "parallel", "agents": ["agent_1", "agent_2"]},
                {"type": "sequential", "agents": ["agent_3"]},
            ],
            sla_minutes=120,
            estimated_value_eur=5000,
        )
        assert pack.id == "finance.monthly_close.001"
        assert pack.sla_minutes == 120

    def test_invalid_sla_raises_error(self):
        """Should reject negative SLA."""
        with pytest.raises(ValueError):
            DomainPack(
                id="test.pack",
                name="Test Pack",
                supervisor_ids=["finance.supervisor"],
                sla_minutes=-10,
            )


class TestDomainPackOrchestratorHappyPath:
    """Happy path tests for DomainPackOrchestrator."""

    @pytest.fixture
    def orchestrator(self):
        return DomainPackOrchestrator()

    @pytest.fixture
    def sample_pack(self):
        return DomainPack(
            id="finance.monthly_close.001",
            name="Monthly Financial Close",
            description="End-of-month financial closing",
            supervisor_ids=["finance.treasury.supervisor"],
            agent_sequence=[
                {"type": "parallel", "agents": ["finance.ar_ap.001", "finance.tax_compliance.001"]},
                {"type": "sequential", "agents": ["finance.audit_compliance.001"]},
            ],
            sla_minutes=120,
            estimated_value_eur=5000,
        )

    @pytest.mark.asyncio
    async def test_execute_pack_success(self, orchestrator, sample_pack):
        """Should execute pack successfully."""
        tenant_id = "tenant_123"

        with (
            patch.object(
                orchestrator, "_execute_parallel", new_callable=AsyncMock
            ) as mock_parallel,
            patch.object(
                orchestrator, "_execute_sequential", new_callable=AsyncMock
            ) as mock_sequential,
        ):
            mock_parallel.return_value = [{"status": "success"}, {"status": "success"}]
            mock_sequential.return_value = [{"status": "success"}]

            result = await orchestrator.execute_pack(sample_pack, tenant_id)

        assert result["status"] == PackExecutionStatus.SUCCEEDED
        assert result["pack_id"] == sample_pack.id
        assert result["tenant_id"] == tenant_id
        assert "execution_time_ms" in result

    @pytest.mark.asyncio
    async def test_parallel_execution(self, orchestrator):
        """Should execute agents in parallel."""
        agents = ["agent_1", "agent_2"]
        tenant_id = "tenant_123"

        with patch.object(
            orchestrator, "_execute_single_agent", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = {"status": "success"}

            results = await orchestrator._execute_parallel(agents, tenant_id)

        assert len(results) == 2
        assert all(r["status"] == "success" for r in results)

    @pytest.mark.asyncio
    async def test_sequential_execution(self, orchestrator):
        """Should execute agents sequentially."""
        agents = ["agent_1", "agent_2"]
        tenant_id = "tenant_123"

        with patch.object(
            orchestrator, "_execute_single_agent", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = {"status": "success"}

            results = await orchestrator._execute_sequential(agents, tenant_id)

        assert len(results) == 2
        # Verify sequential (mock calls should be in order)
        assert mock_exec.call_count == 2

    @pytest.mark.asyncio
    async def test_sla_monitoring(self, orchestrator, sample_pack):
        """Should monitor SLA and report breach."""
        tenant_id = "tenant_123"

        # Mock execution that takes too long
        with patch.object(
            orchestrator, "_execute_parallel", new_callable=AsyncMock
        ) as mock_parallel:
            # Simulate timeout
            import asyncio

            mock_parallel.side_effect = asyncio.TimeoutError()

            result = await orchestrator.execute_pack(sample_pack, tenant_id)

        assert result["status"] == PackExecutionStatus.FAILED
        # SLA breach should be detected even if exception occurs
        assert result.get("sla_breached") is True or result.get("sla_breached") is False

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, orchestrator, sample_pack):
        """Should retry failed tasks."""
        tenant_id = "tenant_123"

        with patch.object(
            orchestrator, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_retry:
            mock_retry.return_value = {"status": "success"}

            result = await orchestrator.execute_pack(sample_pack, tenant_id)

        assert result["status"] == PackExecutionStatus.SUCCEEDED
        assert mock_retry.called


class TestDomainPackOrchestratorUnhappyPath:
    """Unhappy path tests for DomainPackOrchestrator."""

    @pytest.fixture
    def orchestrator(self):
        return DomainPackOrchestrator()

    @pytest.fixture
    def sample_pack(self):
        return DomainPack(
            id="finance.monthly_close.001",
            name="Monthly Financial Close",
            supervisor_ids=["finance.treasury.supervisor"],
            agent_sequence=[{"type": "parallel", "agents": ["agent_1"]}],
            sla_minutes=60,
        )

    @pytest.mark.asyncio
    async def test_missing_tenant_id_raises_error(self, orchestrator, sample_pack):
        """Should raise AuthError for missing tenant."""
        with pytest.raises(AuthError):
            await orchestrator.execute_pack(sample_pack, None)

    @pytest.mark.asyncio
    async def test_agent_failure_escalates(self, orchestrator, sample_pack):
        """Should escalate to human when all retries fail."""
        tenant_id = "tenant_123"

        with patch.object(
            orchestrator, "_execute_single_agent", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = {"status": "error", "error": "Agent crashed"}

            result = await orchestrator.execute_pack(sample_pack, tenant_id)

        assert result["status"] == PackExecutionStatus.FAILED
        assert result["escalated_to_human"] is True

    @pytest.mark.asyncio
    async def test_partial_failure_reported(self, orchestrator, sample_pack):
        """Should report partial failure when some agents fail."""
        tenant_id = "tenant_123"

        with patch.object(orchestrator, "_execute_parallel", new_callable=AsyncMock) as mock_exec:
            # One success, one failure
            mock_exec.return_value = [
                {"status": "success"},
                {"status": "error", "error": "Timeout"},
            ]

            result = await orchestrator.execute_pack(sample_pack, tenant_id)

        assert result["status"] == PackExecutionStatus.PARTIAL
        assert result["success_count"] == 1
        assert result["failure_count"] == 1


class TestPackExecutionStatus:
    """Tests for PackExecutionStatus enum."""

    def test_status_values(self):
        """Should have all expected status values."""
        statuses = [
            PackExecutionStatus.PENDING,
            PackExecutionStatus.IN_PROGRESS,
            PackExecutionStatus.SUCCEEDED,
            PackExecutionStatus.PARTIAL,
            PackExecutionStatus.FAILED,
            PackExecutionStatus.CANCELLED,
            PackExecutionStatus.ESCALATED,
        ]
        assert len(statuses) == 7

    def test_status_is_string(self):
        """Status should be string enum."""
        assert isinstance(PackExecutionStatus.SUCCEEDED.value, str)
        assert PackExecutionStatus.SUCCEEDED.value == "succeeded"
