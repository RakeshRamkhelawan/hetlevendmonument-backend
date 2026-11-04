"""Het agent-voorstel draagt wat de officieren nodig hebben (SP-COUNCIL-GATE-001).

Twee officieren toetsen eigenschappen die het agent-pad niet meestuurde, gemeten 2026-08-15
op exact de payload uit `specialist_base._council_rejection`:

- ComplianceOfficer: `APPROVE_WITH_MODIFICATION` / `MISSING_AI_DISCLOSURE` -- hij eist
  `ai_disclosure` in `action_params`.
- SanityOfficer: `VETO` / `HALLUCINATION_DETECTED` met reden `empty_suggestion` -- hij voert
  `proposal.message` door `HallucinationGuard.check()`, en die keurt leegte af.

De poort laat alleen `APPROVED` door en kan een gevraagde aanpassing niet toepassen, dus beide
oordelen betekenen: actie geweigerd.

**Waarom dit bestand in `tests/unit/copilot/` staat.** In `tests/unit/als`,
`tests/unit/agents` en `tests/unit/tool_broker` is `council_gate` een autouse-fixture die
standaard APPROVED geeft; `tests/fixtures/agent_governance.py` benoemt dat zelf als bewust
risico. Een test daar zou deze eigenschap niet kunnen zien.

**De grens die blijft staan.** De velden worden door het SYSTEEM gezet, nooit door het model.
`_council_rejection` geeft met opzet alleen de toolnaam en de sleutelnamen door (BE-AGT-043),
om twee redenen die allebei nog gelden: rauwe modeltekst belandt anders onuitwisbaar in de
ADR-019-keten, en een prompt-injectie kan anders zijn eigen governance-oordeel meesturen
(`{"ai_disclosure": true}` zet de ComplianceOfficer stil). De laatste test in dit bestand
bewaakt precies dat.

**Het bericht bevat GEEN sleutelnamen, alleen een aantal.** Uit de Gate 2-review: de sleutels
komen uit `json.loads()` van modeluitvoer, en `HallucinationGuard` weigert op absolute woorden
en op ongegronde bestandsnamen. Een argument dat `always` heet, of `report.py`, zou dan een
veto opleveren dat het MODEL kiest -- exact de eigenschap die dit bestand verbiedt. De toolnaam
mag er wel in: die komt uit het manifest, niet uit het model.

**`autospec=True` op de patch is niet cosmetisch.** Gemeten 2026-08-15:
`AsyncMock(spec=Klasse)` accepteert een argument dat de echte functie niet heeft; alleen
`create_autospec`/`autospec=True` controleert de signatuur. Zonder autospec zou deze test groen
staan terwijl `request_council_decision_for_agent` helemaal geen `message`-parameter heeft --
en dan geeft productie een `TypeError` die `act()` opvangt als "governance-poort niet
bereikbaar". De poort blijft dan dicht en de test zegt dat alles goed is.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

PILOT_TENANT = 1
PILOT_USER = 42


def _agent() -> Any:
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

    agent = SkillsGapTrainingSkill(tenant_id=PILOT_TENANT)
    agent._initiated_by_user_id = PILOT_USER
    # Sinds ADR-036 D4-002 is de piloot Annex III/HITL: `_captured_proposal()` hieronder mockt
    # een APPROVED-verdict, en dat zou de floor nu naar HITL_REQUIRED optillen (een echte
    # databasesessie openen) voordat deze tests de UITGAANDE proposal-kwargs kunnen inspecteren
    # -- precies wat dit bestand test, niet de HITL-floor zelf. Expliciet terugzetten.
    agent.config["human_in_the_loop"] = "hotl"
    return agent


async def _captured_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    """Vang de kwargs waarmee de poort de raad aanroept.

    `autospec=True`: de vervanger krijgt de ECHTE signatuur van
    `request_council_decision_for_agent`. Draagt de poort een argument mee dat die functie
    niet kent, dan gooit de mock hier al een `TypeError` in plaats van dat de fout pas in
    productie zichtbaar wordt.
    """
    from src.core.copilot.council.background_gate import AgentCouncilOutcome
    from src.core.copilot.council.types import DecisionVerdict

    besluit: Any = AsyncMock()
    besluit.verdict = DecisionVerdict.APPROVED
    besluit.explanation_for_user = "ok"

    with patch(
        "src.core.als.agents.specialist_base.request_council_decision_for_agent",
        autospec=True,
    ) as gate:
        # APPROVED en `human_in_the_loop == "hotl"` (zie `_agent()` hierboven): de D4-002-floor
        # is hier niet van toepassing, dus geen ticket, `hitl_ticket_ref=None`.
        gate.return_value = AgentCouncilOutcome(decision=besluit, hitl_ticket_ref=None)
        await _agent()._council_rejection("query_hr_database", payload)

    assert gate.await_count == 1, "De poort heeft de raad niet aangeroepen."
    aanroep = gate.await_args
    assert aanroep is not None
    assert not aanroep.args, (
        "De raad wordt positioneel aangeroepen; deze ingang is keyword-only "
        "(`background_gate.py:50`)."
    )
    return dict(aanroep.kwargs)


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheProposalIsComplete:
    async def test_the_proposal_carries_an_ai_disclosure(self) -> None:
        """Zonder dit veld eist de ComplianceOfficer een aanpassing die de poort niet kan doen."""
        kwargs = await _captured_proposal({"role": "Analyst"})

        params = kwargs["action_params"]
        assert params.get("ai_disclosure"), (
            "Het voorstel draagt geen AI-bekendmaking. De ComplianceOfficer geeft dan "
            "APPROVE_WITH_MODIFICATION en de poort weigert -- elke toolactie strandt daar."
        )

    async def test_the_proposal_carries_a_message(self) -> None:
        """Zonder bericht ziet de SanityOfficer een lege suggestie en dus een hallucinatie."""
        kwargs = await _captured_proposal({"role": "Analyst"})

        bericht = kwargs.get("message") or ""
        assert bericht.strip(), (
            "Het voorstel draagt geen bericht. HallucinationGuard.check() keurt leegte af met "
            "`empty_suggestion` en de SanityOfficer geeft een veto."
        )
        assert "query_hr_database" in bericht, (
            "Het bericht noemt de tool niet. Dan beoordeelt de SanityOfficer iets dat losstaat "
            "van de actie waar het over gaat."
        )

    async def test_the_proposal_carries_the_department_and_specialisation(self) -> None:
        """Systeemdata uit het manifest, met de ECHTE waarden.

        Gate 2-review ronde 2: de eerste versie las `self.config["role"]`, een sleutel die
        `SkillManifest.to_config()` niet levert -- er ging dus altijd een lege string mee. Een
        veld dat er wel staat maar niets bevat is erger dan geen veld: het ziet eruit alsof de
        informatie er is.
        """
        kwargs = await _captured_proposal({"role": "Analyst"})

        params = kwargs["action_params"]
        assert params.get("department") == "hr_culture", (
            f"De afdeling is {params.get('department')!r}; verwacht `hr_culture` uit het "
            "manifest van de piloot."
        )
        assert params.get("specialisation"), (
            "De specialisatie is leeg. Leest de code een sleutel die het manifest niet levert?"
        )

    async def test_the_message_actually_survives_the_hallucination_guard(self) -> None:
        """Niet 'er staat iets', maar 'de officier keurt het goed'.

        Zonder deze test volstaat het bericht `"query_hr_database"` en toetst niets of de
        SanityOfficer er daadwerkelijk mee door de bocht komt.
        """
        from src.core.learning.safety.hallucination_guard import HallucinationGuard

        kwargs = await _captured_proposal({"role": "Analyst"})

        veilig, reden = HallucinationGuard.check(kwargs.get("message"), {})
        assert veilig, (
            f"HallucinationGuard weigert het bericht ({reden}). De SanityOfficer geeft dan een "
            "veto en de actie strandt alsnog."
        )

    async def test_the_message_does_not_contain_model_written_key_names(self) -> None:
        """Sleutelnamen komen uit modeluitvoer en mogen het oordeel niet kunnen sturen.

        `always` is een absoluut woord (`hallucination_guard.py:25`) en `report.py` een
        ongegronde bestandsverwijzing (`:38`). Staan sleutelnamen in het bericht, dan kiest het
        MODEL of de SanityOfficer een veto geeft.
        """
        from src.core.learning.safety.hallucination_guard import HallucinationGuard

        kwargs = await _captured_proposal({"always": 1, "report.py": 2})

        bericht = kwargs.get("message") or ""
        assert "always" not in bericht and "report.py" not in bericht, (
            f"Sleutelnamen uit de payload staan in het bericht: {bericht!r}. Een model kan zo "
            "zijn eigen veto uitlokken of vermijden."
        )
        veilig, reden = HallucinationGuard.check(bericht, {})
        assert veilig, f"Het bericht wordt geweigerd ({reden}) door namen die het model koos."


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheModelCannotSteerItsOwnJudgement:
    async def test_model_written_values_never_reach_the_council(self) -> None:
        """De payload van het model gaat NIET mee -- alleen de sleutelnamen (BE-AGT-043)."""
        kwargs = await _captured_proposal({"role": "Geheime Waarde", "notitie": "vrije tekst"})

        params = kwargs["action_params"]
        platte_tekst = str(params)
        assert "Geheime Waarde" not in platte_tekst and "vrije tekst" not in platte_tekst, (
            f"Modelwaarden staan in het voorstel: {params}. Die belanden verbatim in de "
            "onuitwisbare ADR-019-keten en botsen met AVG art. 16/17."
        )
        assert params.get("arg_keys") == ["notitie", "role"], (
            "De sleutelnamen horen er wel in te staan; daar beoordeelt de raad de vorm op."
        )

    async def test_the_model_cannot_set_the_disclosure_itself(self) -> None:
        """Een payload die zijn eigen bekendmaking meebrengt, mag die van het systeem niet
        overschrijven.

        Anders zet een prompt-injectie met `{"ai_disclosure": true}` de ComplianceOfficer stil
        -- exact het scenario dat in `_council_rejection` als reden staat waarom de payload
        niet wordt doorgegeven.
        """
        kwargs = await _captured_proposal({"ai_disclosure": "door het model gezet"})

        assert kwargs["action_params"]["ai_disclosure"] != "door het model gezet", (
            "Het model heeft de bekendmaking gezet. Daarmee bepaalt de aanroeper zijn eigen "
            "governance-oordeel."
        )
