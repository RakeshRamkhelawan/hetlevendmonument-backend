"""Tests for genuine NotImplementedError contract in BaseSupervisor.act()."""

from datetime import datetime, timezone
import pytest

from src.core.als.infrastructure.signal_bus import Signal, SignalTier
from src.core.als.supervisors.base_supervisor import BaseSupervisor
from src.core.als.supervisors.cva_supervisor import CVASupervisor
from src.core.als.supervisors.finance_supervisor import FinanceSupervisor
from src.core.als.supervisors.itsecurity_supervisor import ITSecuritySupervisor


@pytest.fixture
def sample_signal() -> Signal:
    return Signal(
        tenant_id=1,
        source_agent_id="waf_sensor",
        target_agent_ids=[],
        tier=SignalTier.REFLEX,
        payload={"threat": "SQL Injection", "severity": "critical"},
        timestamp=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_base_supervisor_act_raises_not_implemented_error() -> None:
    """BaseSupervisor.act() must raise NotImplementedError instead of returning fake success."""
    supervisor = BaseSupervisor(agent_id="test_sup", tenant_id=1, department="it_security")
    with pytest.raises(NotImplementedError) as exc_info:
        await supervisor.act("escalate_or_immediate_dispatch")
    assert "ADR-036" in str(exc_info.value)
    assert "no consumer wired" in str(exc_info.value)


@pytest.mark.asyncio
async def test_derived_supervisors_inherit_not_implemented_contract() -> None:
    """All domain supervisors must inherit honest contract without faking dispatch success."""
    supervisors = [
        ITSecuritySupervisor(agent_id="sec_sup", tenant_id=1),
        FinanceSupervisor(agent_id="fin_sup", tenant_id=1),
        CVASupervisor(agent_id="cva_sup", tenant_id=1),
    ]
    for sup in supervisors:
        with pytest.raises(NotImplementedError) as exc_info:
            await sup.act("escalate_or_immediate_dispatch")
        assert "no consumer wired" in str(exc_info.value)
