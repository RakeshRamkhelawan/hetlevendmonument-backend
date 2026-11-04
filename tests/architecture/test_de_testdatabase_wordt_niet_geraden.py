"""Niets in `tests/integration` mag zelf raden welke database de testdatabase is (OP-243).

**Wat deze guard bewaakt.** Er is precies EEN plek waar de testdatabase-URL vandaan komt:
`tests/fixtures/testdatabase.py`, die een expliciete omgevingsvariabele leest en GEEN
terugval heeft. Deze guard blokkeert de twee manieren waarop dat opnieuw kan wegrotten:

1. Een poortscan die probeert te ontdekken waar Postgres draait. Op 2026-09-14 nam zo'n
   scan een vergeten `act`-servicecontainer voor de testdatabase.
2. Een hardgecodeerde verbinding-URL met een poortnummer, waarmee een bestand zich aan de
   centrale opgave onttrekt.

**Waarom een GROENE guard met een gedateerde uitzonderingslijst en geen rode test:** de
CI-testgate is blokkerend, en de resterende gevallen horen bij Fase 2 van OP-243. Zie
`.claude/rules/quality-gates.md`, "de guard-met-gedateerde-uitzondering" -- de vier eisen
daaruit zijn alle vier vervuld: de bevinding staat als OP-243 in de ADR met fase en
prioriteit, de lijst hieronder is gedateerd met een reden PER regel, er is een
staleness-test, en de guard is in beide richtingen mutatie-getest.

**Mutatiebewijs (2026-09-15), beide richtingen:**
  1. Een tijdelijk bestand `tests/integration/test_zz_mutatie.py` met
     `URL = "postgresql://postgres:postgres@localhost:5455/x"` -> ROOD.
  2. Een tijdelijk bestand met een `for port in [5435, 5455]:`-lus -> ROOD.
  3. Een tijdelijk bestand dat `testdatabase_url()` gebruikt -> GROEN (legitiem geval blijft
     toegestaan; zonder deze richting zou "weiger alles" een geldige oplossing zijn).
  4. De onaangeroerde boom -> GROEN.
"""

from __future__ import annotations

import re
from pathlib import Path

_INTEGRATIE = Path("tests/integration")

#: Een verbinding-URL met een expliciet poortnummer. Bewust op de URL en niet op het losse
#: getal: een kaal "5455" staat ook in toelichtingen en skip-redenen, en daarop toetsen
#: levert een guard op die tekst bewaakt in plaats van een handeling.
_URL_MET_POORT = re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s\"']*:\d{4,5}/")

#: Een lus over kandidaat-poorten -- de vorm van de scan die op 2026-09-15 is verwijderd.
_POORTSCAN = re.compile(r"for\s+\w+\s+in\s*[\[(][^)\]]*\b5[0-9]{3}\b[^)\]]*[\])]")

#: Gedateerde uitzonderingen, met een reden PER regel. Elke regel hoort bij Fase 2 van
#: OP-243 en mag alleen verdwijnen door hem op te lossen, niet door hem te verplaatsen.
KNOWN_RAADT_ZELF = {
    "tests/integration/test_data_protection_integration.py": (
        "2026-09-15 -- GEEN verbinding: twee URL's staan als tekst in testdata voor de "
        "geheimenscanner ('BAD: Hardcoded credentials'). Blijft permanent uitgezonderd; de "
        "staleness-test hieronder houdt in de gaten dat ze er echt nog staan."
    ),
}


def _overtreders() -> dict[str, list[str]]:
    """Bestanden onder tests/integration die zelf een database aanwijzen."""
    gevonden: dict[str, list[str]] = {}
    for pad in sorted(_INTEGRATIE.rglob("*.py")):
        tekst = pad.read_text(encoding="utf-8", errors="replace")
        regels = []
        for nr, regel in enumerate(tekst.splitlines(), start=1):
            kaal = regel.split("#", 1)[0]
            if _URL_MET_POORT.search(kaal) or _POORTSCAN.search(kaal):
                regels.append(f"{nr}: {regel.strip()[:100]}")
        if regels:
            gevonden[pad.as_posix()] = regels
    return gevonden


def test_geen_nieuwe_plek_raadt_zelf_de_testdatabase() -> None:
    """Nieuwe hardgecodeerde URL's en poortscans zijn geblokkeerd."""
    nieuw = {p: r for p, r in _overtreders().items() if p not in KNOWN_RAADT_ZELF}
    assert not nieuw, (
        "Deze bestanden wijzen zelf een database aan in plaats van "
        "`tests.fixtures.testdatabase.testdatabase_url()` te gebruiken:\n"
        + "\n".join(f"  {p}\n    " + "\n    ".join(r) for p, r in nieuw.items())
        + "\n\nOP-243: op 2026-09-14 nam een poortscan een vergeten act-servicecontainer "
        "voor de testdatabase. Gebruik de centrale resolver, of voeg dit bestand met een "
        "GEDATEERDE reden toe aan KNOWN_RAADT_ZELF."
    )


def test_de_uitzonderingslijst_is_niet_verouderd() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst -- anders rot hij dicht."""
    huidig = _overtreders()
    opgelost = [p for p in KNOWN_RAADT_ZELF if p not in huidig]
    assert not opgelost, (
        "Deze bestanden staan nog in KNOWN_RAADT_ZELF maar raden niets meer. "
        f"Haal ze uit de lijst: {sorted(opgelost)}"
    )


def test_de_scan_vindt_daadwerkelijk_bestanden() -> None:
    """Vangnet: een guard die niets inleest is altijd groen.

    Zonder deze test zou een typefout in het pad of een gewijzigde mapstructuur de guard
    stilletjes vacuum maken -- in dit project al vaker voorgekomen.
    """
    bestanden = list(_INTEGRATIE.rglob("*.py"))
    assert len(bestanden) > 50, (
        f"Slechts {len(bestanden)} bestanden gevonden onder {_INTEGRATIE} -- "
        "de guard leest vrijwel niets in en bewaakt dus niets."
    )
