"""ADR-036 OP-12 (addendum SS8.1, 2026-08-26): tenant_id-resolutie voor
CVAAutonomousTrigger._execute_breakthrough_session().

Voor deze fix gaf oversight_gate.check() nooit een tenant_id mee (het argument
ontbrak simpelweg in de aanroep). Deze test bewijst het GEDRAG: welke tenant_id
oversight_gate.check() daadwerkelijk ontvangt, per DEPLOYMENT_MODE, niet alleen
of de aanroep uberhaupt plaatsvindt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.agents.cva_autonomous_trigger import CVAAutonomousTrigger, TriggerEvent
from src.core.types import TriggerType


class _RecordingOversightGate:
    """Echte, minimale gate-dubbel die de tenant_id-kwarg vastlegt (geen kale
    MagicMock zonder spec, ADR-036 OP-147-les)."""

    def __init__(self) -> None:
        self.received_tenant_id: int | None | object = "NOT_CALLED"
        self._result = MagicMock()
        self._result.allowed = True
        self._result.requires_human_approval = False
        self._result.reason = "ok"

    async def check(self, **kwargs: Any) -> Any:
        self.received_tenant_id = kwargs.get("tenant_id", "NOT_PASSED")
        return self._result


def _trigger_event(tenant_id: int | None = None) -> TriggerEvent:
    return TriggerEvent(
        trigger_type=TriggerType.MANUAL,
        priority=1,
        trigger_data={},
        timestamp=datetime.now(timezone.utc),
        tenant_id=tenant_id,
    )


def _build_agent(gate: _RecordingOversightGate) -> CVAAutonomousTrigger:
    agent = CVAAutonomousTrigger(oversight_gate=gate)  # type: ignore[arg-type]
    agent._log_to_sandbox = MagicMock()  # type: ignore[method-assign]
    agent._run_cva_breakthrough = MagicMock()  # type: ignore[method-assign]
    # ADR-036 OP-12 Fix 3: het echte pad probeert een echte DB-sessie te openen
    # (container.session_factory()) -- niet relevant voor deze tenant-resolutietests,
    # en zonder mock wacht elke test op een DB-connectietimeout (zie
    # test_cva_breakthrough_logs_to_audit_chain.py voor de dedicated audit-write-tests).
    agent._write_breakthrough_audit_log = AsyncMock()  # type: ignore[method-assign]
    # ADR-036 OP-12 Fix 4: idem voor de Prana-budgetcontrole/-afrekening -- anders
    # raakt deze test een echte, gedeelde testdatabase (sanskritisetu_test_db:5455).
    agent._check_prana_budget = AsyncMock()  # type: ignore[method-assign]
    agent._charge_prana_for_breakthrough = AsyncMock()  # type: ignore[method-assign]
    return agent


class TestTenantResolutionInSingleTenantMode:
    def test_single_tenant_mode_resolves_the_fallback_tenant_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEPLOYMENT_MODE", "single_tenant")
        gate = _RecordingOversightGate()
        agent = _build_agent(gate)

        agent._execute_breakthrough_session(_trigger_event(tenant_id=None))

        assert gate.received_tenant_id == 1, (
            "In single_tenant-modus moet een trigger zonder expliciete tenant_id "
            "de ADR-035-fallback (1) doorgeven aan oversight_gate.check(), niet "
            "None en niet een verkeerde waarde."
        )

    def test_explicit_tenant_id_on_the_trigger_wins_over_the_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEPLOYMENT_MODE", "single_tenant")
        gate = _RecordingOversightGate()
        agent = _build_agent(gate)

        agent._execute_breakthrough_session(_trigger_event(tenant_id=42))

        assert gate.received_tenant_id == 42, (
            "Een expliciet op de trigger gezette tenant_id mag niet overschreven "
            "worden door de single-tenant-fallback."
        )


class TestTenantResolutionInSaasMode:
    def test_saas_mode_without_explicit_tenant_id_stays_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
        gate = _RecordingOversightGate()
        agent = _build_agent(gate)

        agent._execute_breakthrough_session(_trigger_event(tenant_id=None))

        assert gate.received_tenant_id is None, (
            "In saas-modus is er geen veilige tenant_id om te raden -- de "
            "bestaande fail-closed regressietest "
            "(test_cva_breakthrough_fails_closed_without_ticket.py) hangt hiervan "
            "af. Deze mag NOOIT stilzwijgend een waarde gaan invullen."
        )

    def test_deployment_mode_defaults_to_saas_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
        gate = _RecordingOversightGate()
        agent = _build_agent(gate)

        agent._execute_breakthrough_session(_trigger_event(tenant_id=None))

        assert gate.received_tenant_id is None, (
            "Zonder DEPLOYMENT_MODE-env-var moet het gedrag identiek zijn aan "
            "saas-modus (de bestaande default in resolve_single_tenant_fallback_id())."
        )
