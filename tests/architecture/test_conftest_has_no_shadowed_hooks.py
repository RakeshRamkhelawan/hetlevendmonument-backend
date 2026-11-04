"""Geen pytest-hook staat twee keer in dezelfde conftest (ADR-036 OP-44).

**De bevinding (historisch).** `tests/conftest.py` definieerde `pytest_collection_modifyitems`
TWEE keer. Python houdt de laatste, dus de eerste was dode code -- inclusief de auto-skip die tests
oversloeg wanneer PostgreSQL niet bereikbaar is. Die skip heeft dus nooit gewerkt. Gevonden in
ronde 5 van BE-AGT-045; pyright meldt het als `reportRedeclaration`, maar `tests/` valt buiten de
pyright-configuratie en daarom stond het niet in de 0-errors-baseline.

**OPGELOST 2026-08-31 (OP-44).** De verificatieronde is gedraaid en de dubbeling is weg. De dode
hook is VERWIJDERD, niet samengevoegd, op grond van twee metingen:

1. Overbodig. Alle 43 items die de dode hook zou raken (gemeten over 18.235 gecollecteerde tests)
   hebben al een eigen, beter gerichte guard -- zie de toelichting bovenaan `tests/conftest.py`.
   Samenvoegen veranderde 0 van de 16.158 uitkomsten in tests/unit+architecture+core: voor 666s
   respectievelijk 633s draaide alles identiek, op de skip-REDEN van twee tests na.
2. Schadelijk. De hook keek naar TEST_PG_PORT (default 5455), terwijl `tests/integration_real` op
   5435 werkt. Gemeten met Postgres OP 5435 en 5455 dicht: de samengevoegde hook skipte daar alle
   14 `requires_postgres`-tests met "PostgreSQL not reachable at localhost:5455", waaronder 3 die
   zonder de hook GROEN draaien tegen diezelfde database.

**VERBREED 2026-09-01, na een onafhankelijke Gate 2.** De eerste versie telde alleen `def`s in
`tree.body` en beloofde in zijn slotzin dat hij voorkwam dat "een WERKENDE hook overschreven"
wordt. Dat deed hij niet. De reviewer heeft de detectiefunctie geimporteerd en tegen synthetische
conftests gedraaid: van de VIER manieren waarop een module-level hookbinding stil overschreven kan
worden, ving hij er EEN.

| Vorm | oude functie | runtime |
| --- | --- | --- |
| twee `def` op moduleniveau | ROOD (2) | tweede wint |
| `def` gevolgd door `pytest_x = _vervanger` | GROEN | de naam wijst naar `_vervanger` |
| `def` in een `if`-blok gevolgd door een `def` op moduleniveau | GROEN | tweede wint stil |
| `def` in een `try`-blok gevolgd door een `def` op moduleniveau | GROEN | tweede wint stil |

Dat laatste is geen bedacht geval: `tests/conftest.py` gebruikt al `try/except` rond optionele
imports. Deze guard telt daarom nu BINDINGEN en geen definities, en hij doet dat met de
uitvoeringssemantiek erbij -- de takken van een `if/else` sluiten elkaar uit en tellen samen voor
EEN, een `finally` draait altijd en telt er dus bij op. Zonder die nuance zou een legitieme
platform-afhankelijke hook (Windows in de ene tak, POSIX in de andere) vals rood gaan.

Wat de guard bewust NIET doet: `ast.walk` gebruiken. Die duikt functiebodies in, en dat is in dit
project al twee keer misgegaan. De recursie hieronder gaat alleen `If`, `Try` en `With` in, nooit
een `FunctionDef` of een `ClassDef`.

**Mutatiebewijs -- een regel per vorm, beide richtingen, op synthetische bronnen** (zie
`_REGEL_GEVALLEN` onderaan en `test_the_rule_itself_catches_every_known_form`, dat de mutaties
uitvoert in plaats van ze alleen te beschrijven). Verplicht rood:

- twee `def pytest_collection_modifyitems` op moduleniveau;
- `def pytest_configure` gevolgd door `pytest_configure = _vervanger`;
- `def pytest_configure` in een `if sys.platform`-blok, daarna nog een op moduleniveau;
- `def pytest_configure` in een `try`-blok, daarna nog een op moduleniveau;
- een `def` in een `try`-body en een tweede in de bijbehorende `finally`.

Verplicht GROEN (zonder deze helft is "meld alles" een geldige oplossing):

- een dubbele NIET-hook (`helper_not_a_hook`);
- een hook die alleen in de `if`-tak staat en een gelijknamige alleen in de `else`-tak;
- een geneste `def` met dezelfde naam binnen een andere functie (de `ast.walk`-valkuil);
- een gelijknamige methode in een klassenbody;
- een enkele hook in een `try`-blok zonder tweede binding.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Conftest-bestanden met een dubbel gebonden hook. Bestand -> (hook, reden met datum).
#: LEEG sinds 2026-08-31: OP-44 was de laatste en is opgelost. Een nieuwe regel hier hoort een
#: datum en een reden te hebben, en `test_known_shadowed_hooks_are_not_stale` dwingt af dat hij
#: eruit gaat zodra de dubbeling verdwenen is.
KNOWN_SHADOWED_HOOKS: dict[str, tuple[str, str]] = {}

#: De hooks die pytest per conftest hoogstens een keer hoort te zien. Niet alle functies: een
#: hulpfunctie mag herhaald worden, een HOOK niet -- die wordt door pytest op naam opgezocht.
_HOOK_PREFIX = "pytest_"


def _conftest_paths() -> list[Path]:
    return sorted(REPO_ROOT.glob("tests/**/conftest.py"))


def _elkaar_uitsluitend(*tellingen: Counter[str]) -> Counter[str]:
    """Het maximum per naam: van elkaar uitsluitende takken draait er hoogstens een."""
    resultaat: Counter[str] = Counter()
    for telling in tellingen:
        for naam, aantal in telling.items():
            if aantal > resultaat[naam]:
                resultaat[naam] = aantal
    return resultaat


def _bindingen(stmts: list[ast.stmt]) -> Counter[str]:
    """Tel per hooknaam hoe vaak hij op moduleniveau GEBONDEN wordt.

    Een binding is een `def`, een `async def`, of een toewijzing aan de kale naam. Recursie gaat
    `If`, `Try` en `With` in -- dat zijn statements die op moduleniveau draaien -- en nooit een
    `FunctionDef` of `ClassDef`, want een naam daarbinnen is een andere naam.
    """
    totaal: Counter[str] = Counter()
    for node in stmts:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith(_HOOK_PREFIX):
                totaal[node.name] += 1
        elif isinstance(node, ast.Assign):
            for doel in node.targets:
                if isinstance(doel, ast.Name) and doel.id.startswith(_HOOK_PREFIX):
                    totaal[doel.id] += 1
        elif isinstance(node, ast.AnnAssign):
            doel_naam = node.target
            if (
                node.value is not None
                and isinstance(doel_naam, ast.Name)
                and doel_naam.id.startswith(_HOOK_PREFIX)
            ):
                totaal[doel_naam.id] += 1
        elif isinstance(node, ast.If):
            totaal += _elkaar_uitsluitend(_bindingen(node.body), _bindingen(node.orelse))
        elif isinstance(node, ast.Try):
            # body en orelse horen bij elkaar (orelse draait alleen als body slaagde); de
            # handlers sluiten die combinatie uit; finalbody draait altijd en telt er dus bij op.
            geslaagd = _bindingen(node.body) + _bindingen(node.orelse)
            gefaald = _elkaar_uitsluitend(*(_bindingen(h.body) for h in node.handlers))
            totaal += _elkaar_uitsluitend(geslaagd, gefaald) + _bindingen(node.finalbody)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            totaal += _bindingen(node.body)
    return totaal


def _duplicate_hooks_in_source(bron: str) -> dict[str, int]:
    """De regel zelf, los van een bestand -- zo is hij op synthetische bronnen te toetsen."""
    telling = _bindingen(ast.parse(bron).body)
    return {naam: aantal for naam, aantal in telling.items() if aantal > 1}


def _duplicate_hooks(path: Path) -> dict[str, int]:
    return _duplicate_hooks_in_source(path.read_text(encoding="utf-8"))


#: Elk geval is een echte vorm die op moduleniveau een binding oplevert, met het aantal dat de
#: regel MOET tellen. De ROOD-helft is de detectie, de GROEN-helft sluit "meld alles" uit.
_REGEL_GEVALLEN: tuple[tuple[str, str, bool], ...] = (
    (
        "twee defs op moduleniveau",
        "def pytest_configure(c):\n    pass\n\n\ndef pytest_configure(c):\n    pass\n",
        True,
    ),
    (
        "def gevolgd door een toewijzing aan dezelfde naam",
        "def pytest_configure(c):\n    pass\n\n\ndef _v(c):\n    pass\n\n\npytest_configure = _v\n",
        True,
    ),
    (
        "def in een if-blok, daarna een op moduleniveau",
        "import sys\n\nif sys.platform == 'win32':\n\n    def pytest_configure(c):\n"
        "        pass\n\n\ndef pytest_configure(c):\n    pass\n",
        True,
    ),
    (
        "def in een try-blok, daarna een op moduleniveau",
        "try:\n\n    def pytest_configure(c):\n        pass\n\nexcept ImportError:\n    pass\n\n"
        "\ndef pytest_configure(c):\n    pass\n",
        True,
    ),
    (
        "def in de try-body en een tweede in de finally",
        "try:\n\n    def pytest_configure(c):\n        pass\n\nfinally:\n\n"
        "    def pytest_configure(c):\n        pass\n",
        True,
    ),
    (
        "geannoteerde toewijzing naast een def",
        "from typing import Any\n\n\ndef pytest_configure(c):\n    pass\n\n\n"
        "pytest_configure: Any = None\n",
        True,
    ),
    (
        "LEGITIEM: dubbele niet-hook",
        "def helper_not_a_hook():\n    pass\n\n\ndef helper_not_a_hook():\n    pass\n",
        False,
    ),
    (
        "LEGITIEM: de ene tak Windows, de andere POSIX",
        "import sys\n\nif sys.platform == 'win32':\n\n    def pytest_configure(c):\n"
        "        pass\n\nelse:\n\n    def pytest_configure(c):\n        pass\n",
        False,
    ),
    (
        "LEGITIEM: geneste def met dezelfde naam binnen een functie",
        "def pytest_configure(c):\n    def pytest_configure(inner):\n        pass\n\n"
        "    return pytest_configure\n",
        False,
    ),
    (
        "LEGITIEM: gelijknamige methode in een klassenbody",
        "def pytest_configure(c):\n    pass\n\n\nclass Plugin:\n"
        "    def pytest_configure(self, c):\n        pass\n",
        False,
    ),
    (
        "LEGITIEM: een enkele hook in een try-blok",
        "try:\n\n    def pytest_configure(c):\n        pass\n\nexcept ImportError:\n    pass\n",
        False,
    ),
    (
        "LEGITIEM: toewijzing aan een attribuut, geen kale naam",
        "class N:\n    pass\n\n\nn = N()\n\n\ndef pytest_configure(c):\n    pass\n\n\n"
        "n.pytest_configure = pytest_configure\n",
        False,
    ),
)


@pytest.mark.parametrize(("omschrijving", "bron", "verwacht_dubbel"), _REGEL_GEVALLEN)
def test_the_rule_itself_catches_every_known_form(
    omschrijving: str, bron: str, verwacht_dubbel: bool
) -> None:
    """De REGEL wordt gemuteerd, niet de productiecode -- een regel per vorm.

    Waarom zo: de vorige mutatieronde noteerde de bewijzen als tekst in een docstring en
    controleerde alleen de vorm die de guard toch al ving. Een tabel met synthetische bronnen
    voert elke mutatie bij elke run uit, en de GROEN-helft sluit uit dat "meld alles" een geldige
    implementatie is.
    """
    gevonden = _duplicate_hooks_in_source(bron)
    if verwacht_dubbel:
        assert gevonden, (
            f"{omschrijving}: deze vorm bindt een hooknaam twee keer op moduleniveau en moet "
            f"betrapt worden, maar de regel meldt niets. Gevonden: {gevonden}"
        )
    else:
        assert not gevonden, (
            f"{omschrijving}: dit is een legitieme vorm en mag niet gemeld worden. "
            f"Gevonden: {gevonden}"
        )


def test_the_scan_finds_hooks_at_all() -> None:
    """Vangnet: zonder gevonden hooks bewaakt deze guard niets."""
    total = 0
    for path in _conftest_paths():
        total += sum(_bindingen(ast.parse(path.read_text(encoding="utf-8")).body).values())

    assert total > 0, (
        "Geen enkele pytest-hook gevonden in de conftest-bestanden. Verplaatst of hernoemd? "
        "Zolang de scan leeg terugkomt, meldt deze guard nooit iets."
    )


def test_no_new_shadowed_hook() -> None:
    """Een nieuwe dubbele hookbinding is geblokkeerd."""
    offenders: dict[str, dict[str, int]] = {}
    for path in _conftest_paths():
        duplicates = _duplicate_hooks(path)
        if not duplicates:
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        known = KNOWN_SHADOWED_HOOKS.get(relative)
        remaining = {
            name: count for name, count in duplicates.items() if known is None or name != known[0]
        }
        if remaining:
            offenders[relative] = remaining

    assert not offenders, (
        f"Deze conftest-bestanden binden een pytest-hook meer dan een keer: {offenders}. "
        "Python houdt de LAATSTE binding, dus de eerdere is dode code -- zonder foutmelding. "
        "Dat geldt ook voor een toewijzing (`pytest_x = _vervanger`) en voor een `def` in een "
        "`if`- of `try`-blok gevolgd door een op moduleniveau. Voeg de definities samen, of zet "
        "de hook met datum en reden in KNOWN_SHADOWED_HOOKS."
    )


def test_known_shadowed_hooks_are_not_stale() -> None:
    """Een opgeloste dubbeling MOET uit de lijst, anders rot hij dicht."""
    stale: list[str] = []
    for relative, (hook, _reason) in KNOWN_SHADOWED_HOOKS.items():
        path = REPO_ROOT / relative
        if not path.exists() or hook not in _duplicate_hooks(path):
            stale.append(f"{relative}::{hook}")

    assert not stale, (
        f"Deze hooks zijn niet meer dubbel gebonden (of het bestand bestaat niet): {stale}. "
        "Haal ze uit KNOWN_SHADOWED_HOOKS, anders dekt de lijst iets anders dan hij beweert."
    )
