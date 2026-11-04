"""De tenantcontext-listener MOET geregistreerd blijven (ADR-036 OP-151).

`src/core/database/database.py` zet `app.current_tenant` via een `begin`-event op de
klasse `Engine`. Haalt iemand dat event weg, dan is het enige bewijs dat dat fout is een
integratietest achter `skipif(not _postgres_bereikbaar())` -- zonder een draaiende
PostgreSQL staat alles groen en merkt niemand het (Gate 2-review 2026-08-16, H1).

Deze guard heeft geen database nodig en draait daarom mee in de blokkerende CI-stap
(`tests/unit tests/architecture tests/core`).

Hij leest de AST en niet de tekst: `event.listens_for` in een comment, een docstring of
een foutmelding is geen registratie. Dat verschil is in dit project geen theorie -- een
zusterguard betrapte een uitzonderingslijst die met `grep` was samengesteld en een
`create_async_engine` uit een DOCSTRING bevatte.

**Mutatiebewijs (2026-08-16), per bewaakt element en in beide richtingen:**
- De decorator `@event.listens_for(Engine, "begin")` weggehaald ->
  `test_the_begin_event_is_registered` ROOD.
- `"begin"` vervangen door `"connect"` -> diezelfde test ROOD (het is de literal die telt,
  niet de aanwezigheid van een listener).
- `Engine` vervangen door een ENKELE engine (`@event.listens_for(engine, "begin")`) ->
  ROOD. Deze mutatie ontbrak in de eerste versie en de guard bleef er groen onder, terwijl
  "op de klasse en niet op een enkele engine" nu juist het hele punt is: er zijn zestien
  engines naast `db_manager` (Gate 2-review ronde 2, BLOCKER 2).
- De aanroep van `set_config` uit de functie gehaald ->
  `test_the_listener_actually_sets_the_setting` ROOD. Zonder die helft zou een leeg
  listener-lichaam de eerste test halen.
- De dialect-guard weggehaald -> `test_the_listener_skips_non_postgresql` ROOD. Zonder die
  helft breekt elke SQLite-unittest, want daar bestaat `set_config` niet.
- Alles ongewijzigd -> GROEN.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

_BESTAND = Path(__file__).resolve().parents[2] / "src" / "core" / "database" / "database.py"
_EVENT = "begin"
_INSTELLING = "app.current_tenant"


@lru_cache(maxsize=1)
def _module() -> ast.Module:
    return ast.parse(_BESTAND.read_text(encoding="utf-8-sig"))


def _luisteraars_op(gebeurtenis: str) -> list[ast.FunctionDef]:
    """Functies met een `@event.listens_for(..., "<gebeurtenis>")`-decorator."""
    gevonden: list[ast.FunctionDef] = []
    for knoop in ast.walk(_module()):
        if not isinstance(knoop, ast.FunctionDef):
            continue
        for decorator in knoop.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            doel = decorator.func
            naam = getattr(doel, "attr", None) or getattr(doel, "id", None)
            if naam not in {"listens_for", "listen"}:
                continue
            # Het EERSTE argument moet de KLASSE `Engine` zijn, niet een enkele engine.
            # Dat is niet cosmetisch: de codebase bouwt zestien engines naast
            # `db_manager`, en een listener op een van hen dekt de andere vijftien niet.
            # De eerste versie van deze guard las alleen de string-literals en bleef
            # daarmee GROEN onder `@event.listens_for(een_engine, "begin")` -- precies de
            # mutatie waarvoor hij is geschreven (Gate 2-review ronde 2, BLOCKER 2).
            doelwit = decorator.args[0] if decorator.args else None
            if not (isinstance(doelwit, ast.Name) and doelwit.id == "Engine"):
                continue
            literals = [
                a.value
                for a in decorator.args
                if isinstance(a, ast.Constant) and isinstance(a.value, str)
            ]
            if gebeurtenis in literals:
                gevonden.append(knoop)
    return gevonden


def _zonder_docstring(functie: ast.FunctionDef) -> list[ast.stmt]:
    """De body zonder de docstring.

    Zonder deze stap is de guard hol, en dat is gemeten en niet bedacht: de eerste versie
    doorzocht alle string-constanten in de functie, en de docstring noemt
    `app.current_tenant` tien keer. De mutatie "haal de set_config-aanroep weg" bleef
    daardoor GROEN -- dezelfde fout als een guard die `ast.dump()` doorzoekt en de
    docstring meeleest.
    """
    body = functie.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _noemt_in_een_aanroep(functie: ast.FunctionDef, naam: str) -> bool:
    """True als `naam` als tekst binnen een daadwerkelijke AANROEP voorkomt.

    Niet in een comment, niet in de docstring, en niet als los liggende constante: alleen
    als argument van een `ast.Call`. Dat is het verschil tussen "de functie noemt de
    instelling" en "de functie zet de instelling".
    """
    for statement in _zonder_docstring(functie):
        for knoop in ast.walk(statement):
            if not isinstance(knoop, ast.Call):
                continue
            for arg in ast.walk(knoop):
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and naam in arg.value
                ):
                    return True
    return False


def _vergelijkt_met(functie: ast.FunctionDef, naam: str) -> bool:
    """True als `naam` in een VERGELIJKING buiten de docstring voorkomt.

    Voor de dialect-guard: die is een `if conn.dialect.name != "postgresql"`, geen aanroep.
    """
    for statement in _zonder_docstring(functie):
        for knoop in ast.walk(statement):
            if not isinstance(knoop, ast.Compare):
                continue
            for arg in ast.walk(knoop):
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and naam in arg.value
                ):
                    return True
    return False


def test_the_begin_event_is_registered() -> None:
    """Er is een functie met een `begin`-listener in database.py."""
    luisteraars = _luisteraars_op(_EVENT)

    assert luisteraars, (
        f"Geen enkele functie in {_BESTAND.name} heeft een "
        f'`@event.listens_for(..., "{_EVENT}")`-decorator. Zonder dat event wordt '
        "`app.current_tenant` nergens meer gezet en draait elke transactie zonder "
        "tenantcontext. Onder de rol `sanskritisetu_app` levert dat nul rijen op zonder "
        "foutmelding (ADR-036 OP-151)."
    )


def test_the_listener_actually_sets_the_setting() -> None:
    """Een leeg listener-lichaam haalt de test hierboven ook -- daarom deze helft."""
    luisteraars = _luisteraars_op(_EVENT)
    assert luisteraars, "geen begin-listener gevonden"

    zetters = [f for f in luisteraars if _noemt_in_een_aanroep(f, _INSTELLING)]

    assert zetters, (
        f"De `{_EVENT}`-listener(s) {[f.name for f in luisteraars]} noemen "
        f"`{_INSTELLING}` niet. De listener bestaat dan wel maar zet niets."
    )


def test_the_listener_skips_non_postgresql() -> None:
    """De listener moet SQLite overslaan; anders breekt elke unittest.

    De andere richting: zonder deze test zou "zet het altijd, overal" een geldige
    oplossing zijn, en dan faalt elke SQLite-sessie op een onbekende functie
    `set_config`. Dat is geen veiligheid maar een storing.
    """
    zetters = [f for f in _luisteraars_op(_EVENT) if _noemt_in_een_aanroep(f, _INSTELLING)]
    assert zetters, "geen begin-listener die de instelling zet"

    with_dialect = [f for f in zetters if _vergelijkt_met(f, "postgresql")]

    assert with_dialect, (
        f"De listener(s) {[f.name for f in zetters]} noemen `postgresql` niet en slaan "
        "andere dialecten dus mogelijk niet over. SQLite kent `set_config` niet."
    )


def test_the_guard_reads_the_right_file() -> None:
    """Een verkeerd pad maakt elke test hierboven trivially rood of groen."""
    assert _BESTAND.exists(), f"{_BESTAND} bestaat niet"
    assert len(_module().body) > 10, f"{_BESTAND} lijkt leeg -- wordt hij wel geparsed?"
