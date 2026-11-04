"""Verdeelt de testbestanden van `tests/integration` over de shards van de CI-job `integration`.

Gebruik (de CI-stap geeft zijn matrixnummer mee; het script geeft de paden, een per regel):

    pytest -c pyproject.toml $(python scripts/ci_integratie_shard.py 3) -q

**Waarom dit bestaat (gemeten 2026-10-26).** Er zijn 3731 integratietests en de hele suite kost zonder xdist ~105
minuten (3563 tests in 6000 s, ~1,7 s per test, vooral setup). De ene CI-stap had 55 minuten en haalde het einde
dus niet, ook niet als alles groen was. Geen xdist binnen een job: `tests/integration/conftest.py` waarschuwt dat
parallelle workers op een gedeelde database de transactie-isolatie breken. Daarom meerdere jobs, elk met een eigen
PostgreSQL-dienst, elk een deel van de bestanden.

**De verdeling is deterministisch en leest de bestanden zelf.** Elk testbestand onder `tests/integration` dat pytest
verzamelt krijgt een gewicht (het aantal testfuncties, AST, met literal `parametrize`-lijsten meegeteld) en gaat,
zwaarste eerst, naar de lichtste shard. De uitsluitingen komen uit `norecursedirs` in `pyproject.toml`: dezelfde
bron als pytest. Een nieuw testbestand komt dus vanzelf in een shard terecht;
`tests/architecture/test_ci_integratiesuite_past_in_de_tijd.py` bewaakt dat elk bestand in precies een shard zit en
dat de langste shard in de tijd van de job past.

**Schatting en meting.** Het gewicht is een ondergrens: 3480 geschat tegen 3731 verzameld (39 van 372 bestanden
wijken af, vooral parametrisaties via een constante). De `VEILIGHEIDSFACTOR` dekt dat.
"""

from __future__ import annotations

import ast
import functools
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATIE = REPO_ROOT / "tests" / "integration"

#: Aantal jobs in de matrix van `.github/workflows/ci-feature.yml` (job `integration`). De architectuurtest eist dat
#: de matrix daar precies 1..AANTAL_SHARDS noemt.
AANTAL_SHARDS = 5

#: Gemeten 2026-10-26: 3563 tests in 6000 s lokaal, zonder xdist (~1,7 s per test). Niet gemeten op de
#: GitHub-runner; de veiligheidsfactor hieronder is er mede daarom.
SECONDEN_PER_TEST = 1.7

#: Dekt de onderschatting van het AST-gewicht (3480 geschat, 3731 verzameld = +7 procent, met uitschieters per
#: bestand) en een tragere runner. Niet gemeten op GitHub: de eerste echte run is de meting.
VEILIGHEIDSFACTOR = 1.5


def _uitgesloten_mappen() -> set[str]:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return set(config["tool"]["pytest"]["ini_options"]["norecursedirs"])


def testbestanden() -> list[str]:
    """De testbestanden onder `tests/integration` die pytest verzamelt, als posix-pad, gesorteerd."""
    uitgesloten = _uitgesloten_mappen()
    paden: list[str] = []
    for pad in INTEGRATIE.rglob("test_*.py"):
        relatief = pad.relative_to(REPO_ROOT)
        if set(relatief.parts[:-1]) & uitgesloten:
            continue
        paden.append(relatief.as_posix())
    return sorted(paden)


def _vermenigvuldiger(decorators: list[ast.expr]) -> int:
    """Het aantal gevallen van een literal `@pytest.mark.parametrize(naam, [..])`; anders 1."""
    totaal = 1
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        functie = decorator.func
        naam = getattr(functie, "attr", getattr(functie, "id", ""))
        if (
            naam == "parametrize"
            and len(decorator.args) >= 2
            and isinstance(decorator.args[1], (ast.List, ast.Tuple))
        ):
            totaal *= max(len(decorator.args[1].elts), 1)
    return totaal


def _is_test(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
        "test"
    )


def _aantal_tests(pad: Path) -> int:
    boom = ast.parse(pad.read_text(encoding="utf-8"))
    totaal = 0
    for node in boom.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test(node):
            totaal += _vermenigvuldiger(node.decorator_list)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            klasse = _vermenigvuldiger(node.decorator_list)
            for lid in node.body:
                if isinstance(lid, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test(lid):
                    totaal += klasse * _vermenigvuldiger(lid.decorator_list)
    return totaal


@functools.cache
def _gewichten_eenmaal() -> tuple[tuple[str, int], ...]:
    """De AST-telling over alle testbestanden, een keer per proces: elke `shard()`-aanroep deed hem opnieuw
    (376 bestanden), waardoor de guard onder belasting minuten kostte (gemeten 2026-10-27: 110 s voor een test)."""
    return tuple((pad, max(_aantal_tests(REPO_ROOT / pad), 1)) for pad in testbestanden())


def gewichten() -> dict[str, int]:
    """Per testbestand het geschatte aantal tests (minimaal 1, zodat een bestand nooit gewichtloos is)."""
    return dict(_gewichten_eenmaal())


def verdeel(gewicht: dict[str, int], aantal: int) -> list[list[str]]:
    """Zwaarste bestand eerst naar de lichtste shard; gelijke stand gaat naar de laagste shard. Deterministisch."""
    shards: list[list[str]] = [[] for _ in range(aantal)]
    lasten = [0] * aantal
    for pad in sorted(gewicht, key=lambda p: (-gewicht[p], p)):
        doel = min(range(aantal), key=lambda i: (lasten[i], i))
        shards[doel].append(pad)
        lasten[doel] += gewicht[pad]
    return [sorted(shard) for shard in shards]


def shard(nummer: int) -> list[str]:
    """De bestanden van shard `nummer` (1 tot en met AANTAL_SHARDS)."""
    if not 1 <= nummer <= AANTAL_SHARDS:
        raise ValueError(f"shard {nummer} bestaat niet: kies 1 tot en met {AANTAL_SHARDS}")
    return verdeel(gewichten(), AANTAL_SHARDS)[nummer - 1]


def schatting_seconden(bestanden: list[str]) -> float:
    """De tijd die deze bestanden kosten: geschat aantal tests x seconden per test x veiligheidsfactor."""
    gewicht = gewichten()
    return sum(gewicht[b] for b in bestanden) * SECONDEN_PER_TEST * VEILIGHEIDSFACTOR


def main(argumenten: list[str]) -> int:
    if len(argumenten) != 1 or not argumenten[0].isdigit():
        print("gebruik: ci_integratie_shard.py <shardnummer>", file=sys.stderr)
        return 2
    try:
        bestanden = shard(int(argumenten[0]))
    except ValueError as fout:
        print(str(fout), file=sys.stderr)
        return 2
    print("\n".join(bestanden))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
