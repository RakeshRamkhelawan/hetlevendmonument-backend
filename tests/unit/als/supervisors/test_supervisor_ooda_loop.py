"""TDD unit tests for genuine OODA loop implementation in ALS Supervisors.

Ensures that BaseSupervisor and all domain supervisors execute a real
Observe-Orient-Decide-Act (OODA) cycle instead of returning empty dictionaries.
"""

from datetime import datetime, timezone
import pytest

from src.core.als.infrastructure.signal_bus import Signal, SignalTier
from src.core.als.supervisors.base_supervisor import BaseSupervisor
from src.core.als.supervisors.cva_supervisor import CVASupervisor
from src.core.als.supervisors.finance_supervisor import FinanceSupervisor
from src.core.als.supervisors.itsecurity_supervisor import ITSecuritySupervisor


@pytest.fixture
def sample_signal():
    return Signal(
        tenant_id=1,
        source_agent_id="waf_sensor",
        target_agent_ids=[],
        tier=SignalTier.REFLEX,
        payload={
            "threat": "SQL Injection attempt",
            "severity": "critical",
            "source_ip": "1.2.3.4",
            "signal_type": "security_alert",
        },
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def non_relevant_signal():
    return Signal(
        tenant_id=1,
        source_agent_id="payroll_bot",
        target_agent_ids=[],
        tier=SignalTier.COGNITIVE,
        payload={
            "employee_id": 101,
            "action": "bonus_payout",
            "signal_type": "hr_payroll_notice",
            "department": "hr",
        },
        timestamp=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_base_supervisor_ooda_cycle_genuine(sample_signal):
    """BaseSupervisor OODA loop extracts telemetry, evaluates urgency, and acts."""
    supervisor = BaseSupervisor(agent_id="test_sup_01", tenant_id=1, department="it_security")

    # 1. Observe
    obs = await supervisor.observe(sample_signal)
    assert obs["signal_type"] == "security_alert"
    assert obs["department"] == "it_security"
    assert "threat" in obs["payload"]

    # 2. Orient
    orientation = await supervisor.orient(obs)
    assert orientation["is_relevant"] is True
    assert orientation["urgency"] == "critical"
    assert orientation["actionable"] is True

    # 3. Decide
    decision = await supervisor.decide(orientation)
    assert decision == "escalate_or_immediate_dispatch"

    # 4. Act raises NotImplementedError honestly until consumers are wired
    with pytest.raises(NotImplementedError) as exc_info:
        await supervisor.act(decision)
    assert "no consumer wired" in str(exc_info.value)


@pytest.mark.asyncio
async def test_supervisor_ooda_ignores_irrelevant_signal(non_relevant_signal):
    """OODA loop correctly classifies and ignores signals for other departments."""
    supervisor = ITSecuritySupervisor(agent_id="itsec_sup", tenant_id=1)

    obs = await supervisor.observe(non_relevant_signal)
    orientation = await supervisor.orient(obs)
    assert orientation["is_relevant"] is False
    assert orientation["actionable"] is False

    decision = await supervisor.decide(orientation)
    assert decision == "ignore_irrelevant"

    result = await supervisor.act(decision)
    assert result.success is True
    assert result.result_data["status"] == "ignored"


@pytest.mark.asyncio
async def test_cva_meta_supervisor_handles_all_departments(sample_signal):
    """CVA meta supervisor considers all signals relevant and dispatches appropriately."""
    cva = CVASupervisor(agent_id="cva_ceo", tenant_id=1)

    obs = await cva.observe(sample_signal)
    orientation = await cva.orient(obs)
    assert orientation["is_relevant"] is True
    assert orientation["urgency"] == "critical"

    decision = await cva.decide(orientation)
    assert decision == "escalate_or_immediate_dispatch"

    with pytest.raises(NotImplementedError) as exc_info:
        await cva.act(decision)
    assert "no consumer wired" in str(exc_info.value)
