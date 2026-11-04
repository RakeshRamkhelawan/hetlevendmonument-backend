"""Tests for FinanceSupervisor implementation."""

import pytest

from src.core.als.supervisors.finance_supervisor import FinanceSupervisor
from src.core.exceptions import AuthError


class TestFinanceSupervisorHappyPath:
    """Happy path tests for FinanceSupervisor."""

    @pytest.fixture
    def supervisor(self):
        return FinanceSupervisor()

    @pytest.mark.asyncio
    async def test_supervisor_has_correct_id(self, supervisor):
        """Should have correct supervisor_id."""
        assert supervisor.supervisor_id == "finance.treasury.supervisor"

    @pytest.mark.asyncio
    async def test_supervisor_has_correct_domain(self, supervisor):
        """Should have correct domain."""
        assert supervisor.domain == "Finance & Treasury"

    @pytest.mark.asyncio
    async def test_supervisor_manages_5_agents(self, supervisor):
        """Should manage exactly 5 finance agents."""
        assert len(supervisor.managed_agents) == 5
        assert "finance.tax_compliance.001" in supervisor.managed_agents
        assert "finance.audit_compliance.001" in supervisor.managed_agents
        assert "finance.ar_ap.001" in supervisor.managed_agents
        assert "finance.forecasting.001" in supervisor.managed_agents
        assert "finance.investment.001" in supervisor.managed_agents

    @pytest.mark.asyncio
    async def test_decompose_tax_task(self, supervisor):
        """Should decompose tax task into subtasks."""
        task = {
            "type": "tax_filing",
            "jurisdiction": "NL",
            "quarter": "Q3",
            "tenant_id": "tenant_123",
        }

        subtasks = await supervisor.decompose_task(task)

        assert len(subtasks) >= 1
        assert any(st.agent_id == "finance.tax_compliance.001" for st in subtasks)

    @pytest.mark.asyncio
    async def test_decompose_audit_task(self, supervisor):
        """Should decompose audit task into subtasks."""
        task = {"type": "audit_review", "year": 2025, "tenant_id": "tenant_123"}

        subtasks = await supervisor.decompose_task(task)

        assert len(subtasks) >= 1
        assert any(st.agent_id == "finance.audit_compliance.001" for st in subtasks)

    @pytest.mark.asyncio
    async def test_delegate_to_single_agent(self, supervisor):
        """Should delegate to a single agent successfully."""
        subtasks = [
            {
                "agent_id": "finance.tax_compliance.001",
                "task": "calculate_vat",
                "params": {"amount": 1000},
            }
        ]

        result = await supervisor.delegate(subtasks, tenant_id="tenant_123")

        assert result["status"] == "completed"
        assert "results" in result
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_delegate_to_multiple_agents(self, supervisor):
        """Should delegate to multiple agents and aggregate results."""
        subtasks = [
            {"agent_id": "finance.tax_compliance.001", "task": "calculate_vat"},
            {"agent_id": "finance.audit_compliance.001", "task": "verify_records"},
        ]

        result = await supervisor.delegate(subtasks, tenant_id="tenant_123")

        assert result["status"] == "completed"
        assert "results" in result
        assert len(result["results"]) == 2


class TestFinanceSupervisorUnhappyPath:
    """Unhappy path tests for FinanceSupervisor."""

    @pytest.fixture
    def supervisor(self):
        return FinanceSupervisor()

    @pytest.mark.asyncio
    async def test_missing_tenant_id_raises_auth_error(self, supervisor):
        """Should raise AuthError when tenant_id is missing."""
        task = {"type": "tax_filing"}  # No tenant_id

        with pytest.raises(AuthError, match="tenant_id is required"):
            await supervisor.decompose_task(task)

    @pytest.mark.asyncio
    async def test_delegate_missing_tenant_id_raises_auth_error(self, supervisor):
        """Should raise AuthError when tenant_id is missing in delegate."""
        subtasks = [{"agent_id": "finance.tax_compliance.001", "task": "calculate_vat"}]

        with pytest.raises(AuthError, match="tenant_id is required"):
            await supervisor.delegate(subtasks, tenant_id=None)  # No tenant_id

    @pytest.mark.asyncio
    async def test_unknown_task_type_returns_empty_subtasks(self, supervisor):
        """Should return empty list for unknown task type."""
        task = {"type": "unknown_task", "tenant_id": "tenant_123"}

        subtasks = await supervisor.decompose_task(task)

        assert subtasks == []

    @pytest.mark.asyncio
    async def test_empty_subtasks_returns_early(self, supervisor):
        """Should handle empty subtasks gracefully."""
        result = await supervisor.delegate([], tenant_id="tenant_123")

        assert result["status"] == "completed"
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_handle_timeout_escalates_to_cva(self, supervisor):
        """Should escalate to CVA when agent times out."""
        task = {"agent_id": "offline_agent", "task": "process"}

        result = await supervisor.handle_timeout("offline_agent", task, tenant_id="tenant_123")

        assert result["status"] == "escalated"
        assert result["escalated_to"] == "cva.meta.supervisor"
