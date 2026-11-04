"""Weigert niet-ASCII in Python-broncode (NOOIT-lijst): de enige definitie, voor de pre-commit EN de CI.

Gebruik:
    python scripts/check_non_ascii.py <bestand> [<bestand> ...]   # de gestagede bestanden (pre-commit)
    python scripts/check_non_ascii.py --alles                     # alle gevolgde .py onder src/, scripts/, mcp-server/ (CI)

Waarom dit een script is en geen grep in een workflow. Gemeten (CI-run 39852524654 op develop, 2026-10-22): de CI-stap
"NOOIT-lijst: non-ASCII in Python gate" faalde op twee tekens in `src/`, terwijl de lokale controles ze lieten passeren: alleen de CI had
een eigen `grep`. Een controle die op twee plekken los wordt bijgehouden loopt uit elkaar. Hier staan mappen, uitzondering en melding
op een plek; `tests/architecture/test_precommit_weigert_niet_ascii.py` bewaakt dat de pre-commit en de CI dit script aanroepen.

Een bestand dat niet als UTF-8 te lezen is, telt als schending: het is het ergste geval van de klasse die dit moet vangen, en wordt dus
niet stil overgeslagen. Een BOM (U+FEFF) is ook niet-ASCII.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
#: De mappen die de CI scant, ook mcp-server/ omdat die deel uitmaakt van de repo.
WORTELS = ("src", "scripts", "mcp-server")
#: Gearchiveerde migraties worden niet meer aangeraakt en zijn buiten de NOOIT-lijst gehouden.
ARCHIEF = "src/alembic/versions/archive/"
MAX_MELDINGEN = 20


def vind_schendingen(tekst: str) -> list[tuple[int, int, str]]:
    """(regel, kolom, 'U+XXXX') voor elk teken buiten ASCII; regel en kolom tellen vanaf 1."""
    gevonden: list[tuple[int, int, str]] = []
    # Splitsen op "\n" en NIET `splitlines()`: die splitst ook op U+0085, U+2028 en U+2029 en gooit die tekens weg, zodat een bestand
    # waarin zo'n teken het enige niet-ASCII-teken is erdoor kwam (security-review Gate 2, 2026-10-23). De oude grep ving het wel.
    for regelnummer, regel in enumerate(tekst.split("\n"), start=1):
        if regel.isascii():
            continue
        for kolom, teken in enumerate(regel, start=1):
            if ord(teken) > 127:
                gevonden.append((regelnummer, kolom, f"U+{ord(teken):04X}"))
    return gevonden


def controleer(bestand: Path) -> list[str]:
    """De meldingen voor een bestand; leeg als het schoon is."""
    try:
        tekst = bestand.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as fout:
        return [f"{bestand}: niet als UTF-8 te lezen ({type(fout).__name__})"]
    return [f"{bestand}:{regel}:{kolom} {teken}" for regel, kolom, teken in vind_schendingen(tekst)]


def alle_bestanden(repo: Path = REPO) -> list[Path]:
    """De door git gevolgde .py onder de CI-mappen, zonder het archief.

    `-z`: zonder dit citeert git een naam met een accent als "src/caf\\303\\251.py" (`core.quotepath`, de standaard), en dan zag het
    filter op `.py` en het archiefvoorvoegsel zo'n bestand niet (security-review Gate 2, 2026-10-23).
    """
    uit = subprocess.run(
        ["git", "ls-files", "-z", "--", *WORTELS],
        capture_output=True,
        cwd=repo,
        check=True,
    ).stdout.decode("utf-8")
    namen = [naam for naam in uit.split("\0") if naam]
    return [repo / naam for naam in namen if naam.endswith(".py") and not naam.startswith(ARCHIEF)]


def main(argv: list[str]) -> int:
    if argv == ["--alles"]:
        bestanden = alle_bestanden()
    else:
        bestanden = [Path(arg) for arg in argv]

    meldingen: list[str] = []
    for bestand in bestanden:
        meldingen.extend(controleer(bestand))

    if meldingen:
        print(f"{len(meldingen)} niet-ASCII teken(s) in Python-broncode (NOOIT-lijst):")
        for melding in meldingen[:MAX_MELDINGEN]:
            print(f"  {melding}")
        if len(meldingen) > MAX_MELDINGEN:
            print(f"  ... en nog {len(meldingen) - MAX_MELDINGEN}")
        print("Gebruik uitsluitend ASCII in code, comments en logs.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
