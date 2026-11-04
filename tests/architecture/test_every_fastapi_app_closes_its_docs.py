"""Geen enkele FastAPI-app in `src/` publiceert zijn schema onvoorwaardelijk (ADR-036 OP-124).

**Waarom deze guard bestaat.** OP-124 is gerepareerd in `src/main.py`, maar dat is niet de
enige plek waar een `FastAPI(...)` wordt gebouwd. Twee andere deden het fout en zijn op
2026-08-14 meegerepareerd:

  - `src/core/app_factory.py` had `docs_url="/docs" if not testing else "/docs"` -- een ternary
    waarvan BEIDE takken open waren. Een guard die alleen "is het een conditie?" toetst, keurt
    dat goed. Daarom kijkt deze guard naar de mogelijke WAARDEN en eist hij dat `None` erbij
    zit, niet naar de vorm van de expressie.
  - `src/core/tool_broker/main.py` zette `docs_url` helemaal niet, en dan geldt de
    FastAPI-default `/docs`. Ontbreken is dus ook een overtreding, geen neutraal geval.

**Bereik.** Alleen `src/`, en de kandidaten worden opgehaald met `git grep -l` zodat er nooit
duizenden bestanden in Python worden ingelezen -- dat liet eerder een xdist-worker omvallen
(zie `.claude/skills/valkuilen`). `git grep` op de working tree is een bewijsbare superset:
een `FastAPI(`-constructie zonder die tekst bestaat niet.

Mutatie-bewijs (daadwerkelijk gedraaid, zie de final-approver brief van 2026-08-14):

  - `openapi_url` weghalen bij `src/main.py` -> test_no_fastapi_app_publishes_its_schema FAILED
  - `openapi_url="/openapi.json"` als constante -> zelfde test FAILED
  - **alleen `docs_url` sluiten en openapi_url/redoc_url weglaten** -> zelfde test FAILED. Dit is
    de val waar de eerste versie van deze guard zelf in liep: die toetste alleen `docs_url` en
    keurde daarmee een app goed die het volledige schema plus ReDoc uitleverde.
  - **alleen `openapi_url` gated, docs_url en redoc_url weggelaten** -> beide tests GROEN. Dat is
    de andere richting: zo'n app is aantoonbaar dicht en mag geen vals positief opleveren.
  - de gedateerde uitzondering leeghalen -> test_no_fastapi_app_publishes_its_schema FAILED op
    security_middleware.py
  - een uitzondering laten staan die is opgelost -> test_the_dated_exceptions_are_not_stale FAILED
"""

import ast
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Alle drie de endpoints vormen samen de OpenAPI-oppervlakte. `/openapi.json` is de payload;
# `/docs` en `/redoc` zijn alleen viewers. Een guard die alleen `docs_url` toetst mist dus juist
# het endpoint dat het schema uitlevert.
# `openapi_url` is de HOOFDSCHAKELAAR, en dat is gedocumenteerd gedrag van FastAPI: "If you want
# to disable the OpenAPI schema completely you can set openapi_url=None, that will also disable the
# documentation user interfaces that use it."
# (https://fastapi.tiangolo.com/tutorial/metadata/)
#
# Empirisch nagemeten op fastapi 0.121.1:
#     openapi_url=None alleen -> /docs 404, /redoc 404, /openapi.json 404
#     docs_url=None    alleen -> /docs 404, /redoc 200, /openapi.json 200
#
# Daarom toetst deze guard uitsluitend `openapi_url`. Dat is sluitend EN zonder vals positief:
# `docs_url` en `redoc_url` ook eisen zou een auteur afkeuren die alleen de hoofdschakelaar
# omzet, terwijl diens app aantoonbaar dicht is. En het dekt de val waar de eerste versie van
# deze guard in liep: wie alleen `docs_url` sluit, laat het schema en ReDoc wagenwijd open --
# daar is `openapi_url` niet gezet, dus die valt hier alsnog door.
SCHEMA_KWARG = "openapi_url"

ONBEPAALD = object()

# Gedateerde uitzonderingen, met een reden per regel (zie .claude/rules/quality-gates.md).
# Elke regel is gemeten, niet aangenomen.
TOEGESTAAN_ZONDER_GATE = {
    "src/core/security/security_middleware.py": (
        "2026-08-14: wegwerp-app in `validate_security_configuration()` die alleen dient om te "
        "toetsen of de middleware instantieerbaar is. Wordt nooit geserveerd en heeft geen "
        "routes, dus er is geen schema om te lekken."
    ),
}


def _kandidaatbestanden() -> list[Path]:
    """Bestanden in `src/` die de tekst `FastAPI(` bevatten."""
    resultaat = subprocess.run(
        ["git", "grep", "-l", "-E", r"FastAPI\(", "--", "src/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # returncode 1 betekent bij git grep "niets gevonden"; alles daarboven is een echte fout en
    # mag niet als "geen overtredingen" wegvallen.
    assert resultaat.returncode in (0, 1), (
        f"git grep faalde met returncode {resultaat.returncode}: {resultaat.stderr.strip()}"
    )
    return [
        REPO_ROOT / regel
        for regel in resultaat.stdout.splitlines()
        if regel.strip().endswith(".py")
    ]


def _mogelijke_waarden(knoop: ast.expr) -> list[object]:
    """Alle constante uitkomsten van een expressie; `object()` voor 'niet te bepalen'."""
    if isinstance(knoop, ast.Constant):
        return [knoop.value]
    if isinstance(knoop, ast.IfExp):
        return _mogelijke_waarden(knoop.body) + _mogelijke_waarden(knoop.orelse)
    if isinstance(knoop, ast.BoolOp):
        return [waarde for deel in knoop.values for waarde in _mogelijke_waarden(deel)]
    # Alles wat niet statisch te herleiden is (een naam, een functieaanroep, een attribuut) telt
    # als ONBEPAALD en dus als overtreding. Eerder stond hier `return [None]` -- "kan dicht" --
    # en dat liet `DOCS = "/docs"` plus `FastAPI(docs_url=DOCS)` stil passeren.
    return [ONBEPAALD]


def _overtredingen() -> list[str]:
    gevonden = []
    for pad in _kandidaatbestanden():
        relatief = pad.relative_to(REPO_ROOT).as_posix()
        boom = ast.parse(pad.read_text(encoding="utf-8", errors="replace"), filename=str(pad))
        for knoop in ast.walk(boom):
            if not isinstance(knoop, ast.Call):
                continue
            naam = getattr(knoop.func, "id", None) or getattr(knoop.func, "attr", None)
            if naam != "FastAPI":
                continue
            argumenten = {kw.arg: kw.value for kw in knoop.keywords if kw.arg}
            if SCHEMA_KWARG not in argumenten:
                gevonden.append(
                    f"{relatief}:{knoop.lineno} zet {SCHEMA_KWARG} niet, dus de FastAPI-default "
                    "geldt en het volledige schema wordt geserveerd"
                )
                continue
            waarden = _mogelijke_waarden(argumenten[SCHEMA_KWARG])
            if ONBEPAALD in waarden:
                gevonden.append(
                    f"{relatief}:{knoop.lineno} {SCHEMA_KWARG} is niet statisch te herleiden; "
                    "geef een expliciete conditie met None in een van de takken"
                )
            elif None not in waarden:
                gevonden.append(
                    f"{relatief}:{knoop.lineno} {SCHEMA_KWARG} kan nooit None zijn "
                    f"(mogelijke waarden: {waarden})"
                )
    return gevonden


def test_no_fastapi_app_publishes_its_schema() -> None:
    """Elke FastAPI-app kan zijn docs dichtzetten, of staat als gedateerde uitzondering."""
    open_apps = [
        melding
        for melding in _overtredingen()
        if melding.split(":")[0] not in TOEGESTAAN_ZONDER_GATE
    ]

    assert not open_apps, (
        "Deze FastAPI-app(s) publiceren hun OpenAPI-schema onvoorwaardelijk:\n  "
        + "\n  ".join(open_apps)
        + "\n\nGeef docs_url/redoc_url/openapi_url een waarde die None KAN zijn buiten "
        "development (ADR-036 OP-124), of zet het bestand met datum en reden in "
        "TOEGESTAAN_ZONDER_GATE."
    )


def test_the_dated_exceptions_are_not_stale() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst, anders rot hij dicht."""
    nog_overtredend = {melding.split(":")[0] for melding in _overtredingen()}
    opgelost = [pad for pad in TOEGESTAAN_ZONDER_GATE if pad not in nog_overtredend]

    assert not opgelost, (
        "Deze uitzonderingen zijn niet meer nodig en moeten uit TOEGESTAAN_ZONDER_GATE:\n  "
        + "\n  ".join(opgelost)
    )
