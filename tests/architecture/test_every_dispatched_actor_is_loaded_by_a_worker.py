"""Een `.send()` naar een actor die geen enkel proces laadt, schrijft in het niets.

ADR-036 OP-158 (D2). Gemeten 2026-08-17:

`src/core/scheduling/webhooks/handlers.py:203` doet `sync_calendar_integration.send(...)`.
Het gedeployde workercommando is `dramatiq src.workers.workflow_worker:redis_broker
src.workers.actors` (`Dockerfile:168`, `docker-compose.yml:182`), en `src/workers/actors.py`
sloot de calendar-actors expliciet uit. Er consumeerde dus geen enkel proces de queue
`calendar_sync`: agenda-synchronisatie schreef in het niets en `refresh_expiring_webhooks`
draaide nooit, waardoor webhooks die binnen 24 uur verlopen niet werden vernieuwd.

Dat valt niet op, want er komt nooit een melding wanneer iets NIET gebeurt. Een berichtje
in een queue zonder consument geeft geen fout -- het blijft gewoon liggen.

De uitsluiting droeg een reden: "calendar_sync_worker imports workflow_worker via
src/workers/__init__.py which requires DATABASE_URL at import time". **Die reden is
weerlegd door meting.** `src/workers/actors.py` zit in datzelfde pakket, dus die importketen
liep sowieso al. Met exact de omgevingsvariabelen van de container geladen:

    de twee gedeployde modules laden: OK
    calendar_sync_worker laadt ERBIJ: OK
    actors geregistreerd op de broker: 22, waaronder refresh_expiring_webhooks
    en sync_calendar_integration

Deze guard leest de AST, niet de tekst: een actornaam in een comment of een docstring is
geen verzending.

**Mutatiebewijs (2026-08-17), per bewaakt element en in beide richtingen:**
- De import van `calendar_sync_worker` uit `actors.py` gehaald ->
  `test_every_dispatched_actor_is_loaded` ROOD met beide actornamen erbij.
- Een tijdelijke module met `@dramatiq.actor def proef()` plus een `proef.send()` elders,
  zonder import in `actors.py` -> ROOD.
- Diezelfde module MET de import in `actors.py` -> GROEN. Dat is de tegenrichting: de
  guard mag een correct geladen actor niet betrappen.
- Een module die een actor DEFINIEERT maar waarvan niets wordt verzonden, en die nergens
  wordt geladen -> GROEN. Ongebruikte actors zijn geen schrijf-in-het-niets.
- Een verzonnen naam in de uitzonderingslijst -> `test_the_exceptions_are_not_stale` ROOD.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"

# De instappunten worden UIT DE COMPOSE-BESTANDEN gelezen, niet hier vastgelegd. Dat is
# geen netheid maar noodzaak: de eerste versie van deze guard had er twee hardgecodeerd en
# miste daardoor de tweede workercontainer (`docker-compose.yml:353` draait
# `dramatiq src.core.learning.worker:_broker`). Vijf van de zeven bevindingen waren
# vals-positief. Een nieuwe workercontainer telt nu vanzelf mee.
_COMPOSE = ("docker-compose.yml", "docker-compose.prod.yml")

# Actors die bewust worden verzonden zonder dat een worker ze laadt. Gedateerd 2026-08-17,
# reden per regel. Leeg is goed: elke regel hier is een bericht dat blijft liggen.
#
# `execute_workflow_task` (het dode `core/workflow/worker.py`/`api.py`-modulepaar) stond hier
# tot 2026-08-27 -- ADR-036 OP-158 D2b is toen opgelost door de twee bestanden te verwijderen
# in plaats van te wachten op een aparte wijziging.
KNOWN_ZONDER_CONSUMENT: dict[str, str] = {}


def _actor_naam(functie: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """De actornaam als deze functie een `@dramatiq.actor` draagt, anders None.

    Houdt rekening met `actor_name="..."`, want dat is de naam waaronder de broker hem
    kent en die kan afwijken van de functienaam.
    """
    for decorator in functie.decorator_list:
        doel = decorator.func if isinstance(decorator, ast.Call) else decorator
        naam = getattr(doel, "attr", None) or getattr(doel, "id", None)
        if naam not in ("actor", "workflow_actor"):
            continue
        if isinstance(decorator, ast.Call):
            for kw in decorator.keywords:
                if kw.arg == "actor_name" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
        return functie.name
    return None


@lru_cache(maxsize=1)
def _instappunten() -> frozenset[str]:
    """De modules die de gedeployde processen laden, gelezen uit de compose-bestanden."""
    gevonden: set[str] = set()
    patroon = re.compile(r"src[\w.]*\.[\w.]+")
    for naam in _COMPOSE:
        pad = _REPO / naam
        if not pad.exists():
            continue
        for regel in pad.read_text(encoding="utf-8").splitlines():
            # `:_broker`: een worker die via de ENTRYPOINT van zijn image start (bonlezer-worker) heeft
            # in compose alleen `module:_broker` en niet het woord `dramatiq` op die regel.
            if "dramatiq" not in regel and "src.workers" not in regel and ":_broker" not in regel:
                continue
            if regel.lstrip().startswith("#"):
                continue
            for treffer in patroon.findall(regel):
                module = treffer.split(":")[0]
                if not module.startswith("src."):
                    continue
                gevonden.add(module.removeprefix("src.").replace(".", "/") + ".py")
    return frozenset(gevonden)


@lru_cache(maxsize=1)
def _scan() -> tuple[dict[str, set[str]], dict[str, str], frozenset[str]]:
    """(actornaam -> modules, verzonden actornaam -> vindplaats, geladen modules)."""
    gedefinieerd: dict[str, set[str]] = {}
    verzonden: dict[str, str] = {}
    bomen: dict[str, ast.Module] = {}

    for bestand in _SRC.rglob("*.py"):
        relatief = bestand.relative_to(_SRC).as_posix()
        if relatief.split("/")[0] in ("alembic", "tests"):
            continue
        try:
            boom = ast.parse(bestand.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        bomen[relatief] = boom

        for knoop in ast.walk(boom):
            if isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
                naam = _actor_naam(knoop)
                if naam:
                    # Een VERZAMELING modules per naam: twee bestanden kunnen dezelfde
                    # actornaam definieren (`execute_workflow_task` staat zowel in
                    # core/workflow/worker.py als in workers/workflow_worker.py). Wordt er
                    # ook maar een van geladen, dan heeft de verzending een consument.
                    gedefinieerd.setdefault(naam, set()).add(relatief)
                    gedefinieerd.setdefault(knoop.name, set()).add(relatief)
            elif (
                isinstance(knoop, ast.Call)
                and isinstance(knoop.func, ast.Attribute)
                and knoop.func.attr == "send"
                and isinstance(knoop.func.value, ast.Name)
            ):
                verzonden.setdefault(knoop.func.value.id, f"{relatief}:{knoop.lineno}")

    # Welke modules laadt het gedeployde commando? De instappunten plus alles wat zij
    # importeren -- een import voert de decorators in dat bestand uit.
    geladen: set[str] = set()
    for instap in _instappunten():
        geladen.add(instap)
        boom = bomen.get(instap)
        if boom is None:
            continue
        for knoop in ast.walk(boom):
            if isinstance(knoop, ast.ImportFrom) and knoop.module and knoop.module.startswith("src."):
                geladen.add(knoop.module.removeprefix("src.").replace(".", "/") + ".py")
        # `src/workers/__init__.py` wordt bij elke import van het pakket uitgevoerd.
        geladen.add("workers/__init__.py")
    init = bomen.get("workers/__init__.py")
    if init is not None:
        for knoop in ast.walk(init):
            if isinstance(knoop, ast.ImportFrom) and knoop.level == 1 and knoop.module:
                geladen.add(f"workers/{knoop.module.replace('.', '/')}.py")

    return gedefinieerd, verzonden, frozenset(geladen)


def test_every_dispatched_actor_is_loaded() -> None:
    """Elke actor waar een `.send()` naartoe gaat, moet door een worker geladen worden."""
    gedefinieerd, verzonden, geladen = _scan()

    zwevend: list[str] = []
    for naam, vindplaats in sorted(verzonden.items()):
        modules = gedefinieerd.get(naam)
        if not modules:
            continue  # geen actor -- een gewone `.send()` op iets anders
        if not (modules & geladen) and naam not in KNOWN_ZONDER_CONSUMENT:
            waar = ", ".join(f"src/{m}" for m in sorted(modules))
            zwevend.append(f"{naam} (gedefinieerd in {waar}, verzonden op src/{vindplaats})")

    assert not zwevend, (
        f"{len(zwevend)} actor(s) krijgen een `.send()` terwijl geen enkel gedeployd "
        "workerproces ze laadt:\n"
        + "\n".join(f"  - {r}" for r in zwevend)
        + "\n\nDie berichten blijven in de queue liggen. Er komt geen foutmelding, want er "
        "komt nooit een melding wanneer iets NIET gebeurt.\n"
        f"Laad de module in een van {sorted(_instappunten())}, of zet een regel in "
        "KNOWN_ZONDER_CONSUMENT met de reden erbij."
    )


def test_the_exceptions_are_not_stale() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst."""
    gedefinieerd, verzonden, geladen = _scan()

    opgelost = sorted(
        naam
        for naam in KNOWN_ZONDER_CONSUMENT
        if naam not in verzonden or (gedefinieerd.get(naam, set()) & geladen)
    )

    assert not opgelost, (
        f"Deze actors staan in KNOWN_ZONDER_CONSUMENT maar worden inmiddels wel geladen "
        f"(of niet meer verzonden): {opgelost}. Haal ze uit de lijst."
    )


def test_the_guard_is_not_vacuous() -> None:
    """Lege verzamelingen maken de test hierboven trivially groen."""
    gedefinieerd, verzonden, geladen = _scan()

    assert len(gedefinieerd) >= 25, (
        f"Slechts {len(gedefinieerd)} actor-definities gevonden; op 2026-08-17 waren het er "
        "31 (met de functienaam-aliassen meer). Leest de scan `src/` wel?"
    )
    assert verzonden, "Geen enkele `.send()` gevonden -- dan toetst de guard niets."
    assert len(_instappunten()) >= 3, (
        f"Slechts {len(_instappunten())} instappunten uit {list(_COMPOSE)} gelezen: "
        f"{sorted(_instappunten())}. Op 2026-08-17 waren het er drie "
        "(workflow_worker, actors, core/learning/worker). Zonder die lijst is de guard hol."
    )
    assert len(geladen) >= 5, (
        f"Slechts {len(geladen)} geladen modules herleid. Kloppen de compose-paden nog?"
    )
