"""Een officier die zijn tijdgrens overschrijdt, legt de actie aan een mens voor; hij blokkeert of keurt haar niet stil.

Brief 2026-10-27 (de Council onder last). Gemeten door 8c op 2026-10-27, 20 rekenprocessen als last naast de testset
(53 integratietests): 21 en 24 tests rood, ALLE door een TIMEOUT van de SecurityOfficer (46 van 46; 0x
CIRCUIT_BREAKER_OPEN). Zonder last duurt die officier ~70 ms (p95 80), onder last 483 ms (p95 628, max 680): hij haalt de
grens van 500 ms niet en kreeg daardoor een VETO. Dezelfde machine-drukte in productie blokkeert zo een goede
agentactie, en in agent-first ketens gaat elke actie langs de Council.

Het besluit (regie):
  - een TIJDOVERSCHRIJDING wordt UITSTEL naar een mens: het oordeel van die officier is `REQUIRE_HITL` met de reden
    "<officier>: De controle kon niet op tijd worden afgerond.", en het eindoordeel `HITL_REQUIRED` (de service maakt
    daar een HITL-ticket van, met die reden in de uitleg);
  - UITZONDERING 1 (Gate 2 security-review 2026-10-28): de SecurityOfficer is de enige die de rechten van de aanvrager
    toetst, en bij goedkeuren van een ticket gebeurt dat niet opnieuw (zelfgoedkeuring is standaard toegestaan): zijn
    tijdoverschrijding blijft een VETO. UITZONDERING 2: een officier zonder vetorecht blijft `REQUIRE_DEFERRAL` (geen
    ticketvloed door een waarschuwer die tikt);
  - dat keurt NOOIT goed: ook als alle andere officieren akkoord zijn wordt het geen APPROVED of MODIFIED;
  - een ECHTE VETO op inhoud blijft een VETO (BLOCKED), ook naast een tijdoverschrijding;
  - een CRASH (INTERNAL_ERROR) en een open circuitbreaker blijven fail-secure zoals ze waren: de meting wees alleen
    TIMEOUT aan als oorzaak.

Rood voor de fix: een tijdoverschrijding gaf een `VETO` en het eindoordeel `BLOCKED` (of, voor een officier zonder
vetorecht, `REQUIRE_DEFERRAL` en `DEFERRED`).

MUTATIEBEWIJS (2026-10-28, kopie als terugweg, 6 mutaties, basis 20 passed): Security niet meer uitgezonderd -> 1 rood;
uitzondering te breed (elke officier houdt veto) -> 6 rood; officier zonder vetorecht ook naar een mens -> 1 rood;
TIMEOUT keurt goed -> 10 rood; reden zonder officiernaam -> 1 rood; uitstel wint van een echte veto -> 1 rood.

De tests hangen niet van de klok af: de trage officier wacht op een gebeurtenis die nooit komt en de beleidsgrens staat
op 10 ms (`_verkort_beleid`).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.copilot.council.coordinator import AgentCouncil
from src.core.copilot.council.members.audit_officer import AuditOfficer
from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)

REDEN = "De controle kon niet op tijd worden afgerond."


def _verdict(officer_name: str, verdict: VerdictType, **kwargs: object) -> OfficerVerdict:
    return OfficerVerdict(
        officer_name=officer_name,
        officer_version="1.0.0-test",
        verdict=verdict,
        reason_code=str(kwargs.get("reason_code", "TEST_OK")),
        reason_text=str(kwargs.get("reason_text", "Test verdict")),
        evidence={},
        deliberation_ms=10,
        confidence=1.0,
    )


def _proposal() -> Proposal:
    return Proposal(
        tenant_id=42,
        user_id=1337,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="navigate_to",
        action_params={"route": "/dashboard"},
        reasoning="User asked to navigate to dashboard",
        data_classification=DataClassification.INTERNAL,
        confidence=0.95,
        model_id="test-model",
        model_version="0.0.1",
        context_snapshot={},
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def council() -> AgentCouncil:
    officers = {
        name: MagicMock(
            name=name,
            deliberate=AsyncMock(),
            can_cache=MagicMock(return_value=False),
            timeout_ms=500,
        )
        for name in [
            "compliance",
            "privacy",
            "security",
            "risk",
            "ethics",
            "resource",
            "sanity",
            "audit",
        ]
    }
    for sleutel, o in officers.items():
        o.name = f"{sleutel.capitalize()}Officer"
        o.version = "1.0.0"
        o.health_check = MagicMock(return_value=True)
    return AgentCouncil(**officers)


async def _traag(*_args: object, **_kwargs: object) -> OfficerVerdict:
    """Wacht op een gebeurtenis die nooit komt: alleen de tijdgrens maakt er een einde aan, niet de klok van de test."""
    await asyncio.Event().wait()
    return _verdict("traag", VerdictType.APPROVE)


def _verkort_beleid(context: object) -> None:
    """Zet de beleidsgrens van elke officier op 10 ms: het echte beleid (500 tot 3000 ms) zou de test traag maken."""
    for regel in context.policy.officers.values():  # type: ignore[attr-defined]
        regel.timeout_ms = 10


async def _beraadslaag(
    council: AgentCouncil, *, traag: int | None, veto: int | None = None, crash: int | None = None
) -> tuple[tuple[OfficerVerdict, ...], DecisionVerdict]:
    """Alle officieren keuren goed, behalve de genoemde: traag (tijdgrens 10 ms), vetoot, of crasht."""
    proposal = _proposal()
    context = await council._build_context(proposal)
    _verkort_beleid(context)
    for i, officer in enumerate(council._voting_officers):
        if i == traag:
            officer.deliberate.side_effect = _traag
            officer.timeout_ms = 10
        elif i == veto:
            officer.deliberate.return_value = _verdict(
                officer.name,
                VerdictType.VETO,
                reason_code="PROMPT_INJECTION",
                reason_text="Onveilige input.",
            )
        elif i == crash:
            officer.deliberate.side_effect = RuntimeError("kapot")
        else:
            officer.deliberate.return_value = _verdict(officer.name, VerdictType.APPROVE)
    verdicts = await council._gather_verdicts(proposal, context)
    eind, _ = council._aggregate(verdicts, context)
    return verdicts, eind


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_officier_die_te_lang_doet_vraagt_een_mens_en_blokkeert_niet(
    council: AgentCouncil,
) -> None:
    verdicts, eind = await _beraadslaag(council, traag=0)

    traag = next(v for v in verdicts if v.reason_code == "TIMEOUT")
    assert (traag.verdict, traag.reason_text, eind) == (
        VerdictType.REQUIRE_HITL,
        f"ComplianceOfficer: {REDEN}",
        DecisionVerdict.HITL_REQUIRED,
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("positie", range(7))
async def test_een_tijdoverschrijding_keurt_nooit_goed_welke_officier_het_ook_is(
    council: AgentCouncil, positie: int
) -> None:
    _, eind = await _beraadslaag(council, traag=positie)

    assert eind not in (DecisionVerdict.APPROVED, DecisionVerdict.MODIFIED)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("positie", [0, 1, 3, 6])
async def test_een_tijdoverschrijding_van_een_officier_met_vetorecht_gaat_naar_een_mens(
    council: AgentCouncil, positie: int
) -> None:
    _, eind = await _beraadslaag(council, traag=positie)

    assert eind == DecisionVerdict.HITL_REQUIRED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_tijdoverschrijding_van_de_securityofficer_blijft_een_veto(
    council: AgentCouncil,
) -> None:
    """Security is de ENIGE die de rechten van de aanvrager toetst (Gate 2 security-review 2026-10-28): een ticket zonder
    die toets is uitvoerbaar door wie het goedkeurrecht heeft maar het recht zelf niet, dus zijn timeout blijft fail-secure."""
    verdicts, eind = await _beraadslaag(council, traag=2)

    traag = next(v for v in verdicts if v.reason_code == "TIMEOUT")
    assert (traag.officer_name, traag.verdict, eind) == (
        "SecurityOfficer",
        VerdictType.VETO,
        DecisionVerdict.BLOCKED,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_officier_zonder_vetorecht_blijft_bij_een_tijdoverschrijding_uitgesteld(
    council: AgentCouncil,
) -> None:
    """Geen ticketvloed: een waarschuwende officier (Ethics, Resource) die tikt maakt geen mensticket (oud gedrag)."""
    council._voting_officers[4].can_veto = False

    verdicts, eind = await _beraadslaag(council, traag=4)

    traag = next(v for v in verdicts if v.reason_code == "TIMEOUT")
    assert (traag.verdict, eind) == (VerdictType.REQUIRE_DEFERRAL, DecisionVerdict.DEFERRED)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_echte_veto_op_inhoud_blijft_een_veto(council: AgentCouncil) -> None:
    _, eind = await _beraadslaag(council, traag=None, veto=1)

    assert eind == DecisionVerdict.BLOCKED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_echte_veto_naast_een_tijdoverschrijding_blijft_geblokkeerd(
    council: AgentCouncil,
) -> None:
    _, eind = await _beraadslaag(council, traag=0, veto=1)

    assert eind == DecisionVerdict.BLOCKED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_een_crash_blijft_fail_secure_een_veto(council: AgentCouncil) -> None:
    verdicts, eind = await _beraadslaag(council, traag=None, crash=0)

    gecrasht = next(v for v in verdicts if v.reason_code == "INTERNAL_ERROR")
    assert (gecrasht.verdict, eind) == (VerdictType.VETO, DecisionVerdict.BLOCKED)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_zonder_tijdoverschrijding_of_veto_blijft_goedkeuren_goedkeuren(
    council: AgentCouncil,
) -> None:
    _, eind = await _beraadslaag(council, traag=None)

    assert eind == DecisionVerdict.APPROVED


@pytest.mark.unit
def test_de_uitleg_aan_de_klant_noemt_de_reden_van_het_uitstel() -> None:
    stemmen = (
        _verdict(
            "risk",
            VerdictType.REQUIRE_HITL,
            reason_code="TIMEOUT",
            reason_text=f"RiskOfficer: {REDEN}",
        ),
        _verdict("risk", VerdictType.APPROVE),
    )

    uitleg = AuditOfficer._generate_explanation(None, stemmen, DecisionVerdict.HITL_REQUIRED)  # type: ignore[arg-type]

    assert REDEN in uitleg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deliberate_geeft_het_uitstel_door_aan_de_afronding(council: AgentCouncil) -> None:
    """Heel `deliberate`: wat aan `_finalize` wordt doorgegeven is HITL_REQUIRED, niet BLOCKED of APPROVED."""
    proposal = _proposal()
    bouw_context = council._build_context

    async def _bouw_met_kort_beleid(voorstel: Proposal, *rest: object) -> object:
        context = await bouw_context(voorstel, *rest)
        _verkort_beleid(context)
        return context

    council._build_context = _bouw_met_kort_beleid  # type: ignore[method-assign,assignment]
    for i, officer in enumerate(council._voting_officers):
        if i == 3:
            officer.deliberate.side_effect = _traag
            officer.timeout_ms = 10
        else:
            officer.deliberate.return_value = _verdict(officer.name, VerdictType.APPROVE)

    async def _finalize(**kwargs: object) -> CouncilDecision:
        return CouncilDecision(
            proposal_id=proposal.proposal_id,
            tenant_id=proposal.tenant_id,
            user_id=proposal.user_id,
            verdict=kwargs["final_verdict"],  # type: ignore[typeddict-item]
            officer_verdicts=kwargs["officer_verdicts"],  # type: ignore[typeddict-item]
            explanation_for_user="OK",
            decision_hash="HASH",
            previous_decision_hash=None,
            deliberation_ms=10,
        )

    council._finalize = AsyncMock(side_effect=_finalize)

    besluit = await council.deliberate(proposal)

    assert besluit.verdict == DecisionVerdict.HITL_REQUIRED
