"""ADR-036 OP-12/ADR031-001, fix-sprint dag 4.

`_execute_breakthrough_session()`'s `requires_human_approval`-tak liet een `# TODO: Submit
to BoardService for approval` staan die impliceert dat er nog een goedkeuringsmechanisme
gebouwd wordt. Dat gebeurt niet: `CVAAutonomousTrigger` heeft geen tenant-context en
`hitl_tickets.tenant_id` is `NOT NULL` (ADR-005) zonder een schone "systeem-tenant"-
conventie. Rakesh's expliciete beslissing (2026-08-19): fail-secure blijven blokkeren, geen
ticket, maar de log-regel moet dat DUIDELIJK zeggen in plaats van de misleidende TODO.

Dit pad is vandaag onbereikbaar in productie (de enige constructieplek, `cva_trigger =
CVAAutonomousTrigger()` -- regel 1055 in de pre-fix bestandsversie, regel 1062 in de huidige
versie na de regelverschuiving door deze fix -- geeft geen `oversight_gate` mee), dus deze
test construeert een instantie met een expliciete, echte gate-stub om het pad direct te
bereiken.

**Verplichte tweede blinde review (2026-08-19) vond een BLOCKER**: geen van de drie
onderstaande tests bewees dat de breakthrough-actie daadwerkelijk NIET uitvoert -- alleen
dat de LOG een bepaalde tekst wel/niet bevat. Een mutatietest (de `return` op de
approval-tak verwijderen) liet alle drie tests groen blijven terwijl
`_run_cva_breakthrough()` en `_enable_cva_file_management()` daadwerkelijk draaiden
(inclusief een echt bestand op disk). `_build_agent()` mockt nu ook
`_run_cva_breakthrough` zodat elke test kan bewijzen dat die NOOIT wordt aangeroepen.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from src.core.agents.cva_autonomous_trigger import CVAAutonomousTrigger, TriggerEvent
from src.core.types import TriggerType


class _StubOversightGate:
    """Een echte, minimale gate-dubbel -- geen `spec=`/`autospec`-loze mock (ADR-036 OP-147-les)."""

    def __init__(self, *, allowed: bool, requires_human_approval: bool, reason: str) -> None:
        self._result = MagicMock()
        self._result.allowed = allowed
        self._result.requires_human_approval = requires_human_approval
        self._result.reason = reason

    async def check(self, **_kwargs: Any) -> Any:
        return self._result


def _trigger_event() -> TriggerEvent:
    return TriggerEvent(
        trigger_type=TriggerType.MANUAL,
        priority=1,
        trigger_data={},
        timestamp=datetime.now(timezone.utc),
    )


def _build_agent(gate: _StubOversightGate) -> CVAAutonomousTrigger:
    agent = CVAAutonomousTrigger(oversight_gate=gate)  # type: ignore[arg-type]
    agent._log_to_sandbox = MagicMock()  # type: ignore[method-assign]
    # BLOCKER-1 (tweede blinde review): dit moet daadwerkelijk NOOIT aangeroepen worden op
    # het geblokkeerde/goedkeuring-vereist-pad -- anders is fail-secure alleen een claim in
    # de log, niet in het gedrag.
    agent._run_cva_breakthrough = MagicMock()  # type: ignore[method-assign]
    # ADR-036 OP-12 Fix 3: het echte pad probeert een echte DB-sessie te openen
    # (container.session_factory()) -- niet relevant voor deze fail-closed-tests, en
    # zonder mock wacht elke test op een DB-connectietimeout.
    agent._write_breakthrough_audit_log = AsyncMock()  # type: ignore[method-assign]
    # ADR-036 OP-12 Fix 4: idem voor de Prana-budgetcontrole/-afrekening -- anders
    # raakt deze test een echte, gedeelde testdatabase (sanskritisetu_test_db:5455).
    agent._check_prana_budget = AsyncMock()  # type: ignore[method-assign]
    agent._charge_prana_for_breakthrough = AsyncMock()  # type: ignore[method-assign]
    return agent


class TestApprovalRequiredFailsClosedWithoutTicket:
    def test_no_hitl_ticket_is_created_when_approval_is_required(self) -> None:
        """Geen HITL-ticket-aanmaak op dit pad -- er is geen tenant om het aan toe te wijzen.

        Let op: de eerlijke marker (`APPROVAL_REQUIRED_NO_TICKET`) bevat zelf het woord
        "ticket" -- deze test verbiedt daarom niet de substring "ticket", maar specifiek een
        TICKET-REFERENTIE zoals elders in dit project gebruikt wordt voor een echt aangemaakt
        ticket (`TICKET-STUB-OP163`-stijl, zie ADR-036 OP-163/`hitl_repository.py`) of de
        claim dat er iets "aangemaakt" is.
        """
        gate = _StubOversightGate(
            allowed=True, requires_human_approval=True, reason="risk too high"
        )
        agent = _build_agent(gate)

        agent._execute_breakthrough_session(_trigger_event())

        agent._run_cva_breakthrough.assert_not_called()  # type: ignore[attr-defined]

        for call in agent._log_to_sandbox.call_args_list:  # type: ignore[attr-defined]
            message = call.args[0]
            assert "TICKET-" not in message, (
                "Er wordt een ticketreferentie gelogd -- dat mag niet: er is geen tenant om "
                "het ticket aan toe te wijzen (Rakesh's beslissing 2026-08-19)."
            )
            assert "aangemaakt" not in message.lower(), (
                "Er wordt gesuggereerd dat er iets is aangemaakt -- dat mag niet: "
                "CVAAutonomousTrigger heeft geen tenant-context (Rakesh's beslissing 2026-08-19)."
            )

    def test_the_log_message_explains_why_no_ticket_exists_instead_of_a_todo(self) -> None:
        """De misleidende TODO ('nog te bouwen') moet vervangen zijn door een eerlijke uitleg.

        ROOD voor de fix: de huidige tekst noemt alleen 'requires human approval' en een
        TODO-comment die nooit in de log terechtkomt -- geen enkele log-regel legt uit DAT er
        bewust geen ticket komt en WAAROM. GROEN na de fix: een herkenbare marker
        (`APPROVAL_REQUIRED_NO_TICKET`) staat in de log, en de reden (geen tenant-context)
        staat in de comment op die plek in de broncode.
        """
        gate = _StubOversightGate(
            allowed=True, requires_human_approval=True, reason="risk too high"
        )
        agent = _build_agent(gate)

        agent._execute_breakthrough_session(_trigger_event())

        logged_messages = [
            call.args[0]
            for call in agent._log_to_sandbox.call_args_list  # type: ignore[attr-defined]
        ]
        assert any("APPROVAL_REQUIRED_NO_TICKET" in msg for msg in logged_messages), (
            "Geen enkele log-regel maakt duidelijk dat hier BEWUST geen goedkeuringsticket "
            "wordt aangemaakt (i.p.v. de oude, misleidende TODO-comment)."
        )

    def test_blocked_path_is_unaffected_by_the_approval_path_fix(self) -> None:
        """Regressie: het allowed=False-pad (BLOCKED) blijft ongewijzigd correct."""
        gate = _StubOversightGate(allowed=False, requires_human_approval=False, reason="denied")
        agent = _build_agent(gate)

        agent._execute_breakthrough_session(_trigger_event())

        agent._run_cva_breakthrough.assert_not_called()  # type: ignore[attr-defined]

        logged_messages = [
            call.args[0]
            for call in agent._log_to_sandbox.call_args_list  # type: ignore[attr-defined]
        ]
        assert any("GOVERNANCE_BLOCKED" in msg for msg in logged_messages)
        assert not any("APPROVAL_REQUIRED" in msg for msg in logged_messages)

    def test_approval_required_actually_blocks_execution_not_just_the_log(self) -> None:
        """BLOCKER-1 (tweede blinde review, 2026-08-19): fail-secure moet GEDRAG zijn, niet
        alleen een claim in de log.

        Gevonden door de `return` op de approval-tak te verwijderen: alle drie de
        oorspronkelijke tests bleven groen terwijl `_run_cva_breakthrough()` daadwerkelijk
        draaide (inclusief een echt geschreven bestand op disk via
        `_enable_cva_file_management()`). Deze test bewijst het gedrag direct, niet via de
        log-tekst.
        """
        gate = _StubOversightGate(
            allowed=True, requires_human_approval=True, reason="risk too high"
        )
        agent = _build_agent(gate)

        agent._execute_breakthrough_session(_trigger_event())

        agent._run_cva_breakthrough.assert_not_called()  # type: ignore[attr-defined]
