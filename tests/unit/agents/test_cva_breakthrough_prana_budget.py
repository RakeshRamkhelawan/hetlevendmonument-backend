"""ADR-036 OP-12 (addendum SS8.2, Fix 4, 2026-08-26): CVAAutonomousTrigger controleert en
belast het Prana-budget van de tenant rond een breakthrough-sessie.

Voor deze fix bestond er geen enkele budgetcontrole -- een breakthrough-sessie kon
onbeperkt draaien zonder ooit een tenant se Prana-budget te raadplegen of te belasten.

Mockt `_check_prana_budget()`/`_charge_prana_for_breakthrough()` zelf (i.p.v. diep in
`PranaGuard` te patchen, zelfde bewezen patroon als
`test_cva_breakthrough_logs_to_audit_chain.py` voor `_write_breakthrough_audit_log()`) --
zo blijft dit een pure unit-test van CVAAutonomousTrigger's EIGEN besluitvorming (roept
het de juiste methode aan, met de juiste tenant_id, op het juiste moment), los van
PranaGuard's eigen, apart geteste gedrag.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from src.core.agents.cva_autonomous_trigger import CVAAutonomousTrigger, TriggerEvent
from src.core.governance.prana_guard import InsufficientPranaError
from src.core.types import TriggerType


class _RecordingOversightGate:
    def __init__(self) -> None:
        self._result = MagicMock()
        self._result.allowed = True
        self._result.requires_human_approval = False
        self._result.reason = "ok"

    async def check(self, **_kwargs: Any) -> Any:
        return self._result


def _trigger_event(tenant_id: int | None = None) -> TriggerEvent:
    return TriggerEvent(
        trigger_type=TriggerType.MANUAL,
        priority=1,
        trigger_data={},
        timestamp=datetime.now(timezone.utc),
        tenant_id=tenant_id,
    )


def _build_agent() -> CVAAutonomousTrigger:
    agent = CVAAutonomousTrigger(oversight_gate=_RecordingOversightGate())  # type: ignore[arg-type]
    agent._log_to_sandbox = MagicMock()  # type: ignore[method-assign]
    agent._write_breakthrough_audit_log = AsyncMock()  # type: ignore[method-assign]
    agent._check_prana_budget = AsyncMock()  # type: ignore[method-assign]
    agent._charge_prana_for_breakthrough = AsyncMock()  # type: ignore[method-assign]
    return agent


def test_check_budget_is_called_with_the_resolved_tenant() -> None:
    agent = _build_agent()
    agent._run_cva_breakthrough = MagicMock(return_value={"success": False})  # type: ignore[method-assign]

    agent._execute_breakthrough_session(_trigger_event(tenant_id=7))

    agent._check_prana_budget.assert_awaited_once_with(7)  # type: ignore[attr-defined]


def test_insufficient_prana_blocks_execution() -> None:
    """Een uitgeputte Prana-budget moet de breakthrough-sessie fail-closed blokkeren,
    net als een governance-weigering."""
    agent = _build_agent()
    agent._run_cva_breakthrough = MagicMock()  # type: ignore[method-assign]
    agent._check_prana_budget = AsyncMock(  # type: ignore[method-assign]
        side_effect=InsufficientPranaError("Tenant 7 has insufficient Prana budget.")
    )

    agent._execute_breakthrough_session(_trigger_event(tenant_id=7))

    agent._run_cva_breakthrough.assert_not_called()  # type: ignore[attr-defined]


def test_no_budget_check_without_a_resolved_tenant() -> None:
    """Saas-modus zonder tenant: geen tenant om te belasten, dus geen check-aanroep
    (het fail-closed APPROVAL_REQUIRED-pad elders blijft daar de begrenzing)."""
    agent = _build_agent()
    agent._run_cva_breakthrough = MagicMock(return_value={"success": False})  # type: ignore[method-assign]

    agent._execute_breakthrough_session(_trigger_event(tenant_id=None))

    agent._check_prana_budget.assert_not_awaited()  # type: ignore[attr-defined]


def test_successful_breakthrough_charges_prana() -> None:
    agent = _build_agent()
    agent._run_cva_breakthrough = MagicMock(  # type: ignore[method-assign]
        return_value={"success": True, "execution_time": 1, "innovation_title": "x"}
    )
    agent._handle_breakthrough_file_operations = MagicMock()  # type: ignore[method-assign]

    agent._execute_breakthrough_session(_trigger_event(tenant_id=7))

    agent._charge_prana_for_breakthrough.assert_awaited_once_with(7)  # type: ignore[attr-defined]


def test_failed_breakthrough_does_not_charge_prana() -> None:
    agent = _build_agent()
    agent._run_cva_breakthrough = MagicMock(return_value={"success": False})  # type: ignore[method-assign]

    agent._execute_breakthrough_session(_trigger_event(tenant_id=7))

    agent._charge_prana_for_breakthrough.assert_not_awaited()  # type: ignore[attr-defined]


def test_charge_prana_failure_does_not_raise() -> None:
    """best_effort-garantie: een afrekenfout NA een succesvolle sessie mag niet naar
    buiten lekken -- de actie heeft al plaatsgevonden."""
    agent = _build_agent()
    agent._run_cva_breakthrough = MagicMock(  # type: ignore[method-assign]
        return_value={"success": True, "execution_time": 1, "innovation_title": "x"}
    )
    agent._handle_breakthrough_file_operations = MagicMock()  # type: ignore[method-assign]
    agent._charge_prana_for_breakthrough = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("db onbereikbaar")
    )

    # Mag geen exception naar buiten laten lekken.
    agent._execute_breakthrough_session(_trigger_event(tenant_id=7))

    agent._handle_breakthrough_file_operations.assert_called_once()  # type: ignore[attr-defined]
