"""Geen enkel Python-bronbestand begint met een UTF-8 BOM (ADR-036, blok 4).

**Waarom een APART bestand naast `test_no_non_ascii_in_core_zone.py`.** Die guard is
GEZONEERD: hij bewaakt vier mappen (`src/core/als/agents`, `src/core/tool_broker`,
`src/core/copilot/council`, `src/core/api/v1/agentic`) en dat is een bewuste keuze, want
813 van de 4.773 getrackte `.py`-bestanden bevatten non-ASCII. Boombreed zou daar een
uitzonderingslijst van 813 regels vragen, en dat is geen guard meer.

Een BOM is een ander geval. Hij heeft in een Python-bronbestand NUL legitiem gebruik: Python
accepteert hem, maar hij staat onzichtbaar voor het eerste teken, hij is niet te zien in een
diff, en CLAUDE.md verbiedt non-ASCII in code. Daarom kan deze helft wel boombreed, met NUL
uitzonderingen -- en daarom staat hij in een eigen bestand met een naam die zegt wat hij doet.

**Waarom hij nodig is, gemeten en niet aangenomen.** Op 2026-09-03 stonden er 17 BOMs in
getrackte `.py`-bestanden op develop. Geen ervan zit in een van de vier zones, en
`KNOWN_NON_ASCII` in die andere guard is leeg -- ze waren dus niet vrijgesteld, ze vielen
buiten beeld. Twee ervan zijn in dezelfde week onafhankelijk gevonden: een Copilot-review
meldde `src/core/api/v1/digital_twin/service.py`, en een handmatige scan vond
`src/alembic/versions/fc090c9d7267_adr029_missing_tables.py`. Twee losse vondsten in een week
op een probleem waar niets tegen beschermt, betekent dat het terugkomt.

De zonering van die andere guard is trouwens niet fout maar reactief ontstaan: zijn eigen
docstring noemt een eerdere BOM in `api/v1/agentic/monitoring.py`, en dat is precies waarom die
map een zone is. De zone is nooit meegegroeid met de plek waar het probleem KAN optreden. Dat is
hetzelfde patroon als OP-11 (tests/core buiten de poort) en OP-180 (tests/contracts).

**Waarom `git ls-files` en niet `Path.rglob`.** Boombreed rglob'en vanaf de repo-root loopt door
`.venv`, `node_modules` en `.git`. `git ls-files` geeft exact de getrackte verzameling. De
returncode wordt gecontroleerd: zonder git kan deze guard niets bewijzen en dan hoort hij te
falen in plaats van stilletjes nul te meten.

**Mutatiebewijs -- beide richtingen, uitgevoerd en gemeten 2026-09-03.**

- een BOM voor het eerste teken van een bestaand poortbestand: verwacht ROOD, gemeten ROOD;
- hetzelfde bestand zonder BOM: verwacht GROEN, gemeten GROEN;
- `git ls-files` laten falen (verkeerde cwd): verwacht ROOD via de returncode-controle, niet
  stilletjes nul bestanden -- verwacht ROOD, gemeten ROOD.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

BOM = b"\xef\xbb\xbf"


def _tracked_python_files() -> list[Path]:
    """Elk getrackt `.py`-bestand. Faalt LUID als git niet beschikbaar is."""
    resultaat = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if resultaat.returncode != 0:
        raise AssertionError(
            "git ls-files gaf returncode %s -- zonder git meet deze guard nul bestanden en zou "
            "hij stilletjes groen melden: %s"
            % (resultaat.returncode, resultaat.stderr.decode("utf-8", "replace").strip())
        )
    namen = [n for n in resultaat.stdout.decode("utf-8").split("\0") if n]
    return [REPO_ROOT / n for n in namen]


@pytest.mark.architecture
def test_the_scan_finds_python_files_at_all() -> None:
    """Vangnet: zonder bestanden bewaakt deze guard niets.

    Rood te maken door `git ls-files` een patroon te geven dat niets matcht.
    """
    aantal = len(_tracked_python_files())
    assert aantal > 1000, (
        f"Slechts {aantal} getrackte .py-bestanden gevonden; op 2026-09-03 waren het er 4.773. "
        "Is de scan stukgelopen, dan meldt deze guard nooit meer iets."
    )


@pytest.mark.architecture
def test_no_python_source_starts_with_a_bom() -> None:
    """Geen enkel Python-bronbestand begint met een UTF-8 BOM.

    Nul uitzonderingen, en dat kan omdat de 17 die er op 2026-09-03 stonden in dezelfde
    wijziging zijn opgeruimd. Rood te maken door drie bytes (EF BB BF) voor het eerste teken
    van een willekeurig `.py`-bestand te zetten.
    """
    met_bom = [
        pad.relative_to(REPO_ROOT).as_posix()
        for pad in _tracked_python_files()
        if pad.exists() and pad.read_bytes()[:3] == BOM
    ]
    assert not met_bom, (
        "Deze Python-bestanden beginnen met een UTF-8 BOM:\n"
        + "\n".join(f"  {naam}" for naam in sorted(met_bom))
        + "\n\nEen BOM heeft in een Python-bronbestand geen enkel doel. Hij staat onzichtbaar "
        "voor het eerste teken, is niet te zien in een diff, en CLAUDE.md verbiedt non-ASCII in "
        "code. Meestal komt hij van een editor die het bestand als cp1252 of 'UTF-8 met BOM' "
        "opslaat -- controleer die instelling, anders komt hij terug.\n"
        "Weghalen kan zonder risico: het zijn drie bytes en Python leest het bestand daarna "
        "identiek."
    )
