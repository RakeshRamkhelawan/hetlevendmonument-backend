"""De klant krijgt gewone taal als de council een voorstel niet kon beoordelen (BE-DEB-006 open punt, 2026-10-23).

Gemeten bij de acceptatie van 2026-10-22: een debiteurenvoorstel werd vier keer geblokkeerd omdat de RiskOfficer
na zijn tijdsgrens een TIMEOUT-veto gaf. De klant zag "Council-verdict blocked: ..." -- Engelse vaktaal, en niets
waaruit bleek dat het gewoon opnieuw kon. Een TIMEOUT was toen een veto; sinds 2026-10-27 is het een mensticket (de coordinator maakt dit veto niet meer, de
tests bouwen het zelf), maar een crash of open circuit breaker blijft een technisch veto. Alleen de tekst verandert,
en alleen als de BLOKKADE zelf technisch is. Een echt veto van een functionaris houdt zijn eigen uitleg.

Mutatiebewijs (in een wegwerp-worktree): `is_technisch_niet_beoordeeld` altijd False laten geven maakt de timeout-tests rood;
altijd True laat de tests op een echt veto rood worden.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.copilot.council.types import OfficerVerdict, VerdictType
from tests.unit.als.test_council_gate_per_action import _build_agent, _tool_call_lines

KLANTTEKST_STAM = "opnieuw"
VAKTAAL = ("Council-verdict", "TIMEOUT", "Fail-secure", "blocked", "veto")


def _stem(
    reason_code: str, verdict: VerdictType = VerdictType.VETO, naam: str = "RiskOfficer"
) -> OfficerVerdict:
    return OfficerVerdict(
        officer_name=naam,
        officer_version="1.0.0",
        verdict=verdict,
        reason_code=reason_code,
        reason_text=f"Fail-secure blocked due to {reason_code}",
        evidence={},
        deliberation_ms=500,
        confidence=1.0,
    )


def _beslissing(stemmen: tuple[OfficerVerdict, ...]) -> Any:
    from src.core.copilot.council.background_gate import AgentCouncilOutcome
    from src.core.copilot.council.types import DecisionVerdict

    class _D:
        verdict = DecisionVerdict.BLOCKED
        explanation_for_user = "De Co-Pilot kan deze actie niet uitvoeren."
        decision_id = "decision-blocked"
        officer_verdicts = stemmen

    return AgentCouncilOutcome(decision=_D(), hitl_ticket_ref=None)  # type: ignore[arg-type]


class TestHetOordeelOverEenTechnischeBlokkade:
    def test_een_timeout_is_technisch(self) -> None:
        from src.core.copilot.council.technische_blokkade import is_technisch_niet_beoordeeld

        assert is_technisch_niet_beoordeeld((_stem("TIMEOUT"),)) is True

    @pytest.mark.parametrize("code", ["CIRCUIT_BREAKER_OPEN", "INTERNAL_ERROR"])
    def test_ook_een_open_circuit_of_interne_fout_is_technisch(self, code: str) -> None:
        from src.core.copilot.council.technische_blokkade import is_technisch_niet_beoordeeld

        assert is_technisch_niet_beoordeeld((_stem(code),)) is True

    def test_een_echt_veto_is_niet_technisch(self) -> None:
        from src.core.copilot.council.technische_blokkade import is_technisch_niet_beoordeeld

        assert is_technisch_niet_beoordeeld((_stem("SHADOW_CEO_CRITICAL"),)) is False

    def test_een_echt_veto_naast_een_timeout_is_niet_technisch(self) -> None:
        from src.core.copilot.council.technische_blokkade import is_technisch_niet_beoordeeld

        stemmen = (_stem("TIMEOUT"), _stem("MISSING_SCOPE", naam="SecurityOfficer"))

        assert is_technisch_niet_beoordeeld(stemmen) is False

    def test_zonder_stemmen_is_het_niet_technisch(self) -> None:
        from src.core.copilot.council.technische_blokkade import is_technisch_niet_beoordeeld

        assert is_technisch_niet_beoordeeld(()) is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeKlanttekstVanDeAgentpoort:
    async def test_bij_een_timeout_staat_er_een_nederlandse_zin_zonder_vaktaal(
        self, council_gate: AsyncMock, hitl_ticket_repository: AsyncMock
    ) -> None:
        agent, _ = _build_agent(_tool_call_lines(1))
        council_gate.return_value = _beslissing((_stem("TIMEOUT"),))

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        fouten = " ".join(str(e) for e in (result.result_data.get("errors") or []))
        assert KLANTTEKST_STAM in fouten and not any(woord in fouten for woord in VAKTAAL), fouten

    async def test_de_actie_wordt_bij_een_timeout_nog_steeds_niet_uitgevoerd(
        self, council_gate: AsyncMock, hitl_ticket_repository: AsyncMock
    ) -> None:
        agent, broker = _build_agent(_tool_call_lines(1))
        council_gate.return_value = _beslissing((_stem("TIMEOUT"),))

        await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        assert broker.execute_tool.await_count == 0

    async def test_een_echt_veto_houdt_zijn_eigen_uitleg(
        self, council_gate: AsyncMock, hitl_ticket_repository: AsyncMock
    ) -> None:
        agent, _ = _build_agent(_tool_call_lines(1))
        council_gate.return_value = _beslissing((_stem("SHADOW_CEO_CRITICAL"),))

        result = await agent.execute_with_manifest_prompt(
            {"task": "gap analyse"}, initiated_by_user_id=agent._test_initiator
        )

        fouten = " ".join(str(e) for e in (result.result_data.get("errors") or []))
        assert "Council-verdict blocked" in fouten, fouten


class TestDeUitlegVanDeAuditfunctionaris:
    def test_bij_een_timeout_zegt_de_uitleg_dat_het_opnieuw_kan(self) -> None:
        from src.core.copilot.council.members.audit_officer import AuditOfficer
        from src.core.copilot.council.types import DecisionVerdict

        uitleg = AuditOfficer(AsyncMock())._generate_explanation(
            (_stem("TIMEOUT"),), DecisionVerdict.BLOCKED
        )

        assert KLANTTEKST_STAM in uitleg and not any(woord in uitleg for woord in VAKTAAL), uitleg

    def test_bij_een_echt_veto_blijft_de_gewone_uitleg(self) -> None:
        from src.core.copilot.council.members.audit_officer import AuditOfficer
        from src.core.copilot.council.types import DecisionVerdict

        uitleg = AuditOfficer(AsyncMock())._generate_explanation(
            (_stem("SHADOW_CEO_CRITICAL"),), DecisionVerdict.BLOCKED
        )

        assert uitleg == "De Co-Pilot kan deze actie niet uitvoeren."


class TestDeKlanttekstVanDeBasisagent:
    @pytest.mark.asyncio
    async def test_bij_een_timeout_zegt_de_basisagent_dat_het_opnieuw_kan(self) -> None:
        from unittest.mock import patch

        from src.core.tool_broker.exceptions import ToolExecutionException
        from tests.unit.agents.test_enhanced_base_agent_council_consultation import _make_agent

        agent = _make_agent()
        agent._initiated_by_user_id = 42

        with (
            patch("src.core.agents.base_agent.get_feature_flag", return_value=True),
            patch(
                "src.core.copilot.council.background_gate.request_council_decision_for_agent",
                new_callable=AsyncMock,
                return_value=_beslissing((_stem("TIMEOUT"),)),
            ),
            pytest.raises(ToolExecutionException) as fout,
        ):
            await agent.execute_tool("test__echo", {"value": 1})

        tekst = str(fout.value)
        assert KLANTTEKST_STAM in tekst and not any(woord in tekst for woord in VAKTAAL), tekst
