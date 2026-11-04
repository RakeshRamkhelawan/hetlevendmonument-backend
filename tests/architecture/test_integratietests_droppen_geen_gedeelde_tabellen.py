"""Een integratietest laat geen tabel of schema vallen in de gedeelde testdatabase (CI-run 40674951559, 2026-10-28).

**Waarom.** Alle testbestanden van een shard delen EEN PostgreSQL-database; de sessiefixture in
`tests/integration/conftest.py` bouwt het schema een keer met `create_all`. Een testbestand dat daarna een tabel laat
vallen en zelf opnieuw bouwt, laat de rest van de shard met een ander schema achter. Gemeten in die run:

- `test_company_layer_isolated.py` bouwde `board_decisions` zonder `updated_at`; `test_fase7_templates_onboarding.py`
  faalde daarna met 'column board_decisions.updated_at does not exist';
- `test_company_layer_fase1_integration.py` liet `users` vallen, wat de samengestelde vreemde sleutels van `user_roles`
  meenam; `test_platformgezag_op_een_definitie.py` faalde daarna met 'DID NOT RAISE'.

**Wat dit toetst (structuur, geen tekst).** Per bestand onder `tests/integration/` (dezelfde uitsluitingen als
`norecursedirs` in `pyproject.toml`) wordt de AST doorlopen. Een overtreding is een AANROEP (`text(...)`, `execute(...)`,
`exec_driver_sql(...)`, `executescript(...)`) waarvan een tekstargument `DROP TABLE` of `DROP SCHEMA` bevat. Een tekst die
alleen in een comment, een docstring of een niet-aangeroepen constante staat, telt niet. Een argument dat een naam is,
wordt een niveau teruggezocht naar de tekst die eraan is toegewezen (zo vangt dit ook `sql = "DROP ..."; execute(sql)`).
De omsluitende functie wordt bijgehouden met expliciete recursie.

**Uitzonderingslijst.** De sleutel is `bestand::functie`, nooit het bestand alleen, met een reden en een datum per regel.
`test_known_uitzonderingen_is_not_stale` faalt zodra een uitzondering niet meer voorkomt, zodat de lijst niet dichtrot.

**Mutatiebewijs (2026-10-28, uitgevoerd op een kopie van de boom in een tijdelijk bestand onder `tests/integration/`):**

1. De overtreding terugzetten: een `await conn.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))` in een nieuw bestand
   -> `test_no_new_drops_in_integration_tests` ROOD.
2. Per element van `UITVOERENDE_AANROEPEN` een eigen mutatie op `vind_drops` (`text`, `execute`, `exec_driver_sql`,
   `executescript`), plus via een variabele (`sql = "DROP SCHEMA x"; conn.execute(text(sql))`), kleine letters en een
   geneste functie -> elk gevonden, de functie is de innerlijkste. Als nieuw bestand onder `tests/integration/`
   gedraaid -> ROOD (`['tests/integration/test_mut_tmp.py::f']`). Ook `DROP TYPE` en een gewone DELETE -> GROEN.
3. Een legitiem geval mag niet blijven hangen: de tekst `DROP TABLE` in een comment, in een docstring en in een
   niet-aangeroepen constante -> GROEN.
4. IN een bestand dat al op de uitzonderingslijst staat (`tests/integration/conftest.py`): een tweede functie met een
   DROP -> ROOD (de sleutel is `bestand::functie`, het bestand alleen volstaat niet).
5. Een uitzondering die niet meer voorkomt (naam verzonnen) -> `test_known_uitzonderingen_is_not_stale` ROOD.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INTEGRATIE = REPO_ROOT / "tests" / "integration"

#: Aanroepen die SQL uitvoeren. Een verzameling, zodat de mutatie per element te bewijzen is.
UITVOERENDE_AANROEPEN = frozenset({"text", "execute", "exec_driver_sql", "executescript"})

_DROP = re.compile(r"\bDROP\s+(TABLE|SCHEMA)\b", re.IGNORECASE)

#: bestand::functie -> reden (met datum). Alleen wat een EIGEN, op te geven omgeving heeft of nog open staat.
KNOWN_UITZONDERINGEN: dict[str, str] = {
    "tests/integration/conftest.py::_init_schema": (
        "2026-10-28: de sessiefixture IS de bouwer van het gedeelde schema. Hij wist `public` een keer per sessie, na "
        "`eis_testdatabase()` (alleen een database op `_test`, niet de ontwikkelpoort), en bouwt daarna alles met create_all."
    ),
}


def _uitgesloten_mappen() -> set[str]:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return set(config["tool"]["pytest"]["ini_options"]["norecursedirs"])


def integratiebestanden() -> list[Path]:
    uitgesloten = _uitgesloten_mappen()
    paden: list[Path] = []
    for pad in sorted(INTEGRATIE.rglob("*.py")):
        relatief = pad.relative_to(REPO_ROOT)
        if set(relatief.parts[:-1]) & uitgesloten:
            continue
        paden.append(pad)
    return paden


def _tekst_van(knoop: ast.expr, toegewezen: dict[str, str]) -> str:
    """De vaste tekstdelen van een expressie: een tekst, een f-string (zonder de ingevulde delen), een optelling, een naam."""
    if isinstance(knoop, ast.Constant) and isinstance(knoop.value, str):
        return knoop.value
    if isinstance(knoop, ast.JoinedStr):
        return "".join(
            deel.value
            for deel in knoop.values
            if isinstance(deel, ast.Constant) and isinstance(deel.value, str)
        )
    if isinstance(knoop, ast.BinOp):
        return _tekst_van(knoop.left, toegewezen) + _tekst_van(knoop.right, toegewezen)
    if isinstance(knoop, ast.Name):
        return toegewezen.get(knoop.id, "")
    return ""


def _toegewezen_teksten(boom: ast.AST) -> dict[str, str]:
    """Naam -> vaste tekst voor elke `naam = <tekst>` in het bestand (een niveau diep, geen dataflow)."""
    uit: dict[str, str] = {}
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.Assign) and len(knoop.targets) == 1:
            doel = knoop.targets[0]
            if isinstance(doel, ast.Name):
                tekst = _tekst_van(knoop.value, {})
                if tekst:
                    uit[doel.id] = tekst
    return uit


def _aanroepnaam(aanroep: ast.Call) -> str:
    if isinstance(aanroep.func, ast.Attribute):
        return aanroep.func.attr
    if isinstance(aanroep.func, ast.Name):
        return aanroep.func.id
    return ""


def vind_drops(bron: str) -> set[str]:
    """De functies (innerlijkste omsluitende functie, of `<module>`) waarin een uitvoerende aanroep een DROP bevat."""
    boom = ast.parse(bron)
    toegewezen = _toegewezen_teksten(boom)
    gevonden: set[str] = set()

    def loop(knoop: ast.AST, functie: str) -> None:
        if isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functie = knoop.name
        if isinstance(knoop, ast.Call) and _aanroepnaam(knoop) in UITVOERENDE_AANROEPEN:
            argumenten = [*knoop.args, *(k.value for k in knoop.keywords)]
            if any(_DROP.search(_tekst_van(a, toegewezen)) for a in argumenten):
                gevonden.add(functie)
        for kind in ast.iter_child_nodes(knoop):
            loop(kind, functie)

    loop(boom, "<module>")
    return gevonden


def _alle_drops() -> set[str]:
    sleutels: set[str] = set()
    for pad in integratiebestanden():
        relatief = pad.relative_to(REPO_ROOT).as_posix()
        for functie in vind_drops(pad.read_text(encoding="utf-8")):
            sleutels.add(f"{relatief}::{functie}")
    return sleutels


def test_no_new_drops_in_integration_tests() -> None:
    """Een integratietest laat geen tabel of schema vallen in de gedeelde testdatabase."""
    nieuw = sorted(_alle_drops() - set(KNOWN_UITZONDERINGEN))

    assert not nieuw, (
        "Deze integratietests laten tabellen of schema's vallen in de gedeelde testdatabase: "
        f"{nieuw}. Gebruik het schema dat de sessiefixture met create_all maakt, of een eigen schema/database, en ruim "
        "alleen je EIGEN rijen op (CI-run 40674951559, brief 2026-10-28)."
    )


def test_known_uitzonderingen_is_not_stale() -> None:
    """Een uitzondering die niet meer voorkomt, MOET uit de lijst."""
    verouderd = sorted(set(KNOWN_UITZONDERINGEN) - _alle_drops())

    assert not verouderd, (
        f"Deze uitzonderingen komen niet meer voor en moeten uit de lijst: {verouderd}"
    )


def test_elke_uitzondering_heeft_een_reden_met_datum() -> None:
    zonder = sorted(
        k for k, reden in KNOWN_UITZONDERINGEN.items() if not re.match(r"20\d\d-\d\d-\d\d", reden)
    )

    assert not zonder, f"Uitzonderingen zonder datum aan het begin van de reden: {zonder}"
