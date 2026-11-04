"""De council-auditrij bewaart geen klaartekst uit `action_params` (ADR-036 OP-33) of `message`
(ADR-036 D2-002/OP-38, fix-sprint dag 6).

**Een bewarende sink die LIVE is.** OP-27 hardde vijf bewarende plekken voor de tool-payload,
maar `git grep "audit_repository=\\|event_publisher="` over `src/` is leeg: vier van die vijf zijn
latent. Intussen gaat in `copilot/council/audit_writer.py` dezelfde dict die
`copilot/service.py:418-425` aan `execute_tool` geeft -- `proposal.action_params` -- verbatim in
`council_decisions.action_params` (JSONB, NOT NULL) en verbatim in `compute_canonical_json`, en dat
pad is volledig gewired via `copilot/dependencies.py:92`.

Deze alinea zei tot 2026-08-05 "de ZESDE sink, en de enige die vandaag live is". Dat was op beide
helften onjuist en is door de blinde review van ronde 7 betrapt: het zijn er zeven (OP-47 vond
`hitl_tickets.payload` via `copilot/service.py:528`, ook live, en RAUW), en er zijn er minstens
twee live. De actuele opsomming met de stand per plek staat in de moduledocstring van
`src/core/tool_broker/redaction.py` -- op EEN plek, zodat de volgende toevoeging niet weer op vier
plekken bijgewerkt moet worden.

**Twee deuren, een transactie.** Naast de rij zelf schrijft `persist()` ook
`OfficerVerdictRow.evidence`, en `privacy_officer.py:119-122` zet daar `params_tenant` in: een
waarde die RECHTSTREEKS uit `action_params` komt. De voordeur dichtdoen en die zijdeur als apart
OP-nummer wegzetten zou betekenen dat dezelfde waarde in kolom A gedigest is en in kolom B
leesbaar, aangelegd in dezelfde `session.commit()`.

**Wat hier NIET onder valt, en waarom dat gemeten is en niet aangenomen.** Alle evidence-velden van
de zeven officers zijn nagelopen met een AST-scan. Uitkomst: `pii_types` (privacy) bevat TYPEnamen
("email", "phone") en geen waarden; `patterns` (security) is de vaste literal
`["injection_pattern"]` uit `_PromptGuardAdapter.scan()`; `risk_officer` en `resource_officer`
bewaren getallen; `compliance_officer` een vaste tekst. Wat wel modeltekst bevat --
`ethics_officer`'s `modifications.reasoning` en `sanity_officer`'s `hallucination_reason` -- is
afgeleid van `proposal.reasoning` (niet `.message`, zie hieronder), en DIE staat nog steeds
onbewerkt in `council_decisions.reasoning`. Redigeren in evidence terwijl de kolom ernaast
dezelfde tekst onbewerkt draagt, sluit niets; dat is ADR-036 OP-38 en heeft een eigen afweging
nodig (het is art.-14-materiaal: `reasoning`/`explanation_for_user` worden rechtstreeks aan de
gebruiker geserveerd via `copilot/api/explanation_builder.py:38-39`, geverifieerd 2026-08-20). Deze
tests dekken dus precies wat uit `action_params` komt.

**Sinds fix-sprint dag 6 (2026-08-20) ook `message`.** `message` is de vrije babbeltekst van het
model naar de eindgebruiker (`proposal_builder.py:68`, `action.message`) -- GEEN
toezichts-/uitleg-materiaal: het staat in geen response-schema van `explanation_builder.py`, en
wordt uitsluitend gelezen door `chain_verifier.py`/`forensics.py`/`report_generator.py` voor
hash-herberekening. Bewust WEL geredigeerd, in tegenstelling tot `reasoning`/`explanation_for_user`
-- zie `TestTheMessageIsNotStoredVerbatim` hieronder. Rakesh's expliciete beslissing (2026-08-20),
na deze scope-vraag voorgelegd te krijgen: alleen `message` vandaag, `reasoning`/
`explanation_for_user` blijven OPEN onder OP-38.

**De valstrik in de fix.** Er zijn TWEE onafhankelijke verifiers die de hash herberekenen:
`audit/chain_verifier.py:92` en `audit/report_generator.py:72-100`. Beide reconstrueren uit
`row.action_params` en roepen `compute_canonical_json` opnieuw aan. Zou de redactie BINNEN
`compute_canonical_json` zitten, dan redigeren zij een al geredigeerde waarde nog eens, komen op
een andere hash uit, en melden ELKE historische rij als gemanipuleerd.
`test_a_verifier_recomputing_from_the_row_gets_the_stored_hash` legt dat vast.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)

TENANT = 7

#: Een persoonsgegeven dat BINNEN een toegelaten vorm past. Niet `jan.jansen@acme.nl`: die wordt
#: al op zijn tekens afgewezen en bewijst daarmee de tekenklasse in plaats van de eigenschap --
#: exact de vacuum-test die in ronde 3 151 tests groen hield met een BSN verbatim in de uitvoer.
PII_THAT_FITS_THE_SHAPE = "Jan_Jansen_salaris_82000"

#: Een tweede, met een andere vorm: dit is wat een model in een pagineersleutel kan zetten.
PII_AS_A_NUMBER = 82000


def _proposal(
    action_params: dict[str, Any],
    action_type: str = "update_task",
    proposal_id: UUID | None = None,
    message: str = "Ik heb de taak bijgewerkt.",
) -> Proposal:
    """Een voorstel zoals de copilot het bouwt.

    `action_type` is met opzet een ECHTE toolnaam: `copilot/service.py:418` geeft hem als
    `tool_name` aan `execute_tool`, dus `PAYLOAD_POLICY` geldt hier daadwerkelijk. Met een
    verzonnen naam zou de policy leeg zijn en werd alles gedigest -- dan bewijst de test niets over
    de policy en zou hij ook groen blijven bij "digest altijd alles", wat de functionaliteit sloopt.

    `message` is optioneel en standaard ongewijzigd (backward compatible) -- alleen de
    message-redactietests (ADR-036 D2-002/OP-38, fix-sprint dag 6) geven hier iets anders aan.
    """
    return Proposal(
        tenant_id=TENANT,
        user_id=3,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type=action_type,
        action_params=action_params,
        message=message,
        reasoning="De gebruiker vroeg om een statuswijziging.",
        data_classification=DataClassification.INTERNAL,
        confidence=0.9,
        model_id="deepseek-chat",
        model_version="v3",
        context_snapshot={},
        proposal_id=proposal_id or uuid4(),
    )



def _proposal_met_reasoning(reasoning: str) -> Proposal:
    """Een voorstel met een specifiek `reasoning`, om het lek in de evidence te kunnen aantonen."""
    from dataclasses import replace

    return replace(_proposal({"status": "todo"}), reasoning=reasoning)

def _verdict(evidence: dict[str, Any] | None = None) -> OfficerVerdict:
    return OfficerVerdict(
        officer_name="PrivacyOfficer",
        officer_version="1.0.0",
        verdict=VerdictType.APPROVE,
        reason_code="OK",
        reason_text="Geen bezwaar.",
        evidence=evidence or {},
        deliberation_ms=1,
        confidence=1.0,
    )


def _decision(proposal: Proposal, verdicts: tuple[OfficerVerdict, ...]) -> CouncilDecision:
    """Een besluit dat aan zijn voorstel gekoppeld is.

    `proposal_id=proposal.proposal_id` en niet een nieuwe UUID: zo doet productie het op alle drie
    de constructieplekken (`coordinator.py:365`, `service.py:327`, `audit_officer.py:169`). Met een
    losse UUID lijkt de hertelling-test hieronder te falen op de redactie, terwijl hij in
    werkelijkheid faalt op een `proposal_id` die niet bij de rij hoort -- een test die de verkeerde
    oorzaak aanwijst.
    """
    return CouncilDecision(
        proposal_id=proposal.proposal_id,
        tenant_id=TENANT,
        user_id=3,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=verdicts,
        explanation_for_user="Goedgekeurd.",
        decision_hash="",
        previous_decision_hash=None,
        deliberation_ms=5,
    )


class _FakeResult:
    def scalar_one_or_none(self) -> None:
        return None


class _FakeSession:
    """Genoeg sessie om `persist()` te laten lopen zonder database.

    `persist()` doet een advisory lock via `session.execute(text(...))` en leest de vorige hash met
    dezelfde methode; beide krijgen hier None terug, dus dit is de genesis-rij van de keten.
    """

    def __init__(self) -> None:
        self.added: list[Any] = []

    async def execute(self, *args: Any, **kwargs: Any) -> _FakeResult:
        return _FakeResult()

    def add(self, row: Any) -> None:
        self.added.append(row)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


def _writer(session: _FakeSession) -> Any:
    """Een writer op een nepsessie.

    De `arg-type`-ignore is dezelfde als in `audit/report_generator.py:77`: de signatuur vraagt een
    `AbstractAsyncContextManager[AsyncSession]` en `_FakeSession` is er een in gedrag maar niet in
    type. Gebundeld in een helper zodat er EEN ignore staat en niet drie.
    """
    from src.core.copilot.council.audit_writer import CouncilAuditWriter

    return CouncilAuditWriter(db_session_factory=lambda: session)  # type: ignore[arg-type]


async def _persist(
    action_params: dict[str, Any],
    evidence: dict[str, Any] | None = None,
    action_type: str = "update_task",
    message: str = "Ik heb de taak bijgewerkt.",
) -> tuple[Any, list[Any], tuple[OfficerVerdict, ...]]:
    """Persisteer een besluit en geef (decision_row, verdict_rows, verdicts) terug.

    De gebruikte `verdicts` komen mee omdat `compute_officer_verdicts_hash` over `asdict(v)`
    hasht, inclusief `verdict_id` -- en dat veld heeft een eigen default-factory. Een hertelling
    met nieuw gebouwde verdicts krijgt dus andere ids en daarmee een andere hash, zonder dat er
    iets met de redactie aan de hand is. `report_generator` haalt die ids uit
    `OfficerVerdictRow.verdict_id`; hier geven we dezelfde objecten terug, wat op het punt dat
    getoetst wordt (verandert de hash door de redactie?) hetzelfde is.
    """
    from src.core.governance.models import CouncilDecisionRow

    session = _FakeSession()
    writer = _writer(session)

    proposal = _proposal(action_params, action_type=action_type, message=message)
    verdicts = (_verdict(evidence),)
    decision = _decision(proposal, verdicts)

    await writer.persist(decision, proposal, verdicts)

    decision_rows = [r for r in session.added if isinstance(r, CouncilDecisionRow)]
    verdict_rows = [r for r in session.added if not isinstance(r, CouncilDecisionRow)]
    assert len(decision_rows) == 1, "persist() hoort precies een besluitrij toe te voegen"
    return decision_rows[0], verdict_rows, verdicts


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheRowCarriesNoCleartext:
    async def test_a_free_text_value_is_not_stored_verbatim(self) -> None:
        """De voordeur: `action_params` in de rij.

        Dit is de bevinding zelf. Dezelfde dict gaat naar `execute_tool`, dus elke waarde is door
        een taalmodel geschreven en dus aanvallerbeinvloed.
        """
        row, _, used_verdicts = await _persist(
            {"title": PII_THAT_FITS_THE_SHAPE, "status": "in_progress"}
        )

        rendered = json.dumps(row.action_params, default=str)
        assert PII_THAT_FITS_THE_SHAPE not in rendered, (
            "De klaartekst staat in council_decisions.action_params -- een JSONB-kolom in een "
            "onuitwisbare, hash-geketende tabel zonder wisroute (OP-36). Voor dezelfde uitvoering "
            "staat in tool_audit_logs.tool_input netjes een digest."
        )

    async def test_a_reviewed_enum_value_stays_readable(self) -> None:
        """En de fix mag niet "digest altijd alles" zijn.

        `status` is lid van een OPSOMMING (`TaskStatusLiteral`), dus die blijft leesbaar. Zonder
        deze test is de vorige test ook groen te krijgen door de hele kolom onleesbaar te maken --
        en dan is het auditspoor waardeloos en wordt de redactie uitgezet in plaats van vervuld.
        """
        row, _, used_verdicts = await _persist(
            {"title": PII_THAT_FITS_THE_SHAPE, "status": "in_progress"}
        )

        assert row.action_params.get("status") == "in_progress", (
            "Een gedeclareerde enum-waarde is gedigest. Dan is niet meer vast te stellen WAT er "
            "gevraagd werd, en dat is precies de toetsbaarheid die art. 12(2) van de logging "
            "verlangt."
        )

    async def test_a_number_a_model_chose_freely_is_not_stored_verbatim(self) -> None:
        """Een sleutel buiten het vocabulaire van de tool wordt naam EN waarde gedigest."""
        row, _, used_verdicts = await _persist({"salaris": PII_AS_A_NUMBER, "status": "todo"})

        rendered = json.dumps(row.action_params, default=str)
        assert "salaris" not in rendered, (
            "De door het model verzonnen SLEUTELNAAM staat verbatim in de auditrij. Een sleutel is "
            "net zo goed modeloutput als een waarde."
        )
        assert str(PII_AS_A_NUMBER) not in rendered, (
            "De waarde onder een niet-beoordeelde sleutel staat verbatim in de auditrij."
        )


#: Een `action_type` die GEEN sleutel is in `PAYLOAD_POLICY`. Dan geldt `_EMPTY_POLICY`
#: (`redaction.py:817-823`) en wordt naam EN waarde gedigest. Dit is de referentiemeting.
ACTION_TYPE_WITHOUT_A_POLICY = "definitely_not_a_tool"

#: Een `action_type` die WEL een sleutel is in `PAYLOAD_POLICY` en die de copilot ook mag
#: uitvoeren (`config/tool_permissions.yml:42`, profiel `copilot`, namespace `council_action`).
ALLOWED_ACTION_TYPE_WITH_A_POLICY = "list_tasks"

#: Een `action_type` die WEL een sleutel is in `PAYLOAD_POLICY` maar die de copilot NIET mag
#: uitvoeren: hij staat niet in `allowed_tools` van het `copilot`-profiel
#: (`config/tool_permissions.yml:33-56`).
#:
#: De naam ZEGT "vetoed" en dat is een bewering, niet een gegeven. Tot 2026-09-01 stond die
#: bewering alleen in deze comment en verzon de test hem aan beide kanten van de vergelijking.
#: Ze wordt nu GEMETEN door de ECHTE `SecurityOfficer` over dit scenario te laten lopen:
#: `test_the_real_security_officer_vetoes_this_action_type` hieronder.
VETOED_ACTION_TYPE_WITH_A_POLICY = "query_hr_database"


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheModelSelectsItsOwnRedactionPolicy:
    """ADR-036 OP-34, hermeten 2026-08-31: de policy-KEUZE komt uit ongevalideerde modeloutput.

    `audit_writer.py:163-168` gebruikt `proposal.action_type` als `tool_name`-opzoeksleutel voor
    `PAYLOAD_POLICY`. Die string is door het taalmodel geschreven (`proposal_builder.py:66`,
    `action_type=action.action or "noop"`) en de ENIGE beperking erop is een VORM:
    `schemas.py:58-63`, `max_length=64` en `pattern=r"^[a-z][a-z0-9_]*$"` (OP-78).

    Gemeten: alle 12 sleutels van `PAYLOAD_POLICY` passeren dat patroon. De vormbeperking sluit
    er dus NUL af -- zie `tests/architecture/test_council_action_type_policy_reachability.py`,
    dat die 12 vastpint.

    **Wat dat concreet oplevert, en wat NIET.** Wat leesbaar kan blijven is uitsluitend een lid
    van een OPSOMMING (`_one_of`) of een geheel getal binnen een GRENS (`_bounded_int`). Er is
    geen enkele `readable`-vorm die vrije tekst toelaat, en die eigenschap is de bovengrens van
    dit lek; hij wordt bewaakt door de guard hierboven genoemd. Een persoonsgegeven in TEKST
    komt hier dus niet leesbaar door -- alleen een door het model gekozen GETAL, en dat is
    precies de "bereik en geen opsomming"-observatie van OP-34.

    Deze klasse legt het gedrag VAST zoals het vandaag is (karakterisering, geen wens). De
    afweging staat in het rapport bij OP-34: de ernst is LAAG omdat dezelfde rij `action_type`
    zelf onbewerkt bewaart (`audit_writer.py:259`, kolom `String(128)`,
    `governance/models.py:781`) en `reasoning` onbewerkt (`audit_writer.py:279`, kolom `Text`,
    `governance/models.py:787`; `CopilotAction.reasoning` heeft geen `max_length`). Hoeveel dit
    verborgen kanaal precies is, staat hier niet als getal: het wordt GEMETEN en vastgepind door
    `tests/architecture/test_council_action_type_policy_reachability.py`
    (`PINNED_MAX_READABLE_BITS`, 28.8988 bits, gemeten 2026-09-01). Hier stond "~27 bits" en dat
    was de waarde van `query_hr_database` (26.5769), niet die van `list_tasks`; niemand kon hem
    herleiden omdat geen test hem berekende.

    **Mutatiebewijs (uitgevoerd 2026-08-31, in-memory, beide richtingen):**
      - `redaction.PAYLOAD_POLICY` op `{}` gezet, zodat geen enkele modelgekozen naam nog een
        policy selecteert -- de FIX-richting van OP-34: BEIDE tests ROOD.
      - `redaction._content_capture_enabled` op `True` gezet, zodat alles verbatim wordt
        opgeslagen: de eerste test ROOD op zijn REFERENTIE-assertie. Die assertie zit er precies
        daarvoor -- zonder hem zou "alles is leesbaar" deze tests groen houden en zouden ze het
        differentieel niet meer meten.
      - huidige staat: beide GROEN.
    """

    async def test_the_same_number_is_readable_or_digested_purely_by_the_models_action_type(
        self,
    ) -> None:
        """Het differentieel, in een test: dezelfde payload, twee `action_type`s.

        Dit is de kern van het bewijs. `PII_AS_A_NUMBER` staat onder `skip` -- en de docstring van
        die constante zegt al "dit is wat een model in een pagineersleutel kan zetten", terwijl
        geen enkele test hem tot nu toe ONDER zo'n sleutel zette.

        Dat 82000 binnen de leesbare grens van `list_tasks.skip` valt is hier GEEN redenering in
        een comment meer: `TestThePiiNumberSitsInsideTheReadableRange` hieronder leest die grens
        uit `PAYLOAD_POLICY` en wordt rood zodra de grens onder 82000 zakt.
        """
        zonder_policy, _, _ = await _persist(
            {"skip": PII_AS_A_NUMBER}, action_type=ACTION_TYPE_WITHOUT_A_POLICY
        )
        met_policy, _, _ = await _persist(
            {"skip": PII_AS_A_NUMBER}, action_type=ALLOWED_ACTION_TYPE_WITH_A_POLICY
        )

        assert str(PII_AS_A_NUMBER) not in json.dumps(zonder_policy.action_params, default=str), (
            "Referentiemeting kapot: een onbekende `action_type` hoort `_EMPTY_POLICY` te geven "
            "en dan wordt ALLES gedigest. Zonder dit verschil bewijst de assertie hieronder niets."
        )
        assert met_policy.action_params.get("skip") == PII_AS_A_NUMBER, (
            "Het differentieel is weg. Deze test karakteriseert ADR-036 OP-34: door zelf een "
            "`action_type` te kiezen die letterlijk een sleutel van PAYLOAD_POLICY is, maakt het "
            "model een getal leesbaar dat onder elke andere naam gedigest was. Is dit gedrag "
            "bewust gewijzigd, werk dan OP-34 in het ADR-036-register bij."
        )

    async def test_an_action_the_copilot_may_not_execute_still_gets_that_tools_policy(self) -> None:
        """De 8 sleutels die de copilot NIET mag uitvoeren krijgen toch hun eigen policy.

        `query_hr_database` staat niet in `allowed_tools` van het `copilot`-profiel
        (`config/tool_permissions.yml:33-55`), dus `security_officer.py:171` geeft een VETO en de
        beslissing wordt `BLOCKED` (`coordinator.py:350`). Toch loopt `_finalize`
        (`coordinator.py:199` -> `:389`) ZONDER verdict-controle door naar
        `audit_officer.py:195` -> `persist()`, en daar selecteert `proposal.action_type` alsnog de
        policy van `query_hr_database` -- inclusief `offset` leesbaar tot 100_000
        (`redaction.py:222`).

        Netto: een actie die is geweigerd en nooit is uitgevoerd, zet een door het model gekozen
        getal leesbaar in een hash-geketende, onuitwisbare rij. Dat is de scherpe helft van OP-34:
        bij de 4 toegestane taaktools is een leesbare `skip`/`limit` per ontwerp verdedigbaar,
        hier is er geen uitvoering om hem aan te verdedigen.
        """
        row, _, _ = await _persist(
            {"offset": PII_AS_A_NUMBER}, action_type=VETOED_ACTION_TYPE_WITH_A_POLICY
        )

        assert row.action_params.get("offset") == PII_AS_A_NUMBER, (
            "Gedrag gewijzigd: de policy van een niet-toegestane `action_type` wordt niet meer "
            "toegepast. Dat is de FIX-richting van OP-34 -- werk dan het register bij en verwijder "
            "deze karakterisering."
        )


class _NoInjectionPromptGuard:
    """Systeemgrens: de PromptGuard-adapter, op "geen injectie".

    Bewust op de NIET-vetoende uitkomst gezet. Zou hij injectie melden, dan geeft
    `security_officer.py:158-168` een VETO met `reason_code="PROMPT_INJECTION"` en zou de test
    hieronder een veto meten dat niets met de allowlist te maken heeft. De assertie eist daarom
    `TOOL_NOT_ALLOWLISTED` en niet alleen "een VETO" -- zo kan deze stub het antwoord niet
    verzinnen. De echte adapter (`factory.py:_PromptGuardAdapter`) vraagt `require_tenant_id()`
    op uit de ambient ContextVar en hoort niet in een unit-test.
    """

    def scan(self, text: str) -> dict[str, object]:
        return {"injection_detected": False, "patterns": []}


class _AllScopesRbac:
    """Systeemgrens: de RBAC-check, op "alle scopes aanwezig".

    Ook hier de niet-vetoende uitkomst, om dezelfde reden: `MISSING_SCOPE` zou een tweede,
    onbedoelde bron van een VETO zijn. De echte checker leest rollen uit de database.
    """

    async def user_has_scope_for(
        self, user_id: int, action_type: str, tenant_id: int | None = None
    ) -> bool:
        return True


def _deliberation_context() -> Any:
    from src.core.copilot.council.types import DeliberationContext

    return DeliberationContext(
        tenant_settings={},
        user_preferences={},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=500,
        request_id=uuid4(),
    )


def _real_security_officer() -> Any:
    """De ECHTE `SecurityOfficer` met de ECHTE allowlist-adapter.

    `_ToolBrokerAdapter` (`factory.py:131-151`) is het object dat productie hier gebruikt: het
    leest `config/tool_permissions.yml` via `ToolPermissionManager` en bevraagt het onder
    `agent_id="copilot"`. Geen mock, want juist de vraag "geeft dit profiel een VETO?" is wat
    gemeten moet worden -- een `AsyncMock` met `is_allowed.return_value = False` zou het antwoord
    dat de test zoekt zelf leveren.
    """
    from src.core.copilot.council.factory import _ToolBrokerAdapter
    from src.core.copilot.council.members.security_officer import SecurityOfficer

    return SecurityOfficer(_ToolBrokerAdapter(), _NoInjectionPromptGuard(), _AllScopesRbac())


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheRealSecurityOfficerAgreesWithTheseConstants:
    """De twee `action_type`-constanten hierboven zijn BEWERINGEN -- hier worden ze gemeten.

    ADR-036 OP-34, Gate 2-bevinding MEDIUM-4 (2026-09-01). De test hieronder
    (`test_an_action_the_copilot_may_not_execute_still_gets_that_tools_policy`) leunt erop dat
    `query_hr_database` wordt GEVETOD. Die aanname stond in een constante-naam en in een comment,
    en de test verzon hem daarmee aan beide kanten van de vergelijking -- dezelfde faalvorm die
    in dit project tweemaal onopgemerkt bleef (een goedkeuring die onverzilverbaar was, een
    planner die naar een geheugenwachtrij stuurde).

    Mutaties (uitgevoerd 2026-09-01, beide richtingen, op een KOPIE van
    `config/tool_permissions.yml`, een regel per element van {vetoed, allowed}):
      - `query_hr_database` AAN `allowed_tools` van het `copilot`-profiel toegevoegd
        -> `test_the_real_security_officer_vetoes_this_action_type` ROOD (gemeten APPROVE /
        COMPLIANT in plaats van VETO / TOOL_NOT_ALLOWLISTED).
      - `list_tasks` UIT `allowed_tools` gehaald
        -> `test_the_real_security_officer_does_not_veto_the_allowed_action_type` ROOD (gemeten
        VETO / TOOL_NOT_ALLOWLISTED). Dit is de tweede richting: zonder deze test zou "veto
        alles" beide constanten kloppend maken.
      - huidige staat: beide GROEN.
    """

    async def test_the_real_security_officer_vetoes_this_action_type(self) -> None:
        """Gemeten, niet aangenomen: dit profiel geeft op deze naam een allowlist-VETO."""
        from src.core.copilot.council.types import VerdictType

        verdict = await _real_security_officer().deliberate(
            _proposal({"offset": PII_AS_A_NUMBER}, action_type=VETOED_ACTION_TYPE_WITH_A_POLICY),
            _deliberation_context(),
        )

        assert (verdict.verdict, verdict.reason_code) == (
            VerdictType.VETO,
            "TOOL_NOT_ALLOWLISTED",
        ), (
            f"`{VETOED_ACTION_TYPE_WITH_A_POLICY}` levert nu "
            f"{verdict.verdict}/{verdict.reason_code} in plaats van een allowlist-VETO. Dan is de "
            "naam `VETOED_ACTION_TYPE_WITH_A_POLICY` onwaar en beschrijft de test hieronder niet "
            "meer de scherpe helft van OP-34 (een geweigerde actie die toch een leesbare rij "
            "krijgt). Staat de tool nu in het `copilot`-profiel, kies dan een andere naam die er "
            "niet in staat -- of, als er geen enkele meer is, haal de claim weg."
        )

    async def test_the_real_security_officer_does_not_veto_the_allowed_action_type(self) -> None:
        """De andere kant: een toegestane naam mag GEEN allowlist-VETO opleveren."""
        from src.core.copilot.council.types import VerdictType

        verdict = await _real_security_officer().deliberate(
            _proposal({"skip": PII_AS_A_NUMBER}, action_type=ALLOWED_ACTION_TYPE_WITH_A_POLICY),
            _deliberation_context(),
        )

        assert verdict.verdict is not VerdictType.VETO, (
            f"`{ALLOWED_ACTION_TYPE_WITH_A_POLICY}` wordt nu GEVETOD "
            f"({verdict.reason_code}), terwijl hij in `allowed_tools` van het `copilot`-profiel "
            "staat. Zonder deze richting zou een guard die ALLES vetot beide constanten "
            "kloppend maken."
        )

    async def test_the_permission_check_is_not_patched_here(self) -> None:
        """Vangnet: de meting hierboven mag niet door een fixture zijn uitgezet.

        Patroon uit `.claude/rules/quality-gates.md`. Een autouse-fixture die
        `ToolPermissionManager.is_tool_allowed` patcht (zoals in
        `tests/unit/test_tool_broker_hitl.py`) maakt de twee asserties hierboven vacuum: het
        veto komt dan uit de mock en niet uit `config/tool_permissions.yml`. Gemeten
        2026-09-01: geen conftest boven dit bestand patcht die functie.
        """
        from src.core.tool_broker.permission_manager import ToolPermissionManager

        controle = ToolPermissionManager.is_tool_allowed
        assert type(controle).__name__ == "function", (
            f"`ToolPermissionManager.is_tool_allowed` is hier een {type(controle).__name__} en "
            "geen gewone functie -- er patcht iets de allowlist-controle. Verplaats de metingen "
            "hierboven naar een module zonder die fixture; repareer ze niet ter plekke."
        )


#: De (tool, veld)-paren waarvan de tests in dit bestand aannemen dat `PII_AS_A_NUMBER` erbinnen
#: valt. Expliciet benoemd, zodat het mutatiebewijs een regel per element heeft.
RANGES_THESE_TESTS_RELY_ON: tuple[tuple[str, str], ...] = (
    (ALLOWED_ACTION_TYPE_WITH_A_POLICY, "skip"),
    (VETOED_ACTION_TYPE_WITH_A_POLICY, "offset"),
)


@pytest.mark.unit
class TestThePiiNumberSitsInsideTheReadableRange:
    """`PII_AS_A_NUMBER` is met de hand gekozen -- de relatie met de grens staat nu in code.

    ADR-036 OP-34, Gate 2-bevinding MEDIUM-6 (2026-09-01). De docstring van
    `test_the_same_number_is_readable_or_digested_purely_by_the_models_action_type` rekende
    "82000 <= 100_000" met de hand voor, maar niets asserteerde het. Zakt de grens in
    `PAYLOAD_POLICY` onder 82000, dan meet die test niets meer en zegt hij dat nergens.

    Mutaties (uitgevoerd 2026-09-01, beide richtingen, op een KOPIE van `redaction.py`, een regel
    per element van `RANGES_THESE_TESTS_RELY_ON`):
      - `list_tasks.skip` van `_bounded_int(100_000)` naar `_bounded_int(1_000)`
        -> `test_every_range_these_tests_rely_on_accepts_the_number` ROOD op `list_tasks.skip`.
      - `query_hr_database.offset` van `_bounded_int(100_000)` naar `_bounded_int(1_000)`
        -> ROOD op `query_hr_database.offset`.
      - de tweede richting: `list_tasks.skip` naar `_bounded_int(1_000_000)` -- ruimer, dus de
        testwaarde blijft geldig -> GROEN, en
        `test_the_number_is_not_readable_above_its_own_range` blijft ook GROEN omdat die de grens
        MEET in plaats van 100_000 te herhalen.
      - huidige staat: beide GROEN.
    """

    def test_every_range_these_tests_rely_on_accepts_the_number(self) -> None:
        """De grens komt uit `PAYLOAD_POLICY`, niet uit een comment."""
        from src.core.tool_broker.redaction import PAYLOAD_POLICY

        buiten = [
            f"{tool}.{veld}"
            for tool, veld in RANGES_THESE_TESTS_RELY_ON
            if not PAYLOAD_POLICY[tool].readable[veld](PII_AS_A_NUMBER)
        ]

        assert not buiten, (
            f"{buiten} accepteert {PII_AS_A_NUMBER} niet meer als leesbare waarde. De tests in "
            "dit bestand kiezen dat getal juist OMDAT het binnen de grens valt -- valt het "
            "erbuiten, dan wordt het gedigest en meten ze het differentieel van OP-34 niet meer. "
            "Kies een waarde binnen de nieuwe grens, en werk `PII_THAT_FITS_THE_SHAPE` mee bij: "
            "die draagt hetzelfde getal in zijn tekst."
        )

    def test_the_number_is_not_readable_above_its_own_range(self) -> None:
        """En de grens is echt een grens: ver erboven wordt niets meer geaccepteerd.

        Zonder deze helft zou een vorm die ELK getal doorlaat de test hierboven ook groen houden,
        en dan bewijst "82000 valt binnen de grens" niets over een grens.
        """
        from src.core.tool_broker.redaction import PAYLOAD_POLICY

        grenzeloos = []
        for tool, veld in RANGES_THESE_TESTS_RELY_ON:
            shape = PAYLOAD_POLICY[tool].readable[veld]
            hoog = max(PII_AS_A_NUMBER, 1)
            while shape(hoog) and hoog < 2**40:
                hoog *= 2
            if shape(hoog):
                grenzeloos.append(f"{tool}.{veld}")

        assert not grenzeloos, (
            f"{grenzeloos} accepteert nog waarden boven 2**40. Dan is de leesbare waarde geen "
            "begrensd getal meer en klopt de bovengrens in "
            "`tests/architecture/test_council_action_type_policy_reachability.py` niet meer "
            "(`PINNED_MAX_READABLE_BITS`)."
        )


#: Een persoonsgegeven in de vrije babbeltekst van het model, niet in `action_params`.
PII_IN_A_MESSAGE = "Bel Jan Jansen op 06-12345678 over dit voorstel."


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheMessageIsNotStoredVerbatim:
    """ADR-036 D2-002 (OP-38, fix-sprint dag 6): `message` is vrije modeltekst, net als
    `action_params`, en gaat verbatim de onuitwisbare hashketen in.

    **Waarom alleen `message` en niet `reasoning`/`explanation_for_user` (bewust, na overleg met
    Rakesh 2026-08-20).** `reasoning` en `explanation_for_user` worden rechtstreeks aan de
    eindgebruiker geserveerd via `copilot/api/explanation_builder.py:38-39`
    (`reasoning_summary=decision.reasoning`, `explanation_for_user=decision.explanation_for_user`)
    onder AI Act art. 13/14 (transparantie/menselijk toezicht) -- ze digesten zou die wettelijke
    uitlegbaarheid slopen. `message` staat in GEEN response-schema van die explainability-API
    (zelf gecontroleerd: `grep -n "message" src/core/copilot/api/schemas.py` binnen
    `DecisionExplanationResponse` geeft niets) en wordt uitsluitend gelezen door
    `chain_verifier.py`/`forensics.py`/`report_generator.py` voor hash-herberekening, nooit voor
    menselijke weergave. `reasoning`/`explanation_for_user` blijven daarom OPEN onder OP-38.
    """

    async def test_a_free_text_message_is_not_stored_verbatim(self) -> None:
        """De voordeur voor `message`: dezelfde klasse bevinding als `action_params` (OP-33)."""
        row, _, _used_verdicts = await _persist({"status": "todo"}, message=PII_IN_A_MESSAGE)

        assert PII_IN_A_MESSAGE not in row.message, (
            "De klaartekst staat in council_decisions.message -- een Text-kolom (NOT NULL) in "
            "een onuitwisbare, hash-geketende tabel zonder wisroute (OP-36)."
        )

    async def test_an_empty_message_stays_empty(self) -> None:
        """De lege default (`message=""`) mag niet gedigest worden.

        Een lege string bevat per definitie geen persoonsgegeven; digesten zou alleen een
        onleesbare HMAC-string opleveren voor de meest voorkomende waarde (elke aanroeper die
        `message` niet zet). Zonder deze test zou "altijd digesten, punt" ook groen zijn --
        functioneel correct voor PII maar een onnodige regressie voor het overgrote deel van de
        rijen.
        """
        row, _, _used_verdicts = await _persist({"status": "todo"}, message="")

        assert row.message == "", (
            "Een lege message werd gedigest tot een niet-lege HMAC-string. Dat is geen "
            "informatielek, maar wel een onnodige afwijking van de default voor elke rij die "
            "geen message meegeeft."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheMessageRedactionDoesNotAffectActionParams:
    """Regressie: de bestaande `action_params`-redactie (OP-33) mag niet dubbel of anders
    geredigeerd worden door het toevoegen van de message-redactie."""

    async def test_action_params_redaction_is_unchanged(self) -> None:
        row, _, _used_verdicts = await _persist(
            {"title": PII_THAT_FITS_THE_SHAPE, "status": "in_progress"},
            message=PII_IN_A_MESSAGE,
        )

        assert row.action_params.get("status") == "in_progress", (
            "De message-redactie heeft de bestaande action_params-redactie beinvloed -- een "
            "gedeclareerde enum-waarde is niet meer leesbaar."
        )
        rendered = json.dumps(row.action_params, default=str)
        assert PII_THAT_FITS_THE_SHAPE not in rendered, (
            "De message-redactie heeft de bestaande action_params-redactie beinvloed -- de "
            "vrije-tekst-waarde in action_params staat weer verbatim in de rij."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheCanonicalJsonCarriesNoCleartext:
    async def test_the_hashed_representation_is_redacted_too(self) -> None:
        """De canonical JSON wordt gehasht, maar de hash is niet het enige dat telt.

        `compute_canonical_json` bouwt de string waarover `decision_hash` wordt berekend. Zou daar
        de onbewerkte waarde in zitten terwijl de rij geredigeerd is, dan is de hash niet meer
        narekenbaar uit de rij -- en dan slaat elke verifier alarm op elke rij.
        """
        writer = _writer(_FakeSession())
        row, _, used_verdicts = await _persist(
            {"title": PII_THAT_FITS_THE_SHAPE, "status": "in_progress"}
        )

        canonical = writer.compute_canonical_json(
            proposal=_proposal(dict(row.action_params), proposal_id=row.proposal_id),
            officer_verdicts=used_verdicts,
            final_verdict=DecisionVerdict.APPROVED,
            previous_hash=None,
            explanation_for_user="Goedgekeurd.",
        )

        assert PII_THAT_FITS_THE_SHAPE not in canonical

    async def test_the_message_in_the_hashed_representation_is_redacted_too(self) -> None:
        """Dezelfde reden als hierboven, maar voor `message` (ADR-036 D2-002, dag 6)."""
        writer = _writer(_FakeSession())
        row, _, used_verdicts = await _persist({"status": "todo"}, message=PII_IN_A_MESSAGE)

        canonical = writer.compute_canonical_json(
            proposal=_proposal(
                dict(row.action_params), proposal_id=row.proposal_id, message=row.message
            ),
            officer_verdicts=used_verdicts,
            final_verdict=DecisionVerdict.APPROVED,
            previous_hash=None,
            explanation_for_user="Goedgekeurd.",
        )

        assert PII_IN_A_MESSAGE not in canonical


@pytest.mark.unit
@pytest.mark.asyncio
class TestAVerifierRecomputingFromTheRowGetsTheStoredHash:
    """De valstrik: redigeren op de verkeerde plek meldt elke historische rij als gemanipuleerd.

    Twee onafhankelijke verifiers herberekenen de hash uit `row.action_params`:
    `audit/chain_verifier.py:92` en `audit/report_generator.py:72-100`. Zit de redactie binnen
    `compute_canonical_json`, dan redigeren zij een al geredigeerde waarde nog eens en komen op een
    andere hash uit. Deze test is daarmee de reden dat de redactie op de AANROEPPLEK in `persist()`
    hoort en niet in de hashfunctie.
    """

    async def test_recomputing_the_hash_from_the_stored_row_matches(self) -> None:
        row, _, used_verdicts = await _persist(
            {"title": PII_THAT_FITS_THE_SHAPE, "status": "in_progress"}
        )

        writer = _writer(_FakeSession())
        # Precies zoals report_generator._verify_record: Proposal uit de RIJ reconstrueren.
        # `message=row.message` sinds fix-sprint dag 6 (ADR-036 D2-002): zonder dit zou de
        # reconstructie de DEFAULT message gebruiken in plaats van de daadwerkelijk opgeslagen
        # (sinds dag 6 geredigeerde) waarde, en dan komt de hertelling voor GEEN enkele rij meer
        # overeen -- niet omdat de redactie verkeerd staat, maar omdat deze reconstructiestap
        # zelf niet meer overeenkomt met wat `report_generator._reconstruct_proposal()` doet.
        canonical = writer.compute_canonical_json(
            proposal=_proposal(
                dict(row.action_params), proposal_id=row.proposal_id, message=row.message
            ),
            officer_verdicts=used_verdicts,
            final_verdict=DecisionVerdict(row.verdict),
            previous_hash=row.previous_decision_hash,
            explanation_for_user=row.explanation_for_user,
        )
        recomputed = writer.compute_decision_hash(canonical)

        assert recomputed == row.decision_hash, (
            "Een verifier die uit de opgeslagen rij herberekent komt op een andere hash uit dan "
            "wat er in de rij staat. Dan meldt chain_verifier en report_generator ELKE rij als "
            "gemanipuleerd. Zit de redactie in compute_canonical_json in plaats van op de "
            "aanroepplek in persist()? Dan wordt de al geredigeerde waarde nog eens geredigeerd."
        )

    async def test_recomputing_the_hash_from_the_stored_row_matches_with_a_redacted_message(
        self,
    ) -> None:
        """Dezelfde valstrik, nu voor `message` (ADR-036 D2-002, dag 6).

        `report_generator._reconstruct_proposal()` zet `message=row.message` -- dus deze test
        reconstrueert net als de echte verifier, MET de opgeslagen (geredigeerde) message, niet
        met de default uit `_proposal()`.
        """
        row, _, used_verdicts = await _persist({"status": "todo"}, message=PII_IN_A_MESSAGE)

        writer = _writer(_FakeSession())
        canonical = writer.compute_canonical_json(
            proposal=_proposal(
                dict(row.action_params), proposal_id=row.proposal_id, message=row.message
            ),
            officer_verdicts=used_verdicts,
            final_verdict=DecisionVerdict(row.verdict),
            previous_hash=row.previous_decision_hash,
            explanation_for_user=row.explanation_for_user,
        )
        recomputed = writer.compute_decision_hash(canonical)

        assert recomputed == row.decision_hash, (
            "Een verifier die de message uit de opgeslagen rij herberekent komt op een andere "
            "hash uit dan wat er in de rij staat -- exact de valstrik hierboven, nu voor message "
            "in plaats van action_params."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheOfficerEvidenceIsTheSideDoorOfTheSameTransaction:
    async def test_persist_writes_officer_evidence_through_unchanged(self) -> None:
        """`persist()` redigeert `evidence` NIET, en dat is een bewuste keuze.

        Het hele blok door de payload-redactie duwen zou reason codes, tellingen en
        lexiconversies onleesbaar maken -- legitiem auditbewijs dat geen persoonsgegeven is. De
        eigenschap wordt dus bij de BRON afgedwongen (de officer), en deze test legt vast dat
        `persist()` doorgeeft wat hij krijgt. Zo staat er zwart op wit waar de grens ligt en waarom
        `test_no_officer_puts_an_action_params_value_in_its_evidence` de eigenlijke vangrail is.
        """
        _, verdict_rows, _unused = await _persist(
            {"status": "todo"},
            evidence={"reason_detail": "counted 3 matches", "lexicon_version": "nl-1.2"},
        )

        assert [r.evidence for r in verdict_rows] == [
            {"reason_detail": "counted 3 matches", "lexicon_version": "nl-1.2"}
        ], (
            "persist() wijzigt de evidence van een officer. Als dat een redactie is: die hoort bij "
            "de bron, anders wordt onleesbaar wat juist het bewijs moet dragen."
        )

    async def test_the_privacy_officer_does_not_put_a_raw_param_value_in_evidence(self) -> None:
        """En bij de BRON: de officer hoort de waarde niet eens vast te leggen.

        `privacy_officer.py:119-122` zet `params_tenant` -- rechtstreeks
        `proposal.action_params.get("tenant_id")` -- in zijn evidence, op het VETO-pad voor een
        cross-tenant-poging. Dat is modeloutput: het kan elke string zijn.
        """
        from src.core.copilot.council.members.privacy_officer import PrivacyOfficer

        class _Enforcer:
            def detect_pii(self, data: dict[str, Any]) -> list[str]:
                return []

        officer = PrivacyOfficer(
            gdpr_enforcer=_Enforcer(),  # type: ignore[arg-type]
            consent_gate=object(),  # type: ignore[arg-type]
            twin_service=object(),  # type: ignore[arg-type]
        )
        proposal = _proposal({"tenant_id": PII_THAT_FITS_THE_SHAPE, "status": "todo"})

        verdict = await officer.deliberate(proposal, context=None)  # type: ignore[arg-type]

        rendered = json.dumps(verdict.evidence, default=str)
        assert verdict.verdict is VerdictType.VETO, (
            "De cross-tenant-poging hoort nog steeds een VETO te geven -- de fix mag de DETECTIE "
            "niet weghalen, alleen het vastleggen van de rauwe waarde."
        )
        assert PII_THAT_FITS_THE_SHAPE not in rendered, (
            "De officer legt de rauwe waarde uit action_params vast in zijn evidence. Leg de "
            "vergelijkingsUITKOMST vast, niet de waarde: dat het niet klopte is het bewijs, wat "
            "er precies stond is het persoonsgegeven."
        )


# ---------------------------------------------------------------------------------------------
# Golden vector -- Gate 2 ronde 6, F2
# ---------------------------------------------------------------------------------------------

#: Een VASTE sleutel, zodat de hash reproduceerbaar is. Hij haalt `key_strength_problem()`
#: (32 tekens, ruim genoeg verschillende tekens, geen blokherhaling) -- anders zou deze test de
#: sterkte-eis omzeilen en daarmee stilzwijgend toestaan dat die eis verslapt.
GOLDEN_KEY = "gV7pQ2mXzR4tL9nB6kW3sD8fH1jC5yA0"

GOLDEN_PROPOSAL_ID = UUID("11111111-2222-3333-4444-555555555555")
GOLDEN_PREVIOUS_HASH = "0" * 64
GOLDEN_EXPLANATION = "De taak is bijgewerkt."

#: De payload dekt met opzet alle DRIE de beslissingstakken van `redact_for_publication`, zodat een
#: wijziging in een van de drie deze vector breekt in plaats van er langs te glippen:
#:   - `task_id`  -- een UUID: WORDT gedigest (`_is_uuid` is in `ad3779a7` verwijderd);
#:   - `status`   -- lid van `TaskStatusLiteral`: blijft leesbaar;
#:   - `title`    -- vrije tekst: wordt gedigest;
#:   - `skip`     -- staat NIET in het vocabulaire van `update_task`, dus de sleutelNAAM zelf wordt
#:                   een pseudonym (`<k:...>`) en de waarde ook.
GOLDEN_ACTION_PARAMS: dict[str, Any] = {
    "task_id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
    "status": "in_progress",
    "title": PII_THAT_FITS_THE_SHAPE,
    "skip": PII_AS_A_NUMBER,
}

#: `OfficerVerdict.verdict_id` heeft `default_factory=uuid4`, en `compute_officer_verdicts_hash`
#: neemt via `asdict()` ALLE velden mee. Zonder een vaste waarde is de decision-hash dus per
#: constructie anders en is een golden vector onmogelijk. Dat is niet gedocumenteerd en het kostte
#: drie verschillende hashes in een proces om het te zien -- de reden dat dit hier expliciet staat.
GOLDEN_VERDICT_ID = UUID("99999999-8888-7777-6666-555555555555")

#: Vrije modeltekst met een persoonsgegeven, voor de message-redactie sinds fix-sprint dag 6
#: (ADR-036 D2-002/OP-38). Een EIGEN, vaste constante -- niet `PII_IN_A_MESSAGE` hergebruiken:
#: die kan onafhankelijk van deze vector wijzigen en zou de golden hash dan stilzwijgend
#: meeveranderen zonder dat dit bestand daarover iets zegt.
GOLDEN_MESSAGE = "Bel Jan Jansen op 06-12345678 over dit voorstel."

#: Berekend op 2026-08-20 (fix-sprint dag 6) met de bovenstaande constanten, INCLUSIEF
#: `GOLDEN_MESSAGE` -- zie de docstring van de testklasse voor wat deze ene waarde vastpint en
#: wat je moet doen als hij verandert. Was tot 2026-08-20
#: "6637a6923b9c7586f976904918810959cf06412b930c89b96e35cfe79f31d172" (zonder message-redactie);
#: die waarde veranderde LEGITIEM doordat `message` nu ook via `value_digest()` gaat in plaats
#: van ongewijzigd de canonieke JSON in te gaan.
GOLDEN_DECISION_HASH = "5277af91e6fd035c77c39cf45994f923b43dd6124df8a3adb3086a681e4f9672"


def _golden_verdict() -> OfficerVerdict:
    """Als `_verdict()`, maar met een VASTE `verdict_id` -- zie `GOLDEN_VERDICT_ID`."""
    return OfficerVerdict(
        officer_name="PrivacyOfficer",
        officer_version="1.0.0",
        verdict=VerdictType.APPROVE,
        reason_code="OK",
        reason_text="Geen bezwaar.",
        evidence={},
        deliberation_ms=1,
        confidence=1.0,
        verdict_id=GOLDEN_VERDICT_ID,
    )


def _golden_writer() -> Any:
    """Een writer zonder database: deze vector raakt alleen de twee zuivere hashfuncties."""
    from src.core.copilot.council.audit_writer import CouncilAuditWriter

    def _unused_factory() -> Any:  # pragma: no cover - wordt nooit aangeroepen
        raise AssertionError("de golden vector mag de database niet raken")

    return CouncilAuditWriter(db_session_factory=_unused_factory)  # type: ignore[arg-type]


def _golden_hash(action_params: dict[str, Any], message: str = GOLDEN_MESSAGE) -> str:
    """De hash zoals `persist()` hem berekent: redigeren (action_params EN message, sinds
    fix-sprint dag 6), dan canoniek, dan SHA-256.

    `message` is optioneel en standaard `GOLDEN_MESSAGE` -- backward compatible met de
    bestaande `test_a_second_redaction_pass_produces_a_different_hash`, die alleen
    `action_params` varieert en op de default message moet blijven vergelijken.
    """
    from dataclasses import replace

    from src.core.tool_broker.redaction import redact_for_publication, value_digest

    proposal = _proposal(action_params, proposal_id=GOLDEN_PROPOSAL_ID, message=message)
    published_params = redact_for_publication(
        proposal.action_type,
        proposal.action_params,
        tenant_id=proposal.tenant_id,
        broker_keys=frozenset(),
    )
    published_message = (
        value_digest(proposal.message, tenant_id=proposal.tenant_id) if proposal.message else ""
    )
    writer = _golden_writer()
    canonical = writer.compute_canonical_json(
        replace(proposal, action_params=published_params, message=published_message),
        (_golden_verdict(),),
        DecisionVerdict.APPROVED,
        GOLDEN_PREVIOUS_HASH,
        GOLDEN_EXPLANATION,
    )
    return str(writer.compute_decision_hash(canonical))


class TestTheDecisionHashIsPinnedToAGoldenVector:
    """Een vaste sleutel, een vast voorstel, een vastgelegde hash.

    **Waarom deze test bestaat (Gate 2 ronde 6, F2).** De docstring van `persist()` eist dat de
    redactie op de AANROEPPLEK staat en NOOIT in `compute_canonical_json()`. Die eis werd door geen
    enkele test afgedwongen: de reviewer zette de redactie ook binnen de hashfunctie en alle 35
    tests in dit bestand bleven groen -- inclusief
    `TestAVerifierRecomputingFromTheRowGetsTheStoredHash`. De reden is dat die test schrijft EN
    verifieert met dezelfde codeversie, dus een dubbele redactie valt aan beide kanten weg.

    Voor rijen die al in de database staan valt hij niet weg. Daar zou zo'n wijziging
    `chain_verifier.verify_tenant_chain` en `report_generator._verify_record`
    `record_content_tampered` laten melden op ELKE bestaande `council_decisions`-rij, en het
    ADR-019-compliancerapport zou de keten van iedere tenant gebroken verklaren.

    Een vector tegen een LITERAL is de enige vorm die dat betrapt, want hij vergelijkt niet met
    zichzelf. Wat deze ene waarde vastpint:
      - de plaats van de redactie en het aantal passes (de redactie is niet idempotent);
      - de scrypt-parameters en de salt;
      - het HMAC-domein en de `:v2`-versiebump;
      - de vorm van de canonieke JSON: sleutelvolgorde, separators, afronding van `confidence`.

    **Verandert deze hash?** Dan is een van die eigenschappen gewijzigd. Dat MAG, maar niet
    stilzwijgend: elke wijziging maakt alle bestaande rijen onverifieerbaar en vraagt dus een
    migratiebesluit van Rakesh plus een domeinbump. Pas de literal niet aan om de test groen te
    krijgen zonder dat besluit.

    **Uitgebreid 2026-08-20 (fix-sprint dag 6, ADR-036 D2-002/OP-38) met `message`.** Gate 2's
    security-reviewer bewees dat DEZE vector voor die dag geen enkele dekking bood voor de
    message-redactie: `_golden_hash()` riep `persist()` nooit aan en redigeerde `message` dus
    nergens, ook niet na de fix -- exact dezelfde blinde vlek als de Gate-2-ronde-6-vondst
    hierboven, nu voor een ANDER veld. `GOLDEN_MESSAGE` en `GOLDEN_DECISION_HASH`
    zijn dienovereenkomstig
    bijgewerkt (met Rakesh's akkoord voor de message-redactie zelf, 2026-08-20 -- geen apart
    domeinbump nodig, want de scrypt-parameters/het HMAC-domein zijn ongewijzigd; alleen de
    WAARDE van het gehashte `message`-veld verandert, van klaartekst naar digest).
    """

    @pytest.fixture(autouse=True)
    def _fixed_key(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        from src.core.tool_broker import redaction

        monkeypatch.setattr(redaction, "_configured_key", lambda: GOLDEN_KEY)
        redaction.reset_key_cache()
        yield
        redaction.reset_key_cache()

    def test_the_golden_key_itself_passes_the_strength_rule(self) -> None:
        """Anders zou deze test de sterkte-eis omzeilen en verslapping onzichtbaar maken."""
        from src.core.tool_broker.redaction import key_strength_problem

        assert key_strength_problem(GOLDEN_KEY) is None

    def test_the_decision_hash_matches_the_recorded_vector(self) -> None:
        assert _golden_hash(GOLDEN_ACTION_PARAMS) == GOLDEN_DECISION_HASH, (
            "De canonieke hash van een VAST voorstel is veranderd. Dat betekent dat een van deze "
            "dingen is gewijzigd: de plaats van de redactie (hoort op de aanroepplek in persist(), "
            "NOOIT in compute_canonical_json), het aantal redactiepasses, de scrypt-parameters, de "
            "salt, het HMAC-domein, of de vorm van de canonieke JSON. Elk daarvan maakt ALLE "
            "bestaande council_decisions-rijen onverifieerbaar: chain_verifier en report_generator "
            "herberekenen uit row.action_params en melden dan record_content_tampered. Pas de "
            "literal niet aan zonder migratiebesluit van Rakesh en een domeinbump."
        )

    def test_a_second_redaction_pass_produces_a_different_hash(self) -> None:
        """Bewijst dat de vector niet vacuum is.

        Zou de redactie idempotent zijn, dan zou een tweede pass dezelfde hash geven en zou deze
        vector de fout die hij moet betrappen niet zien. De idempotentiecheck is in ronde 2 bewust
        verwijderd (een al geredigeerde waarde is niet te onderscheiden van modeloutput die er zo
        uitziet), en dat is precies waarom een dubbele pass gevaarlijk is.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        once = redact_for_publication(
            "update_task", GOLDEN_ACTION_PARAMS, tenant_id=TENANT, broker_keys=frozenset()
        )
        assert _golden_hash(once) != GOLDEN_DECISION_HASH, (
            "Een tweede redactiepass geeft dezelfde hash. Dan is de redactie idempotent geworden "
            "en betrapt de golden vector een redactie binnen compute_canonical_json niet meer."
        )

    def test_a_second_redaction_pass_of_the_message_produces_a_different_hash(self) -> None:
        """Zelfde bewijs als hierboven, nu voor `message` (ADR-036 D2-002, fix-sprint dag 6).

        Zonder deze test zou de message-golden-vector zelf "vacuum" kunnen zijn: hij zou ook
        slagen als iemand de message-redactie per ongeluk weglaat EN als iemand hem er per
        ongeluk twee keer op toepast, zolang de literal maar toevallig klopt met een van de
        twee. Deze test bewijst specifiek dat een tweede pass op `message` een ANDERE hash
        geeft dan de vastgepinde vector.
        """
        from src.core.tool_broker.redaction import value_digest

        once = value_digest(GOLDEN_MESSAGE, tenant_id=TENANT)
        assert _golden_hash(GOLDEN_ACTION_PARAMS, message=once) != GOLDEN_DECISION_HASH, (
            "Een tweede redactiepass op message geeft dezelfde hash. Dan is de message-redactie "
            "idempotent geworden en betrapt de golden vector een redactie binnen "
            "compute_canonical_json voor message niet meer."
        )


@pytest.mark.unit
class TestTheEthicsOfficerDoesNotStoreTheWholeReasoning:
    """De bron, niet de doorgeefluik (ADR-036 OP-95).

    **Waarom hier en niet in `persist()`.** De test hierboven legt een bewuste
    keuze vast: `persist()`
    redigeert `evidence` NIET, want het hele blok door de payload-redactie duwen maakt reason codes,
    tellingen en lexiconversies onleesbaar -- legitiem auditbewijs dat geen persoonsgegeven is. De
    eigenschap hoort dus bij de officer. Ik heb dat eerst wel in `persist()` geprobeerd; die test
    ving het, en dat was terecht.

    **Wat er lekte.** `_build_modify_verdict()` zette `evidence["modifications"]["reasoning"]` op de
    VOLLEDIGE `proposal.reasoning` -- tot 10.000 tekens door een taalmodel geschreven tekst, waarin
    alleen de gevonden bias-termen door een marker zijn vervangen. Dat gaat via
    `compute_officer_verdicts_hash()` mee in `decision_hash` en dus in de ADR-019-keten, die per
    ontwerp onuitwisbaar is. Een blinde securityreview vond dit; zelf nagemeten.

    Wat het toezicht nodig heeft is: DAT er is aangepast, hoeveel, en een narekenbare verwijzing --
    niet de tekst zelf.
    """

    def test_the_evidence_does_not_contain_the_reasoning_text(self) -> None:
        from src.core.copilot.council.members.ethics_officer import EthicsOfficer

        geheim = "medewerker jan.jansen@klant.nl presteert ondermaats en is te oud"
        officer = EthicsOfficer()
        verdict = officer._build_modify_verdict(
            proposal=_proposal_met_reasoning(geheim),
            language="nl",
            high_matches=["te oud"],
            medium_matches=[],
            reason_code="BIAS_DETECTED",
        )

        gestort = json.dumps(verdict.evidence, default=str)
        assert "jan.jansen@klant.nl" not in gestort, (
            "De onderbouwing bevat het volledige `reasoning` van het model, inclusief wat daar aan "
            "persoonsgegevens in stond. Dat wordt meegehasht in de onuitwisbare keten."
        )
        assert "presteert ondermaats" not in gestort, (
            "Alleen de bias-TERMEN worden vervangen; de rest van de modeltekst blijft staan."
        )

    def test_the_evidence_still_carries_what_oversight_needs(self) -> None:
        """Vangnet: alles weggooien zou de test hierboven ook groen maken.

        Zonder deze assertie is "laat evidence leeg" een geldige oplossing, en dan kan een auditor
        niet meer zien waarom dit raadslid ingreep.
        """
        from src.core.copilot.council.members.ethics_officer import EthicsOfficer

        verdict = EthicsOfficer()._build_modify_verdict(
            proposal=_proposal_met_reasoning("iets met te oud erin"),
            language="nl",
            high_matches=["te oud"],
            medium_matches=[],
            reason_code="BIAS_DETECTED",
        )

        assert verdict.evidence.get("high_matches") == ["te oud"], (
            "De gevonden termen zijn weg. Dat is juist het bewijs waarom er is ingegrepen."
        )
        assert verdict.evidence.get(
            "lexicon_version"
        ), "De lexiconversie hoort narekenbaar te zijn."
