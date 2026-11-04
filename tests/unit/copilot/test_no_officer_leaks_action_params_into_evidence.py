"""Geen officer legt een waarde uit `action_params` vast in zijn evidence (ADR-036 OP-33).

**Waarom dit een eigen, generieke guard is.** `persist()` pseudonimiseert sinds OP-33 de
`action_params` van het voorstel, maar schrijft in DEZELFDE transactie ook
`OfficerVerdictRow.evidence` weg -- onbewerkt, en meegehasht in `compute_officer_verdicts_hash`.
`privacy_officer.py` zette daar de rauwe `action_params["tenant_id"]` in. Die ene plek is gefixt,
maar een fix zonder guard betekent dat de volgende officer het opnieuw doet en dat niemand het
merkt: de voordeur dicht, de zijdeur open, in een onuitwisbare tabel zonder wisroute (OP-36).

**Waarom bij de bron en niet in `persist()`.** Het hele evidence-blok door de payload-redactie
duwen maakt reason codes, tellingen en lexiconversies onleesbaar -- dat is legitiem auditbewijs en
geen persoonsgegeven. Een guard die alles verwerpt wordt uitgezet, niet vervuld.

**Waarom gedrag en geen naamscan.** Een AST-scan op `evidence=`-dicts die `action_params`
noemen is precies de naamlijst die in deze reeks vier keer een token te kort was. Deze test voert
elke officer UIT met een merkwaarde in `action_params` en kijkt of die waarde in de uitkomst
terugkomt. Dat werkt ook als iemand de waarde via drie tussenvariabelen doorgeeft.

**Dekking is expliciet, niet toevallig.** `test_every_officer_is_covered_or_explicitly_excluded`
ontdekt alle `Officer`-subklassen en eist dat elke klasse ofwel getoetst wordt, ofwel met een reden
op de uitsluitingslijst staat. Een NIEUWE officer dwingt daarmee een beslissing af in plaats van
stil buiten de guard te vallen -- de les uit par. 6.5 van de overdracht (een vangnet per bewaakt
item, niet per voorbeeld).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

from src.core.copilot.council.types import (
    DataClassification,
    DeliberationContext,
    Proposal,
    ProposalTrigger,
)

TENANT = 11

#: De merkwaarde. Past binnen elke toegelaten vorm (letters, cijfers, liggende streepjes) en is
#: toch een persoonsgegeven -- de les uit ronde 3: een detectiewaarde die al op zijn TEKENS wordt
#: afgewezen bewijst de tekenklasse en niet de eigenschap.
MARKER = "Jan_Jansen_salaris_82000"

#: Officers die deze guard niet uitvoert, met reden. Gedateerd.
#: Hoeveel `Officer`-subklassen er zijn. Gemeten 2026-08-05 met een RECURSIEVE walk over
#: `__subclasses__()`. Een exact getal en geen ondergrens: met `>= 7` hield ook een VERWIJDERDE
#: officer deze guard groen, en dan verdwijnt zijn dekking zonder dat iets klaagt (ADR-036 OP-50).
#: Verandert dit getal, dan hoort er een beslissing bij -- gedekt of expliciet uitgesloten.
EXPECTED_OFFICER_COUNT = 8

EXCLUDED_OFFICERS: dict[str, str] = {
    "AuditOfficer": (
        "2026-08-04 -- vereist een CouncilAuditWriter met databasesessie; zijn evidence is "
        "gemeten leeg ({} op audit_officer.py:106) en hij leest action_params niet."
    ),
    "RiskOfficer": (
        "2026-08-04 -- vereist een ShadowCEO-adapter. Zijn evidence is gemeten uitsluitend "
        "shadow_ceo_score en actor_history_count, beide getallen."
    ),
    "ResourceOfficer": (
        "2026-08-04 -- vereist een BudgetManager met Redis. Zijn evidence is gemeten uitsluitend "
        "budget_remaining, een getal."
    ),
}


def _context() -> DeliberationContext:
    return DeliberationContext(
        tenant_settings={},
        user_preferences={},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=1_000,
        request_id=uuid4(),
    )


def _proposal_with_marker(action_type: str) -> Proposal:
    """Een voorstel met de merkwaarde op drie plekken in `action_params`.

    Sleutelnaam, waarde en een geneste structuur -- want een officer kan elk van die drie
    oppikken.
    """
    return Proposal(
        tenant_id=TENANT,
        user_id=4,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type=action_type,
        action_params={
            "tenant_id": MARKER,
            MARKER: "value",
            "nested": {"deep": MARKER},
            "status": "todo",
        },
        message="Bericht aan de gebruiker.",
        reasoning="Omdat de gebruiker het vroeg.",
        data_classification=DataClassification.INTERNAL,
        confidence=0.9,
        model_id="deepseek-chat",
        model_version="v3",
        context_snapshot={},
    )


def _constructible_officers() -> dict[str, Any]:
    """De officers die zonder database gebouwd kunnen worden.

    De vier factory-singletons bouwen met null-adapters; PrivacyOfficer krijgt stubs. Dit is de
    verzameling die `test_every_officer_is_covered_or_explicitly_excluded` afzet tegen alle
    bestaande `Officer`-subklassen.
    """
    from src.core.copilot.council import factory
    from src.core.copilot.council.members.privacy_officer import PrivacyOfficer

    class _Enforcer:
        def detect_pii(self, data: dict[str, Any]) -> list[str]:
            return []

    officers: dict[str, Any] = {
        "EthicsOfficer": factory._get_ethics_officer(),
        "SanityOfficer": factory._get_sanity_officer(),
        "ComplianceOfficer": factory._get_compliance_officer(),
        "SecurityOfficer": factory._get_security_officer(),
        "PrivacyOfficer": PrivacyOfficer(
            gdpr_enforcer=_Enforcer(),  # type: ignore[arg-type]
            consent_gate=object(),  # type: ignore[arg-type]
            twin_service=object(),  # type: ignore[arg-type]
        ),
    }
    return officers


def _all_officer_class_names() -> set[str]:
    """Alle `Officer`-subklassen, uit de BRON, RECURSIEF.

    Via import van het members-pakket en een recursieve walk over `__subclasses__()`, zodat een
    nieuw bestand automatisch meekomt. Een handmatige lijst zou hier precies de steekproef zijn die
    deze guard wil vermijden.

    **Recursief en niet alleen direct (ADR-036 OP-50, ronde 7).** `Officer.__subclasses__()` geeft
    uitsluitend DIRECTE subklassen. Vandaag levert dat hetzelfde aantal op als een volledige walk
    (gemeten: 8 in beide gevallen), dus er was geen actueel gat -- maar
    `class HRPrivacyOfficer(PrivacyOfficer)` die `action_params["employee_id"]` in zijn evidence
    zet, zou niet ontdekt worden en `test_every_officer_is_covered_or_explicitly_excluded` zou
    groen blijven. Dan staat de zijdeur uit OP-33 weer open, met klaartekst in een hash-geketende
    tabel.
    """
    import importlib
    import pkgutil

    import src.core.copilot.council.members as members_pkg
    from src.core.copilot.council.members.base import Officer

    for module in pkgutil.iter_modules(members_pkg.__path__):
        importlib.import_module(f"{members_pkg.__name__}.{module.name}")

    found: set[str] = set()

    def _walk(cls: type) -> None:
        for subclass in cls.__subclasses__():
            if subclass.__name__ not in found:
                found.add(subclass.__name__)
                _walk(subclass)

    _walk(Officer)
    return found


@pytest.mark.unit
class TestCoverageIsExplicit:
    def test_the_discovery_finds_the_officers(self) -> None:
        """Vangnet: vindt de ontdekking uberhaupt officers?

        Zonder deze test maakt een verkeerd pakketpad de guard stil groen -- dan is de
        verzameling leeg en klaagt niets.
        """
        found = _all_officer_class_names()

        # `== EXPECTED_OFFICER_COUNT` en niet `>= 7` (ADR-036 OP-50, ronde 7). Met een
        # ondergrens die EEN lager ligt dan de werkelijkheid houdt ook een VERWIJDERDE officer
        # deze guard groen -- en dan verdwijnt zijn dekking zonder dat iets klaagt. Een exact
        # getal dwingt bij elke wijziging een beslissing af; dat is het doel van dit vangnet.
        assert len(found) == EXPECTED_OFFICER_COUNT, (
            f"{len(found)} Officer-subklassen gevonden: {sorted(found)}. Verwacht: "
            f"{EXPECTED_OFFICER_COUNT}. Is er een officer toegevoegd of verwijderd, werk dan "
            "EXPECTED_OFFICER_COUNT bij EN beslis of hij gedekt of expliciet uitgesloten is. Is het "
            "members-pakket verplaatst, dan bewaakt deze guard niets."
        )

    def test_every_officer_is_covered_or_explicitly_excluded(self) -> None:
        """Een nieuwe officer dwingt een beslissing af."""
        found = _all_officer_class_names()
        covered = set(_constructible_officers())
        unaccounted = sorted(found - covered - set(EXCLUDED_OFFICERS))

        assert not unaccounted, (
            f"Deze officers vallen buiten de guard: {unaccounted}. Voeg ze toe aan "
            "_constructible_officers() (met stubs voor hun dependencies), of zet ze met datum en "
            "reden in EXCLUDED_OFFICERS. Een officer die stil buiten de guard valt, kan een waarde "
            "uit action_params in zijn evidence zetten zonder dat iets het merkt."
        )

    def test_the_exclusion_list_has_no_stale_entries(self) -> None:
        """Een uitsluiting voor een officer die niet meer bestaat, hoort weg."""
        found = _all_officer_class_names()
        stale = sorted(name for name in EXCLUDED_OFFICERS if name not in found)

        assert not stale, (
            f"Deze uitsluitingen verwijzen naar officers die niet bestaan: {stale}. Haal ze uit "
            "EXCLUDED_OFFICERS, anders dekt de lijst op termijn iets anders dan hij beweert."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestNoOfficerLeaksActionParams:
    @pytest.mark.parametrize("officer_name", sorted(_constructible_officers()))
    @pytest.mark.parametrize("action_type", ["update_task", "export_report", "send_notification"])
    async def test_no_officer_puts_an_action_params_value_in_its_evidence(
        self, officer_name: str, action_type: str
    ) -> None:
        """Drie actietypen, want de meeste officers takken op de actienaam af.

        `export_report` en `send_notification` raken de PII-plus-export-tak van de PrivacyOfficer en
        de disclosure-tak van de ComplianceOfficer; `update_task` is het gewone pad.
        """
        from src.core.middleware.tenant_context import set_tenant_id

        set_tenant_id(TENANT)
        officer = _constructible_officers()[officer_name]
        proposal = _proposal_with_marker(action_type)

        try:
            verdict = await officer.deliberate(proposal, _context())
        except Exception as exc:  # noqa: BLE001 -- zie melding
            pytest.fail(
                f"{officer_name} gooide {type(exc).__name__}: {exc}. Deze guard moet de officer "
                "kunnen UITVOEREN om te zien wat hij vastlegt; geef hem een werkende stub of zet "
                "hem met reden in EXCLUDED_OFFICERS. Een officer die hier crasht is niet getoetst."
            )

        rendered = json.dumps(verdict.evidence, default=str)
        assert MARKER not in rendered, (
            f"{officer_name} legt een waarde uit action_params vast in zijn evidence "
            f"({verdict.evidence!r}). Die evidence gaat via persist() onbewerkt naar "
            "OfficerVerdictRow.evidence en wordt meegehasht -- in dezelfde transactie waarin "
            "action_params sinds OP-33 juist WEL gepseudonimiseerd wordt. Leg de UITKOMST vast "
            "(dat het niet klopte, welk type het was), niet de waarde."
        )
