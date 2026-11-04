"""Een gitlink zonder `.gitmodules`-entry breekt `git submodule` in elke CI-job.

**Hoe dit gevonden is.** Elke van de vijf CI-jobs eindigde met de waarschuwing
`The process '/usr/bin/git' failed with exit code 128`. De regel ervoor, in de post-checkout
van `actions/checkout`, was:

    fatal: No url found for submodule path 'Kimi_Agent_Audit filenextjs/app/app' in .gitmodules

`Kimi_Agent_Audit filenextjs/app/app` is een geneste git-repo die per ongeluk als gitlink
(mode 160000) in de index is gecommit, in commit 5989b772, zonder bijbehorende `.gitmodules`.
Het stond op BEIDE branches. Alleen de pointer was getrackt: van de 254 getrackte bestanden
onder `Kimi_Agent_Audit filenextjs/` viel er geen enkele binnen dat pad, dus het verwijderen
van de pointer verliest niets.

**Waarom deze guard STRUCTUUR toetst en geen tekst.** Hij leest de index-MODUS uit
`git ls-files -s` en de padwaarden uit `.gitmodules` via `git config`, zodat git zelf het
parsen doet. Een variant die naar de string `submodule` of naar een padnaam zoekt, zou groen
blijven zodra iemand de map hernoemt of de naam in een comment laat staan -- precies de
faalvorm die `.claude/rules/quality-gates.md` beschrijft.

**Mutatietest (uitgevoerd, beide richtingen).**
- Een tijdelijke gitlink toevoegen met `git update-index --add --cacheinfo 160000,<sha>,tmp/x`
  maakt deze test ROOD en noemt dat pad.
- Een gitlink MET een corresponderende `path =`-regel in `.gitmodules` wordt doorgelaten, dus
  een echte submodule blijft mogelijk. Zonder die helft zou "weiger elke gitlink" ook slagen,
  en dan bewaakt de guard niets maar verbiedt hij een legitieme constructie.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_GITLINK_MODE = "160000"


def _git(*args: str) -> str:
    """Draai git in de repo en GOOI bij een fout.

    De returncode wordt bewust gecontroleerd. Een guard die hem negeert leest bij een
    onbekende vlag een lege stdout, concludeert "geen overtredingen" en is stil groen -- dat
    is een van de gedocumenteerde faalvormen in quality-gates.md.

    De omgeving wordt geschrobd (OP-245): `*args` is statisch niet te lezen, dus niemand kan
    hier zien of er ooit een schrijvend subcommando doorheen gaat. Onder een van de pre-push
    hook geerfde `GIT_DIR` zou dat de ECHTE repo raken -- `GIT_DIR` wint van `cwd`. Zonder
    deze `env=` meet dit bestand bovendien de index van een andere worktree.
    """
    resultaat = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={
            sleutel: waarde
            for sleutel, waarde in os.environ.items()
            if not sleutel.startswith("GIT_")
        },
    )
    if resultaat.returncode != 0:
        raise AssertionError(
            f"`git {' '.join(args)}` faalde met returncode {resultaat.returncode}: "
            f"{resultaat.stderr.strip()}"
        )
    return resultaat.stdout


def _gitlink_paden() -> set[str]:
    """De paden die in de index als submodule-pointer staan (mode 160000)."""
    paden: set[str] = set()
    for regel in _git("ls-files", "-s").splitlines():
        if not regel.strip():
            continue
        # Vorm: "<mode> <sha> <stage>\t<pad>". Het pad kan spaties bevatten, dus splitsen op
        # de TAB en niet op whitespace -- `Kimi_Agent_Audit filenextjs/...` heeft er een.
        meta, _, pad = regel.partition("\t")
        if meta.split(" ", 1)[0] == _GITLINK_MODE:
            paden.add(pad)
    return paden


def _gedeclareerde_submodulepaden() -> set[str]:
    """De paden uit `.gitmodules`, door git zelf geparseerd."""
    gitmodules = REPO_ROOT / ".gitmodules"
    if not gitmodules.exists():
        return set()
    uitvoer = _git("config", "--file", str(gitmodules), "--get-regexp", r"^submodule\..*\.path$")
    return {regel.split(" ", 1)[1].strip() for regel in uitvoer.splitlines() if " " in regel}


def test_every_gitlink_has_a_gitmodules_entry() -> None:
    """Elke submodule-pointer in de index MOET in `.gitmodules` staan."""
    gitlinks = _gitlink_paden()
    gedeclareerd = _gedeclareerde_submodulepaden()
    zwevend = sorted(gitlinks - gedeclareerd)

    assert not zwevend, (
        "Deze paden staan als submodule-pointer (mode 160000) in de index maar niet in "
        f".gitmodules: {zwevend}. Daardoor faalt `git submodule foreach` -- dat draait in de "
        "post-checkout van actions/checkout, dus ELKE CI-job eindigt met "
        "\"The process '/usr/bin/git' failed with exit code 128\".\n"
        "Is het een echte submodule? Voeg hem toe aan .gitmodules. Is het per ongeluk een "
        "geneste repo die is meegecommit? Verwijder de pointer met "
        "`git rm --cached '<pad>'` (de map op schijf blijft staan)."
    )


def test_the_scan_actually_finds_the_index_modes() -> None:
    """Vangnet tegen een guard die niets meet.

    Als `git ls-files -s` van vorm verandert of leeg terugkomt, vindt de test hierboven nul
    overtredingen en is hij stil groen. Deze test toetst dat de scan wel degelijk modi ziet:
    een repo met broncode heeft altijd gewone blobs (mode 100644).
    """
    modi = {
        regel.partition("\t")[0].split(" ", 1)[0]
        for regel in _git("ls-files", "-s").splitlines()
        if regel.strip()
    }
    assert "100644" in modi, (
        f"`git ls-files -s` leverde geen enkele gewone blob op (gevonden modi: {sorted(modi)}). "
        "De scan meet dan niets en de guard hierboven is vacuum."
    )
