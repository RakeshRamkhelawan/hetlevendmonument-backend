"""Het gereedschap dat de kwaliteitspoorten draait, moet de versie zijn die
requirements-test.txt voorschrijft.

WAAROM DEZE GUARD BESTAAT (gevonden 2026-09-30)
------------------------------------------------
Twee sessies draaiden `python -m pyright` op dezelfde code, dezelfde commit, dezelfde map.
Een sessie meldde "1 error", de andere "0 errors, 38 warnings". De oorzaak: sessie A draaide
buiten de project-.venv en gebruikte de globale Python 3.13-installatie.

  Sessie A (globale Python 3.13, BUITEN .venv):
    pyright 1.1.407 -> 1 error, 14 warnings

  Sessie B (.venv actief, gepinde gereedschappen):
    pyright 1.1.411 -> 0 errors, 38 warnings

De pin EN de gepinde installatie bestaan al -- in requirements-test.txt EN in .venv.
Wat ontbrak was een controle die ROOD wordt als de draaiende sessie buiten die omgeving
draait en zo het verkeerde gereedschap gebruikt.

Hetzelfde patroon sloopte eerder de mypy-meting: requirements-test.txt pinde niets,
iedereen mat met een andere versie, en "52, 69 of 39 fouten" waren allemaal correct voor
de desbetreffende versie. Wie toen 23 "overbodige" ignores had opgeruimd, had CI gesloopt
(quality-gates.md, paragraaf over de mypy-baseline).

MUTATIEBEWIJS (2026-09-30, beide richtingen, zonder handmatige mutatie)
-----------------------------------------------------------------------
Twee echte omgevingen leveren het bewijs gratis:

  Sessie A (globale Python 3.13, BUITEN .venv -- pyright 1.1.407, mypy 1.18.2):
    test_pyright_versie_is_gepind -> ROOD (1.1.407 != 1.1.411)
    test_mypy_versie_is_gepind    -> ROOD (1.18.2 != 2.3.0)
    alle types-* tests            -> ROOD (verkeerde of ontbrekende versies)

  Sessie A na activeren .venv (pyright 1.1.411, mypy 2.3.0):
    8 passed -- alle tests GROEN

  Sessie B (.venv actief, pyright 1.1.411, mypy 2.3.0):
    8 passed -- alle tests GROEN

De parametrize-tests op types-* zijn ROOD buiten .venv en GROEN erin op dezelfde gronden.

TYPES-* PAKKETTEN
-----------------
De zes types-*-pakketten worden bewaakt via importlib.metadata: er is geen CLI-equivalent.
Dit leest uit de actieve Python-omgeving, wat overeenkomt met wat mypy gebruikt.
Het is NIET hetzelfde als `python -m pyright --version`: die aanroep gaat via een subprocess
en garandeert dat het commando dat de poort aanroept ook bevraagd wordt. Voor type-stubs
bestaat dat onderscheid niet -- mypy importeert ze direct.
"""

from __future__ import annotations

import importlib.metadata
import re
import subprocess  # nosec B404: alleen sys.executable + vaste module-argumenten
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = REPO_ROOT / "requirements-test.txt"


def _lees_pin(pakket: str) -> str:
    """Lees de gepinde versie van een pakket uit requirements-test.txt.

    Leest altijd uit het BESTAND zodat de test meebeweegt zodra de pin wijzigt.
    """
    tekst = REQUIREMENTS.read_text(encoding="utf-8")
    patroon = re.compile(rf"^{re.escape(pakket)}==(.+)$", re.MULTILINE)
    treffer = patroon.search(tekst)
    if treffer is None:
        pytest.fail(f"{pakket} niet gevonden in {REQUIREMENTS.relative_to(REPO_ROOT)}")
    return treffer.group(1).strip()


def _versie_via_module(module: str) -> str:
    """Vraag de versie op via `python -m <module> --version`.

    Gebruikt sys.executable zodat precies de Python-omgeving wordt bevraagd die ook
    de kwaliteitspoorten uitvoert -- niet welke `python` toevallig in PATH staat.
    """
    uitkomst = subprocess.run(  # nosec B603: sys.executable + vaste lijst-argumenten
        [sys.executable, "-m", module, "--version"],
        capture_output=True,
        text=True,
    )
    uitvoer = (uitkomst.stdout + uitkomst.stderr).strip()
    treffer = re.search(r"(\d+\.\d+(?:\.\d+)*)", uitvoer)
    if treffer is None:
        pytest.fail(
            f"Geen versienummer gevonden in uitvoer van"
            f" `python -m {module} --version`: {uitvoer!r}"
        )
    return treffer.group(1)


def test_pyright_versie_is_gepind() -> None:
    """De draaiende pyright-versie moet overeenkomen met de pin in requirements-test.txt.

    Bevraging via `python -m pyright --version` -- hetzelfde commando dat Gate 3 aanroept.
    """
    pin = _lees_pin("pyright")
    draaiend = _versie_via_module("pyright")
    assert draaiend == pin, (
        f"pyright draait als {draaiend!r} maar requirements-test.txt schrijft {pin!r} voor.\n"
        f"Installeer de juiste versie: pip install pyright=={pin}"
    )


def test_mypy_versie_is_gepind() -> None:
    """De draaiende mypy-versie moet overeenkomen met de pin in requirements-test.txt.

    Bevraging via `python -m mypy --version` -- hetzelfde pad dat
    scripts/run_mypy_audit.py intern aanroept.
    """
    pin = _lees_pin("mypy")
    draaiend = _versie_via_module("mypy")
    assert draaiend == pin, (
        f"mypy draait als {draaiend!r} maar requirements-test.txt schrijft {pin!r} voor.\n"
        f"Installeer de juiste versie: pip install mypy=={pin}"
    )


GEPINDE_TYPES_PAKKETTEN = [
    "types-redis",
    "types-requests",
    "types-aiofiles",
    "types-PyYAML",
    "types-python-dateutil",
    "types-psycopg2",
]


@pytest.mark.parametrize("pakket", GEPINDE_TYPES_PAKKETTEN)
def test_types_pakket_is_gepinde_versie(pakket: str) -> None:
    """Elk types-*-pakket moet de versie hebben die requirements-test.txt voorschrijft.

    Bevraging via importlib.metadata -- er is geen CLI-equivalent voor type-stub-pakketten.
    Dit leest uit de actieve Python-omgeving, wat overeenkomt met wat mypy gebruikt.
    """
    pin = _lees_pin(pakket)
    try:
        geinstalleerd = importlib.metadata.version(pakket)
    except importlib.metadata.PackageNotFoundError:
        pytest.fail(
            f"{pakket} is niet geinstalleerd maar requirements-test.txt"
            f" schrijft {pin!r} voor."
        )
    assert geinstalleerd == pin, (
        f"{pakket} is versie {geinstalleerd!r} maar requirements-test.txt"
        f" schrijft {pin!r} voor.\n"
        f"Installeer de juiste versie: pip install {pakket}=={pin}"
    )
