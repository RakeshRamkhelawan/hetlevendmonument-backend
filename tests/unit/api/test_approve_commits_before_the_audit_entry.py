"""De verzilvering wordt vastgelegd VOOR de auditregel (ADR-036 OP-100).

**Hoe dit gevonden is.** De blinde securityreview van 2026-08-08, aangetoond tegen een echte
database. De volgorde in `approve_hitl_request` was: goedkeuring vastleggen -> uitvoeren (de poort
verzilvert het ticket in DEZELFDE sessie, nog niet vastgelegd) -> de ADR-019-regel schrijven binnen
`best_effort`.

`best_effort` rolt de sessie terug bij een fout. Dat is zijn hele doel -- een auditregel mag de
primaire handeling nooit blokkeren -- maar daarmee rolde hij ook de verzilvering terug. Het ticket
sprong terug op `approved`, er was geen auditregel, en de goedkeuring was binnen 24 uur opnieuw te
verzilveren door de oorspronkelijke aanvrager, die de ticketverwijzing in zijn eigen antwoord
terugkrijgt. De eenmaligheid uit OP-63/OP-75 hing dus aan iets dat per definitie mag falen.

**Waarom deze test op de VOLGORDE toetst en niet op het gedrag.** De integratietest
`TestAFailingAuditWriteDoesNotUnconsumeTheApproval` toont het mechanisme: zonder commit rolt de
verzilvering mee terug, met commit niet. Maar die test commit ZELF, en kan dus niet zien of de
PRODUCTIECODE dat ook doet. Dat is precies de vorm die deze week zeven keer hol bleek -- een test
die zijn eigen invoer levert en daarmee alleen zichzelf bewijst.

Deze test leest de bronvolgorde van de handler, met de AST, en dwingt af dat er een `commit()`
staat tussen de uitvoering en de auditregel.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ROUTER = REPO_ROOT / "src/core/api/v1/tool_broker/hitl_router.py"


def _handler(naam: str) -> ast.AsyncFunctionDef:
    boom = ast.parse(ROUTER.read_text(encoding="utf-8"))
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.AsyncFunctionDef) and knoop.name == naam:
            return knoop
    pytest.fail(f"handler {naam!r} niet gevonden -- hernoemd? Dan bewaakt deze test niets.")


def _regel_van_eerste_aanroep(functie: ast.AsyncFunctionDef, gezocht: str) -> int | None:
    """Het regelnummer van de eerste aanroep van `gezocht` in deze functie.

    Bewust `ast.Call` en niet `ast.dump()` doorzoeken: die laatste rendert ook de DOCSTRING, dus
    een functie die de naam alleen in haar toelichting noemt zou de toets al halen. Die vorm is in
    deze codebase op drie plekken aangetroffen (ADR-036 OP-101).
    """
    for knoop in ast.walk(functie):
        if not isinstance(knoop, ast.Call):
            continue
        doel = knoop.func
        naam = doel.attr if isinstance(doel, ast.Attribute) else getattr(doel, "id", "")
        if naam == gezocht:
            return knoop.lineno
    return None


@pytest.mark.unit
def test_the_handler_commits_between_execution_and_the_audit_entry() -> None:
    handler = _handler("approve_hitl_request")

    uitvoering = _regel_van_eerste_aanroep(handler, "_voer_goedgekeurde_actie_uit")
    auditregel = _regel_van_eerste_aanroep(handler, "_write_audit_entry")

    assert uitvoering is not None, (
        "`approve_hitl_request` voert niets uit. Dan is de goedkeuringslus weer een doodlopende "
        "straat (OP-89)."
    )
    assert auditregel is not None, (
        "`approve_hitl_request` schrijft geen auditregel. Elke beslissing hoort een onuitwisbaar "
        "spoor te krijgen (OP-71)."
    )

    commits = [
        knoop.lineno
        for knoop in ast.walk(handler)
        if isinstance(knoop, ast.Call)
        and isinstance(knoop.func, ast.Attribute)
        and knoop.func.attr == "commit"
    ]
    ertussen = [regel for regel in commits if uitvoering < regel < auditregel]

    assert ertussen, (
        f"Er staat geen `commit()` tussen de uitvoering (regel {uitvoering}) en de auditregel "
        f"(regel {auditregel}). Gevonden commits: {commits}.\n\n"
        "De poort verzilvert het ticket in dezelfde sessie, en `_write_audit_entry` schrijft binnen "
        "`best_effort` -- die rolt de sessie terug bij een fout. Zonder deze commit maakt een "
        "mislukte auditregel een verbruikte goedkeuring weer bruikbaar, zonder dat er een "
        "auditregel is die dat laat zien (ADR-036 OP-100)."
    )


@pytest.mark.unit
def test_the_audit_entry_still_comes_after_the_execution() -> None:
    """Vangnet: de auditregel VOOR de uitvoering zetten zou de test hierboven ook groen maken.

    Dan legt de keten vast dat er is goedgekeurd zonder te weten of het gelukt is -- en de uitkomst
    is juist wat OP-89 in die regel wilde hebben.
    """
    handler = _handler("approve_hitl_request")

    uitvoering = _regel_van_eerste_aanroep(handler, "_voer_goedgekeurde_actie_uit")
    auditregel = _regel_van_eerste_aanroep(handler, "_write_audit_entry")

    assert uitvoering is not None and auditregel is not None
    assert uitvoering < auditregel, (
        "De auditregel wordt geschreven voordat de actie is uitgevoerd. Dan kan hij de uitkomst "
        "niet bevatten, terwijl dat juist is wat er in hoort te staan."
    )
