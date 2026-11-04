"""Asyncio-toestand op moduleniveau overleeft de event loop niet (ADR-036 OP-156).

Een `asyncio.Lock()`, `asyncio.Queue()` of een async connection pool die bij het IMPORTEREN
van een module wordt aangemaakt, hoort bij de event loop die op dat moment draait. Elke
volgende loop krijgt een object dat aan een dode loop vastzit.

Gemeten 2026-08-16, drie regels, zonder enige wijziging aan de betrokken code:

    asyncio.run(get_redis_client())   -> ok
    asyncio.run(get_redis_client())   -> RuntimeError: Event loop is closed

pytest-asyncio maakt per test een nieuwe loop. In de volledige suite kwam dit boven als
`RuntimeError: Task ... got Future attached to a different loop` in
`tests/unit/workflow/test_workflow_real_routing.py` -- een test die LOS gewoon slaagt. Wat
er faalt hangt af van welke tests op dezelfde xdist-worker belanden, en dat verschuift
zodra er ergens een test bijkomt. Dat leest als flakiness maar is het niet: de oorzaak is
structureel en reproduceerbaar.

`src/core/database/redis.py` heeft wel een herstelpad (`_redis_pool = None` bij een
mislukte ping), maar dat vangt alleen `redis.ConnectionError` en `redis.TimeoutError`. De
loop-mismatch is een `RuntimeError` en glipt er dus langs.

Dit is een GROENE guard met een gedateerde uitzonderingslijst en geen rode test: het
repareren van de Redis-pool raakt elke aanroeper en is een eigen wijziging met een eigen
meting. Nieuwe gevallen worden wel geblokkeerd.

**Mutatiebewijs (2026-08-16), per bewaakt element en in beide richtingen:**
- Tijdelijk bestand `src/core/_proef_loopstate.py` met `_slot = asyncio.Lock()` op
  moduleniveau -> `test_no_new_module_level_event_loop_state` ROOD met dat pad.
- Datzelfde bestand met `asyncio.Lock()` BINNEN een functie -> GROEN. Dat is de
  tegenrichting: de guard bewaakt import-tijd, niet het gebruik van asyncio.
- Datzelfde bestand met `threading.Lock()` op moduleniveau -> GROEN. Deze richting was
  geen formaliteit: de eerste versie matchte op de kale naam `Lock` en betrapte daarmee
  vijf modules die `threading.Lock()` volkomen terecht gebruiken. Een guard die legitieme
  code blokkeert is net zo stuk als een die niets vindt.
- Datzelfde bestand met alleen de TEKST `asyncio.Lock()` in een comment -> GROEN.
- `core/governance/rate_limiter.py` uit de uitzonderingslijst gehaald -> ROOD; terug -> GROEN.
- Een verzonnen pad in de lijst -> `test_the_exceptions_are_not_stale` ROOD.
Zeven mutaties, alle zeven zoals verwacht.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"

# Constructies die aan de draaiende event loop vastzitten zodra ze worden aangemaakt.
_LOOPGEBONDEN = frozenset(
    {
        "Lock",
        "Event",
        "Condition",
        "Semaphore",
        "BoundedSemaphore",
        "Queue",
        "LifoQueue",
        "PriorityQueue",
        "ConnectionPool",
        "BlockingConnectionPool",
    }
)

_BUITEN_BESCHOUWING = ("alembic", "tests")

# Modules met loopgebonden toestand op moduleniveau. Gedateerd 2026-08-16, reden per regel.
KNOWN_MODULE_LEVEL_STATE: dict[str, str] = {
    "core/database/redis.py": (
        "`_redis_pool_lock` staat nog op moduleniveau, maar wordt sinds 2026-08-17 SAMEN "
        "met de pool vervangen zodra `_vervang_de_pool_bij_een_nieuwe_loop()` een andere "
        "event loop ziet. De onderliggende fout van OP-156 is daarmee weg; wat blijft is "
        "de VORM, en die is hier bewust: het slot moet bestaan voordat het kan worden "
        "vervangen. Geborgd door "
        "tests/unit/core/database/test_the_redis_pool_survives_a_new_event_loop.py"
    ),
    "core/governance/rate_limiter.py": (
        "`_redis_limiter_lock` staat nog op moduleniveau, maar wordt sinds 2026-08-26 SAMEN "
        "met de gecachete limiter vervangen zodra `_vervang_de_limiter_bij_een_nieuwe_loop()` "
        "een andere event loop ziet -- zelfde patroon als redis.py hierboven. De onderliggende "
        "fout van OP-156 is daarmee weg; wat blijft is de VORM. Geborgd door "
        "tests/unit/core/governance/test_the_redis_limiter_survives_a_new_event_loop.py"
    ),
}


def _loopgebonden_namen(boom: ast.Module) -> tuple[set[str], set[str]]:
    """(aliassen van asyncio-achtige modules, direct geimporteerde loopgebonden namen).

    De HERKOMST moet meetellen, niet alleen de naam. `threading.Lock()` heet ook `Lock`
    maar zit niet aan een event loop vast; vijf modules in `src/` gebruiken die vorm
    volkomen terecht. De eerste versie van deze guard matchte op de kale naam en betrapte
    ze alle vijf -- een guard die legitieme code blokkeert is net zo stuk als een die niets
    vindt, en dat is precies wat de tweede mutatierichting hoort af te vangen.
    """
    modules: set[str] = set()
    namen: set[str] = set()
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.Import):
            for alias in knoop.names:
                if alias.name == "asyncio" or alias.name.startswith("redis.asyncio"):
                    modules.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(knoop, ast.ImportFrom):
            bron = knoop.module or ""
            if bron == "asyncio" or bron.startswith("redis.asyncio"):
                for alias in knoop.names:
                    if alias.name in _LOOPGEBONDEN:
                        namen.add(alias.asname or alias.name)
    return modules, namen


def _is_loopgebonden(knoop: ast.AST, modules: set[str], namen: set[str]) -> bool:
    """True voor een AANROEP van een loopgebonden constructie uit asyncio of redis.asyncio.

    Op de AST en niet op de tekst: `asyncio.Lock()` in een comment of een docstring is
    geen toestand, en een `def Lock(...)` evenmin.
    """
    if not isinstance(knoop, ast.Call):
        return False
    doel = knoop.func
    if isinstance(doel, ast.Attribute):
        return (
            doel.attr in _LOOPGEBONDEN
            and isinstance(doel.value, ast.Name)
            and doel.value.id in modules
        )
    if isinstance(doel, ast.Name):
        return doel.id in namen
    return False


def _moduleniveau_toewijzingen(boom: ast.Module) -> bool:
    """Alleen toewijzingen die bij het IMPORTEREN worden uitgevoerd.

    Expliciete recursie over de directe body plus `if`/`try`-takken, en NIET `ast.walk()`
    over de hele module: die duikt functiebodies in, en een `asyncio.Lock()` binnen een
    functie wordt pas aangemaakt als die functie draait -- in de dan geldende loop, wat
    juist correct is. Diezelfde fout is in dit project eerder twee keer gemaakt.
    """

    modules, namen = _loopgebonden_namen(boom)
    if not modules and not namen:
        return False

    def loop_door(statements: list[ast.stmt]) -> bool:
        for statement in statements:
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                waarde = statement.value
                if waarde is not None:
                    for knoop in ast.walk(waarde):
                        if _is_loopgebonden(knoop, modules, namen):
                            return True
            elif isinstance(statement, ast.If):
                if loop_door(statement.body) or loop_door(statement.orelse):
                    return True
            elif isinstance(statement, ast.Try):
                if (
                    loop_door(statement.body)
                    or loop_door(statement.orelse)
                    or loop_door(statement.finalbody)
                    or any(loop_door(h.body) for h in statement.handlers)
                ):
                    return True
        return False

    return loop_door(boom.body)


@lru_cache(maxsize=1)
def _scan() -> tuple[frozenset[str], tuple[str, ...]]:
    gevonden: set[str] = set()
    onleesbaar: list[str] = []
    for bestand in _SRC.rglob("*.py"):
        relatief = bestand.relative_to(_SRC).as_posix()
        if relatief.split("/")[0] in _BUITEN_BESCHOUWING:
            continue
        try:
            boom = ast.parse(bestand.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError, OSError) as fout:
            onleesbaar.append(f"{relatief}: {type(fout).__name__}")
            continue
        if _moduleniveau_toewijzingen(boom):
            gevonden.add(relatief)
    return frozenset(gevonden), tuple(sorted(onleesbaar))


def test_no_new_module_level_event_loop_state() -> None:
    """Nieuwe loopgebonden toestand op moduleniveau is geblokkeerd."""
    onverwacht = sorted(set(_scan()[0]) - set(KNOWN_MODULE_LEVEL_STATE))

    assert not onverwacht, (
        f"{len(onverwacht)} module(s) maken bij het IMPORTEREN een asyncio-object of "
        "connection pool aan:\n"
        + "\n".join(f"  - src/{pad}" for pad in onverwacht)
        + "\n\nZo'n object hoort bij de event loop die op dat moment draait. Elke volgende "
        "loop krijgt een object aan een dode loop -- in de testsuite een `RuntimeError: got "
        "Future attached to a different loop` in een WILLEKEURIGE andere test, afhankelijk "
        "van de xdist-verdeling (ADR-036 OP-156).\n"
        "Maak het object binnen de functie die het gebruikt, of zet een regel in "
        "KNOWN_MODULE_LEVEL_STATE met de reden en het OP-nummer erbij."
    )


def test_the_exceptions_are_not_stale() -> None:
    """Een module die die toestand niet meer heeft MOET uit de lijst."""
    met_toestand = set(_scan()[0])
    verdwenen = sorted(pad for pad in KNOWN_MODULE_LEVEL_STATE if pad not in met_toestand)

    assert not verdwenen, (
        f"Deze modules staan in KNOWN_MODULE_LEVEL_STATE maar hebben geen loopgebonden "
        f"toestand op moduleniveau (meer): {verdwenen}. Haal ze uit de lijst."
    )


def test_every_file_was_actually_read() -> None:
    """Een bestand dat de scan niet kon lezen is een gat, geen detail."""
    onleesbaar = _scan()[1]

    assert not onleesbaar, (
        f"De scan kon {len(onleesbaar)} bestand(en) niet parsen: {list(onleesbaar)}."
    )


def test_the_guard_is_not_vacuous() -> None:
    """Een scan die niets vindt maakt de guard trivially groen."""
    assert _SRC.is_dir(), f"{_SRC} bestaat niet"
    aantal = sum(1 for _ in _SRC.rglob("*.py"))
    assert aantal >= 1000, f"Slechts {aantal} bestanden gescand; op 2026-08-16 waren het er 2291."
    assert KNOWN_MODULE_LEVEL_STATE, (
        "De uitzonderingslijst is leeg. Dan bewaakt `test_the_exceptions_are_not_stale` "
        "niets en is de eerste test niet aantoonbaar in staat iets te vinden."
    )
