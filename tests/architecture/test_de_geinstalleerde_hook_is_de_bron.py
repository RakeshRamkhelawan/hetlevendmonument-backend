"""De hook die git DRAAIT is dezelfde als de hook die in de repo STAAT.

WAAROM DEZE GUARD BESTAAT
-------------------------
`scripts/install-hooks.sh` KOPIEERT `scripts/hooks/*` naar de gedeelde `.git/hooks/`. Het
is geen symlink. Een wijziging aan `scripts/hooks/pre-push` doet dus NIETS totdat iemand
dat installatiescript opnieuw draait -- en niets herinnert je daaraan.

Gemeten 2026-09-17: de geinstalleerde `pre-push` dateerde van 10 september. Een reparatie
aan de poort die diezelfde dag in de repo werd gezet, zou stil niet hebben gedraaid. Dat
is de gevaarlijkste soort fout in dit project: een bewaker die je gecommit hebt, die groen
in de repo staat, en die in werkelijkheid niet meedoet.

Erger nog was de oorzaak dat het zo lang kon blijven staan: `install-hooks.sh` zocht naar
`<repo>/.git/hooks`, en in een gelinkte worktree is `.git` een BESTAND en geen map. Het
script viel daar af met "Run this script from inside the git repository" terwijl je er
gewoon in stond. CLAUDE.md schrijft voor dat elke parallelle sessie in een eigen worktree
werkt -- dus precies de plek waar iedereen werkt, was de plek waar hooks niet te
installeren waren. Beide zijn op 2026-09-17 gerepareerd; deze test bewaakt de uitkomst.

MUTATIEBEWIJS (2026-09-17, beide richtingen, een regel per element)
-------------------------------------------------------------------
    een regel toegevoegd aan de GEINSTALLEERDE pre-push    -> ROOD
    een regel toegevoegd aan de GEINSTALLEERDE pre-commit  -> ROOD
    installatiebestand verwijderd (niet geinstalleerd)     -> GROEN (terecht: zie hieronder)
    beide weer gelijkgetrokken                             -> GROEN

Een ONTBREKENDE hook is bewust geen fout. Een verse kloon en een CI-container hebben er
geen, en daar hoort deze test niet over te klagen. De uitspraak is nauwer en precies wat
misging: *staat hij geinstalleerd, dan is hij actueel.*
"""

from __future__ import annotations

import os
import subprocess  # nosec B404: alleen vaste git-argumenten
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BRON = REPO_ROOT / "scripts" / "hooks"


def _gedeelde_git_map() -> Path | None:
    """De GEDEELDE `.git`-map, ook vanuit een gelinkte worktree.

    `--git-common-dir` en niet `--git-dir`: vanuit een worktree wijst de tweede naar
    `.git/worktrees/<naam>`, en daar staan geen hooks.

    `GIT_*` wordt uit de omgeving geschrobd. Gemeten 2026-09-16: `git push` zet vanuit een
    gelinkte worktree `GIT_DIR` in de omgeving van zijn hooks, en `GIT_DIR` wint van `cwd`
    -- deze test kan dus tijdens een push draaien met een `GIT_DIR` die niet van haar is.
    """
    omgeving = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        uit = subprocess.run(  # nosec B603 B607: vaste argumenten
            ["git", "rev-parse", "--git-common-dir"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            env=omgeving,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    pad = Path(uit.stdout.strip())
    return pad if pad.is_absolute() else (REPO_ROOT / pad)


def _bronhooks() -> list[Path]:
    return sorted(p for p in BRON.glob("*") if p.is_file())


def test_de_bron_bevat_de_hooks_die_we_verwachten() -> None:
    """Niet-leegheid: zonder dit is de test hieronder trivially groen."""
    namen = {p.name for p in _bronhooks()}

    assert {"pre-push", "pre-commit"} <= namen, (
        f"`scripts/hooks/` bevat {sorted(namen)}. De poort leunt op `pre-push` en "
        "`pre-commit`; ontbreekt er een, dan bewaakt de test hieronder niets."
    )


def test_elke_geinstalleerde_hook_is_gelijk_aan_zijn_bron() -> None:
    """Staat een hook geinstalleerd, dan is hij actueel."""
    git_map = _gedeelde_git_map()
    if git_map is None or not (git_map / "hooks").is_dir():
        pytest.skip("geen gedeelde .git/hooks -- niets geinstalleerd om te vergelijken")

    verouderd: list[str] = []
    for bron in _bronhooks():
        geinstalleerd = git_map / "hooks" / bron.name
        if not geinstalleerd.is_file():
            continue  # niet geinstalleerd is geen fout -- zie de moduledocstring
        if geinstalleerd.read_bytes() != bron.read_bytes():
            verouderd.append(bron.name)

    assert not verouderd, (
        "Deze hooks staan geinstalleerd maar wijken af van `scripts/hooks/`: "
        f"{verouderd}.\n\n"
        "`.git/hooks/` is een KOPIE, geen symlink. Git draait dus de oude versie, en een "
        "reparatie die je net hebt gecommit doet niets -- zonder enige melding. "
        "Herstel met:\n\n"
        "    bash scripts/install-hooks.sh\n"
    )


def test_de_hooks_hebben_unix_regeleindes() -> None:
    """De hooks staan in LF, zodat elke werkkopie hetzelfde bestand ziet.

    Dit toetst de EIGENSCHAP, niet twee bestanden tegen elkaar.
    `test_elke_geinstalleerde_hook_is_gelijk_aan_zijn_bron` vergelijkt de GEINSTALLEERDE
    hook met de BRON; zijn die allebei CRLF, dan staat die test groen terwijl het verschil
    met andere werkkopieen blijft bestaan. A met B vergelijken is niet hetzelfde als de
    eis toetsen.

    Gemeten 2026-10-01, en zo is dit gevonden: in een verse `git worktree` kwam
    `scripts/hooks/pre-push` met 343 CR-tekens, terwijl dezelfde commit in de hoofdmap nul
    CR gaf. Oorzaak: `core.autocrlf=true` en een `.gitattributes` die alleen `*.sh` dekte --
    de hooks heten `pre-commit` en `pre-push` en hebben geen extensie. Opgelost met de regel
    `scripts/hooks/* text eol=lf`.

    WAT DIT WEL EN NIET VOORKOMT, want de eerste versie van deze docstring beweerde te veel:
      WEL: het valse alarm. De vergelijkingstest hierboven sloeg aan in een worktree terwijl
           er niets verouderd was.
      NIET: een stilstaande hook op deze machine. Gemeten: `.git/hooks/pre-commit` begint
           met `#!/usr/bin/env bash` gevolgd door een CR EN voert zijn controles gewoon uit.
           Git for Windows start hooks kennelijk niet via de kale shebang. Een CR achter een
           shebang breekt wel op andere opstellingen, en dat is de reden dat deze eis blijft
           staan -- maar "hij draait niet" was onjuist en is hier rechtgezet.

    Mutatiebewijs (beide richtingen, 2026-10-01):
      scripts/hooks/pre-commit stond bij het schrijven van deze test op CRLF -> ROOD
      na normalisatie naar LF                                                -> GROEN
    """
    fout = []
    for hook in sorted(BRON.iterdir()):
        if not hook.is_file():
            continue
        inhoud = hook.read_bytes()
        aantal_cr = inhoud.count(b"\r")
        if aantal_cr:
            fout.append(f"{hook.name}: {aantal_cr} CR-tekens")

    assert not fout, (
        "Deze hooks hebben Windows-regeleindes en starten daardoor NIET: "
        + ", ".join(fout)
        + ". Controleer dat `.gitattributes` de regel `scripts/hooks/* text eol=lf` "
        "bevat en check de bestanden opnieuw uit "
        "(`git rm --cached scripts/hooks/* && git checkout scripts/hooks/`)."
    )
