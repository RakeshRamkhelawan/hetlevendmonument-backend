"""ADR-036 OP-12 (addendum SS8.2, Fix 3, 2026-08-26): CVAAutonomousTrigger schrijft de
governance-beslissing naar de ADR-019 audit-keten (`audit_logs`), naast de bestaande
platte-tekst sandboxlog.

Voor deze fix ging de beslissing van `_execute_breakthrough_session()` alleen naar
`_log_to_sandbox()` (een lokaal bestand). `AuditServiceAdapter.log_security_event()`
(gebruikt door `OversightGate` intern) geeft nooit een `db`-sessie mee, waardoor
`log_security_event()` de databaseschrijf stilzwijgend overslaat
(`governance/services/audit_service.py:188-190`, geverifieerd, niet aangenomen) --
`CVAAutonomousTrigger` schrijft daarom zelf, direct, met een echte sessie.

Deze test gebruikt een FAKE session factory (geen echte DB) en verifieert het GEDRAG:
welke argumenten `log_security_event()` daadwerkelijk ontvangt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.agents.cva_autonomous_trigger import CVAAutonomousTrigger, TriggerEvent
from src.core.types import TriggerType


class _FakeAsyncSession:
    """Minimale AsyncSession-dubbel die `async with` en `commit()` ondersteunt."""

    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> "_FakeAsyncSession":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True


class _FakeSessionFactory:
    def __init__(self, session: _FakeAsyncSession) -> None:
        self._session = session

    def __call__(self) -> _FakeAsyncSession:
        return self._session


class _RecordingOversightGate:
    def __init__(self, *, allowed: bool, requires_human_approval: bool, reason: str) -> None:
        self._result = MagicMock()
        self._result.allowed = allowed
        self._result.requires_human_approval = requires_human_approval
        self._result.reason = reason

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


def _build_agent(gate: _RecordingOversightGate) -> CVAAutonomousTrigger:
    agent = CVAAutonomousTrigger(oversight_gate=gate)  # type: ignore[arg-type]
    agent._log_to_sandbox = MagicMock()  # type: ignore[method-assign]
    agent._run_cva_breakthrough = MagicMock()  # type: ignore[method-assign]
    # ADR-036 OP-12 Fix 4: deze tests gaan over de audit-write, niet over Prana --
    # zonder mock raken ze een echte, gedeelde testdatabase (sanskritisetu_test_db:5455).
    agent._check_prana_budget = AsyncMock()  # type: ignore[method-assign]
    agent._charge_prana_for_breakthrough = AsyncMock()  # type: ignore[method-assign]
    return agent


def test_the_governance_decision_is_written_to_the_audit_chain() -> None:
    """Kern-regressietest: log_security_event() wordt aangeroepen met een echte
    db-sessie (niet None) en de juiste tenant_id/reden -- dit is precies wat
    voor de fix stilzwijgend werd overgeslagen."""
    gate = _RecordingOversightGate(allowed=True, requires_human_approval=False, reason="ok")
    agent = _build_agent(gate)
    session = _FakeAsyncSession()

    with (
        patch("src.core.container.get_container") as mock_get_container,
        patch(
            "src.core.governance.services.audit_service.log_security_event",
            new_callable=AsyncMock,
        ) as mock_log_security_event,
    ):
        mock_get_container.return_value.session_factory.return_value = _FakeSessionFactory(session)

        agent._execute_breakthrough_session(_trigger_event(tenant_id=7))

    mock_log_security_event.assert_awaited_once()
    assert mock_log_security_event.await_args is not None
    call_kwargs = mock_log_security_event.await_args.kwargs
    assert call_kwargs["db"] is session, (
        "log_security_event() moet een echte db-sessie krijgen -- zonder dat argument "
        "slaat de functie de databaseschrijf stilzwijgend over."
    )
    assert call_kwargs["tenant_id"] == 7
    assert call_kwargs["event_type"] == "CVA_AUTONOMOUS_BREAKTHROUGH"
    assert session.committed is True, "De audit-transactie moet gecommit worden."


def test_audit_write_failure_never_blocks_the_governance_decision() -> None:
    """best_effort-garantie: als de audit-schrijf faalt (bv. DB onbereikbaar), moet
    de governance-beslissing zelf onaangetast blijven -- geen crash, geen gewijzigd
    resultaat."""
    gate = _RecordingOversightGate(allowed=True, requires_human_approval=False, reason="ok")
    agent = _build_agent(gate)

    with (
        patch("src.core.container.get_container") as mock_get_container,
    ):
        mock_get_container.return_value.session_factory.return_value = MagicMock(
            side_effect=RuntimeError("db onbereikbaar")
        )

        # Mag geen exception naar buiten laten lekken.
        agent._execute_breakthrough_session(_trigger_event(tenant_id=7))

    agent._run_cva_breakthrough.assert_called_once()  # type: ignore[attr-defined]
