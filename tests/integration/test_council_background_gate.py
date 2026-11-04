"""Integration tests for the Council-poort achtergrondingang (ADR-036 D2).

Draait tegen de echte testdatabase (poort 5455, via tests/integration/conftest.py's
autouse fixtures) en Redis. build_council()'s eigen 8-Officer-bedrading wordt hier
NIET opnieuw getest -- dat is al gedekt door tests/integration/copilot/. Deze tests
verifiëren specifiek wat background_gate.py zelf toevoegt: geen HTTPException-koppeling,
het gecorrigeerde tenant-context try/finally-patroon (AUDIT-003), en dat de Proposal
correct wordt opgebouwd voor de Council.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.copilot.council.background_gate import (
    is_irreversible_verdict_blocked,
    request_council_decision_for_agent,
)
from src.core.copilot.council.types import (
    CouncilDecision,
    DecisionVerdict,
    ProposalTrigger,
)
from src.core.middleware.tenant_context import get_tenant_id

pytestmark = pytest.mark.asyncio


def _make_decision(verdict: DecisionVerdict, tenant_id: int) -> CouncilDecision:
    return CouncilDecision(
        proposal_id=uuid4(),
        tenant_id=tenant_id,
        user_id=1,
        verdict=verdict,
        officer_verdicts=(),
        explanation_for_user="test",
        decision_hash="deadbeef",
        previous_decision_hash=None,
        deliberation_ms=1,
    )


class TestRequestCouncilDecisionForAgent:
    async def test_returns_decision_without_raising_on_blocked(self, test_tenant_id: int) -> None:
        """Unlike require_council_approval(), a non-APPROVED verdict must be
        returned, never raised as an HTTPException -- the calling agent decides
        how to translate it into its own statuscontract (ADR-036 D7)."""
        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.BLOCKED, test_tenant_id)
        )

        with patch(
            "src.core.copilot.council.background_gate.build_council",
            AsyncMock(return_value=fake_council),
        ):
            outcome = await request_council_decision_for_agent(
                tenant_id=test_tenant_id,
                agent_id="test-worker",
                user_id=1,
                action_type="send_notification",
                action_params={},
                reasoning="integration test",
                trigger=ProposalTrigger.PROACTIVE_MONITOR,
            )

        assert outcome.decision.verdict == DecisionVerdict.BLOCKED
        assert is_irreversible_verdict_blocked(outcome.decision) is True
        assert outcome.hitl_ticket_ref is None, (
            "BLOCKED is geen HITL_REQUIRED -- de gate mag hier geen ticket aanmaken."
        )

    async def test_returns_approved_decision(self, test_tenant_id: int) -> None:
        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.APPROVED, test_tenant_id)
        )

        with patch(
            "src.core.copilot.council.background_gate.build_council",
            AsyncMock(return_value=fake_council),
        ):
            outcome = await request_council_decision_for_agent(
                tenant_id=test_tenant_id,
                agent_id="test-worker",
                user_id=1,
                action_type="send_notification",
                action_params={},
                reasoning="integration test",
            )

        assert outcome.decision.verdict == DecisionVerdict.APPROVED
        assert is_irreversible_verdict_blocked(outcome.decision) is False
        assert outcome.hitl_ticket_ref is None

    async def test_tenant_context_cleared_after_call(self, test_tenant_id: int) -> None:
        """AUDIT-003: the tenant ContextVar must be cleared in `finally`, even
        though the try-block starts immediately after set_tenant_id() (the
        corrected pattern -- see the module docstring)."""
        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.APPROVED, test_tenant_id)
        )

        assert get_tenant_id() is None

        with patch(
            "src.core.copilot.council.background_gate.build_council",
            AsyncMock(return_value=fake_council),
        ):
            await request_council_decision_for_agent(
                tenant_id=test_tenant_id,
                agent_id="test-worker",
                user_id=1,
                action_type="send_notification",
                action_params={},
                reasoning="integration test",
            )

        assert get_tenant_id() is None

    async def test_tenant_context_cleared_even_if_council_raises(self, test_tenant_id: int) -> None:
        """The finally-cleanup must run even when deliberate() itself raises --
        this is exactly the exception-path guarantee AUDIT-003 requires."""
        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch(
                "src.core.copilot.council.background_gate.build_council",
                AsyncMock(return_value=fake_council),
            ),
            pytest.raises(RuntimeError, match="boom"),
        ):
            await request_council_decision_for_agent(
                tenant_id=test_tenant_id,
                agent_id="test-worker",
                user_id=1,
                action_type="send_notification",
                action_params={},
                reasoning="integration test",
            )

        assert get_tenant_id() is None

    async def test_two_sequential_calls_do_not_leak_tenant_context(self) -> None:
        """Cross-tenant isolation: a second call for a different tenant must
        never observe the first tenant's context (ADR-003/004)."""
        seen_tenant_ids: list[int | str | None] = []

        async def _capture_and_decide(proposal: object) -> CouncilDecision:
            seen_tenant_ids.append(get_tenant_id())
            return _make_decision(DecisionVerdict.APPROVED, 1)

        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(side_effect=_capture_and_decide)

        with patch(
            "src.core.copilot.council.background_gate.build_council",
            AsyncMock(return_value=fake_council),
        ):
            await request_council_decision_for_agent(
                tenant_id=1,
                agent_id="test-worker",
                user_id=1,
                action_type="send_notification",
                action_params={},
                reasoning="tenant A",
            )
            await request_council_decision_for_agent(
                tenant_id=2,
                agent_id="test-worker",
                user_id=1,
                action_type="send_notification",
                action_params={},
                reasoning="tenant B",
            )

        assert seen_tenant_ids == [1, 2]
        assert get_tenant_id() is None


class TestTheGateCreatesItsOwnHitlTicket:
    """ADR-036 OP-167 (open-punten-opruiming dag 1): de gate garandeert nu zelf een ticket.

    Voorheen deed alleen `specialist_base.py` (de enige aanroeper) dit, met eigen
    gerepliceerde logica -- een tweede aanroeper zou stilzwijgend GEEN ticket hebben
    gekregen. Deze tests bewijzen het tegenovergestelde: de gate-FUNCTIE zelf, los van wie
    hem aanroept, maakt het ticket aan zodra het RAUWE Council-verdict HITL_REQUIRED is.

    `HITLTicketRepository` wordt hier gemockt (niet tegen de echte tabel getoetst) om de
    exacte argumenten te kunnen inspecteren -- dezelfde scheiding als
    `tests/unit/als/test_council_gate_per_action.py` toepast voor de D4-002-floor.
    """

    async def test_a_raw_hitl_required_verdict_creates_a_ticket_with_the_right_arguments(
        self, test_tenant_id: int
    ) -> None:
        raw_decision = _make_decision(DecisionVerdict.HITL_REQUIRED, test_tenant_id)
        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(return_value=raw_decision)
        fake_repo = AsyncMock()
        fake_repo.create_hitl_request = AsyncMock(return_value="TICKET-REF-XYZ")

        with (
            patch(
                "src.core.copilot.council.background_gate.build_council",
                AsyncMock(return_value=fake_council),
            ),
            patch(
                "src.core.tool_broker.hitl_repository.HITLTicketRepository",
                return_value=fake_repo,
            ),
        ):
            outcome = await request_council_decision_for_agent(
                tenant_id=test_tenant_id,
                agent_id="hr_skill",
                user_id=7,
                action_type="query_hr_database",
                action_params={"arg_keys": ["employee_id"]},
                ticket_action_params={"employee_id": "e-0"},
                reasoning="integration test",
            )

        assert outcome.decision.verdict == DecisionVerdict.HITL_REQUIRED
        assert outcome.hitl_ticket_ref == "TICKET-REF-XYZ"

        fake_repo.create_hitl_request.assert_awaited_once()
        kwargs = fake_repo.create_hitl_request.await_args.kwargs
        assert kwargs["tenant_id"] == test_tenant_id
        assert kwargs["user_id"] == 7
        assert kwargs["decision_id"] == str(raw_decision.decision_id), (
            "Het ticket moet naar DEZE specifieke beraadslaging kunnen terugverwijzen, niet "
            "naar een willekeurige of hardcoded decision_id."
        )
        assert kwargs["reason"] == "test"
        assert kwargs["action_type"] == "query_hr_database"
        # `ticket_action_params`, niet `action_params`: het ticket heeft de RUWE waarden
        # nodig, niet de (mogelijk geredigeerde) versie die de Council zag.
        assert kwargs["action_params"] == {"employee_id": "e-0"}
        assert kwargs["executing_identity"] == "hr_skill", (
            "De permissiecheck bij het aanmaken van het ticket moet de identiteit van de "
            "AANVRAGENDE agent toetsen, niet een hardcoded 'copilot' (ADR-036 OP-163)."
        )

    async def test_falls_back_to_action_params_when_no_ticket_action_params_given(
        self, test_tenant_id: int
    ) -> None:
        """Een aanroeper zonder eigen redactielaag (zoals `copilot/service.py::handle_turn`)
        geeft `ticket_action_params` niet mee -- het ticket gebruikt dan gewoon
        `action_params` zelf, hetzelfde patroon als dat HTTP-pad al had."""
        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.HITL_REQUIRED, test_tenant_id)
        )
        fake_repo = AsyncMock()
        fake_repo.create_hitl_request = AsyncMock(return_value="TICKET-REF-ABC")

        with (
            patch(
                "src.core.copilot.council.background_gate.build_council",
                AsyncMock(return_value=fake_council),
            ),
            patch(
                "src.core.tool_broker.hitl_repository.HITLTicketRepository",
                return_value=fake_repo,
            ),
        ):
            outcome = await request_council_decision_for_agent(
                tenant_id=test_tenant_id,
                agent_id="test-worker",
                user_id=1,
                action_type="send_notification",
                action_params={"title": "hallo"},
                reasoning="integration test",
            )

        assert outcome.hitl_ticket_ref == "TICKET-REF-ABC"
        kwargs = fake_repo.create_hitl_request.await_args.kwargs
        assert kwargs["action_params"] == {"title": "hallo"}

    async def test_a_non_hitl_verdict_never_creates_a_ticket(self, test_tenant_id: int) -> None:
        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.APPROVED, test_tenant_id)
        )

        with (
            patch(
                "src.core.copilot.council.background_gate.build_council",
                AsyncMock(return_value=fake_council),
            ),
            patch(
                "src.core.tool_broker.hitl_repository.HITLTicketRepository",
            ) as repo_cls,
        ):
            outcome = await request_council_decision_for_agent(
                tenant_id=test_tenant_id,
                agent_id="test-worker",
                user_id=1,
                action_type="send_notification",
                action_params={},
                reasoning="integration test",
            )

        assert outcome.hitl_ticket_ref is None
        repo_cls.assert_not_called()

    async def test_an_unknown_tool_gets_no_ticket_but_does_not_raise(
        self, test_tenant_id: int
    ) -> None:
        """Gate 2-bevinding: `create_hitl_request` weigert zelf met `ValueError` voor een
        onbekende tool (OP-90) -- de gate moet dat vangen, niet laten propageren. Een
        toekomstige tweede aanroeper van deze functie heeft mogelijk geen eigen try/except
        (dat is precies het OP-167-probleem), dus een onverwachte exception hier zou het
        probleem verplaatsen in plaats van oplossen."""
        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.HITL_REQUIRED, test_tenant_id)
        )
        fake_repo = AsyncMock()
        fake_repo.create_hitl_request = AsyncMock(
            side_effect=ValueError("Geen uitvoerder voor tool 'onbekend'")
        )

        with (
            patch(
                "src.core.copilot.council.background_gate.build_council",
                AsyncMock(return_value=fake_council),
            ),
            patch(
                "src.core.tool_broker.hitl_repository.HITLTicketRepository",
                return_value=fake_repo,
            ),
        ):
            outcome = await request_council_decision_for_agent(
                tenant_id=test_tenant_id,
                agent_id="test-worker",
                user_id=1,
                action_type="onbekend",
                action_params={},
                reasoning="integration test",
            )

        assert outcome.decision.verdict == DecisionVerdict.HITL_REQUIRED
        assert outcome.hitl_ticket_ref is None

    async def test_an_unauthorized_identity_gets_no_ticket_but_does_not_raise(
        self, test_tenant_id: int
    ) -> None:
        """Zelfde als hierboven, maar voor de TWEEDE weigeringsgrond: `create_hitl_request`
        gooit `PermissionError` als `executing_identity` de tool niet mag (OP-163). Dit is
        een ANDERE exception-klasse dan de onbekende-tool-weigering en moet apart gevangen
        worden -- gemeten met een echte tweede exception-klasse, niet aangenomen dat een
        enkele `except ValueError` genoeg is."""
        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.HITL_REQUIRED, test_tenant_id)
        )
        fake_repo = AsyncMock()
        fake_repo.create_hitl_request = AsyncMock(
            side_effect=PermissionError("agent mag deze tool niet uitvoeren")
        )

        with (
            patch(
                "src.core.copilot.council.background_gate.build_council",
                AsyncMock(return_value=fake_council),
            ),
            patch(
                "src.core.tool_broker.hitl_repository.HITLTicketRepository",
                return_value=fake_repo,
            ),
        ):
            outcome = await request_council_decision_for_agent(
                tenant_id=test_tenant_id,
                agent_id="test-worker",
                user_id=1,
                action_type="query_hr_database",
                action_params={},
                reasoning="integration test",
            )

        assert outcome.decision.verdict == DecisionVerdict.HITL_REQUIRED
        assert outcome.hitl_ticket_ref is None
