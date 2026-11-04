"""De naamcontrole van `scripts/pg_container_hulp.sh` laat alleen echte namen door (harde poort, eis 6).

Databasenamen en gebruikersnamen komen ongeschoond in `psql -c` terecht (`restore_db.sh`:
`CREATE DATABASE $DOEL`, `DROP DATABASE IF EXISTS $DOEL`, `datname = '$1'`). De enige verdediging is
`controleer_naam`. Tot 2026-10-14 toetste die met `grep -Eq '^...$'` op de uitvoer van `printf`:
`grep` toetst PER REGEL, dus een naam met een regeleinde en daarna SQL kwam erdoor omdat de eerste
regel klopte (Gate 2, security-reviewer, gemeten).

Deze tests draaien de bash-functie zelf, zonder docker of database. Ze slaan over als er geen
werkende `bash` is.

Mutatiebewijs (2026-10-14): de oude `grep`-controle terugzetten maakt de regeleinde-gevallen rood;
een controle die alles weigert maakt de drie goede namen rood.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="geen bash beschikbaar")


def _naam_is_toegestaan(naam: str) -> bool:
    """Draai `controleer_naam` in bash; de naam gaat via de omgeving zodat quoting niets verbergt."""
    assert BASH is not None
    uit = subprocess.run(
        [BASH, "-c", 'source scripts/pg_container_hulp.sh; controleer_naam test "$NAAM"'],
        cwd=REPO_ROOT,
        env={**os.environ, "NAAM": naam},
        capture_output=True,
        text=True,
        check=False,
    )
    return uit.returncode == 0


@pytest.mark.parametrize("naam", ["sanskritisetu", "proef_nieuw", "_x1"])
def test_a_plain_name_is_allowed(naam: str) -> None:
    assert _naam_is_toegestaan(naam)


@pytest.mark.parametrize(
    "naam",
    [
        "proef\nx; DROP DATABASE sanskritisetu",
        "proef\n",
        "x; DROP DATABASE sanskritisetu",
        "",
        "1abc",
        "a-b",
        "a b",
        "a'b",
    ],
)
def test_anything_else_is_refused(naam: str) -> None:
    assert not _naam_is_toegestaan(naam)
