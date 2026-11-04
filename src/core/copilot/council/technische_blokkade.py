"""Wanneer een blokkade van de council technisch is en geen oordeel over het voorstel.

Een functionaris die een open circuit heeft of crasht, levert een synthetisch veto
(`coordinator._synthetic_verdict`); dat geldt ook voor een tijdoverschrijding van de SecurityOfficer. Een
tijdoverschrijding van een andere officier met vetorecht is sinds 2026-10-27 een mensticket (REQUIRE_HITL) en
komt hier niet langs. Dat veto blijft: fail-secure. Maar het zegt
niets over het VOORSTEL, en de klant hoort dat niet als "Council-verdict blocked" te lezen
(gemeten bij de acceptatie van 2026-10-22: vier keer geblokkeerd door een TIMEOUT van de
RiskOfficer). Het technische oordeel blijft in het log en in het logboek; alleen de tekst voor de
klant wordt gewone taal.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.core.copilot.council.types import OfficerVerdict, VerdictType

#: De redencodes die `coordinator._gather_verdicts` zelf toekent (niet de functionaris).
TECHNISCHE_REDENCODES = frozenset({"TIMEOUT", "CIRCUIT_BREAKER_OPEN", "INTERNAL_ERROR"})

#: De reden bij een TIJDOVERSCHRIJDING van een functionaris (brief 2026-10-27): de actie gaat niet geblokkeerd maar naar
#: een mens (HITL), met deze reden in de uitleg en in het ticket. Een tijdoverschrijding zegt niets over het voorstel.
REDEN_TIJDOVERSCHRIJDING = "De controle kon niet op tijd worden afgerond."

#: De officieren van wie een tijdoverschrijding een VETO blijft. SecurityOfficer is de ENIGE die toetst of de aanvrager
#: het recht voor de tool heeft (`user_has_scope_for`); bij goedkeuren van een HITL-ticket gebeurt die toets niet
#: opnieuw en zelfgoedkeuring is standaard toegestaan (Gate 2 security-review 2026-10-28, gelezen in
#: `hitl_router.py` en `hitl_repository.py`). Zou zijn tijdoverschrijding een mensticket worden, dan kan wie het
#: goedkeurrecht heeft maar het recht zelf mist, de timeout uitlokken en zijn eigen ticket goedkeuren.
OFFICIEREN_MET_VETO_BIJ_TIJDOVERSCHRIJDING = frozenset({"SecurityOfficer"})

KLANTTEKST_NIET_BEOORDEELD = (
    "Dit voorstel kon nu niet worden beoordeeld. Probeer het over een moment opnieuw."
)


def is_technisch_niet_beoordeeld(officer_verdicts: Iterable[OfficerVerdict]) -> bool:
    """True als er een technisch veto is en geen enkel echt veto van een functionaris.

    Een echt veto (bijvoorbeeld MISSING_SCOPE) naast een TIMEOUT houdt zijn eigen uitleg: de
    klant heeft recht op de inhoudelijke reden, en `opnieuw proberen` zou dan misleiden.
    """
    stemmen = list(officer_verdicts)
    technisch = any(
        v.reason_code in TECHNISCHE_REDENCODES and v.verdict is not VerdictType.APPROVE
        for v in stemmen
    )
    echt_veto = any(
        v.verdict is VerdictType.VETO and v.reason_code not in TECHNISCHE_REDENCODES
        for v in stemmen
    )
    return technisch and not echt_veto
