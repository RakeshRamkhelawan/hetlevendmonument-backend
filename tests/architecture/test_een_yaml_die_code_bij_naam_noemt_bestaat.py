"""Een yaml-bestandsnaam die productiecode HARDGECODEERD noemt, moet bestaan.

Achtergrond (BE-AGT-068, 2026-09-25). Bij het opruimen van 151 catalogusvermeldingen
zonder implementatie ging ook ``config/agents/critic_agent.yaml`` mee. Die vermelding
heeft inderdaad geen skillmodule -- maar ``src/core/agents/critic_agent.py:39`` opent hem
RECHTSTREEKS op pad, buiten de catalogusloader om. De analyse vooraf keek naar
skillmodules, ``agents/departments/`` en verwijzingen in ``config/domain_packs.yaml``, en
miste daardoor precies deze vierde manier waarop een configuratie in gebruik kan zijn.

Het faalde bovendien stil: ``_load_critic_agent_yaml`` vangt ``FileNotFoundError``, logt
een waarschuwing en geeft ``{}`` terug, waarna de schemavalidator zonder schema ALLES
goedkeurt. Drie tests vielen om; zonder die tests was een validator die niets meer
valideert onopgemerkt gebleven.

Deze bewaker toetst de algemene vorm: noemt code in ``src/`` een yaml bij naam, dan moet
er een bestand met die naam in de repo staan. Hij vangt daarmee ook een typefout in een
pad en een verwijzing die achterblijft na een hernoeming.

Mutatiebewijs (2026-09-25), in beide richtingen:
  voorwaarts -- ``critic_agent.yaml`` uit de index verwijderd: ROOD.
  voorwaarts -- de naam in ``critic_agent.py`` naar ``critic_agent_x.yaml`` gewijzigd: ROOD.
  tegen      -- een uitzondering uit KNOWN_ONTBREKEND halen terwijl hij nog ontbreekt:
                de staleness-test blijft GROEN en de hoofdtest wordt ROOD, dus de lijst
                kan niet stilzwijgend leeglopen.
  tegen      -- een glob (``*.yaml``) toegevoegd: GROEN -- patronen zijn geen bestandsnamen.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Gedateerd, met een reden per regel. Dit zijn GEEN bestanden in de repo, en dat is juist.
KNOWN_ONTBREKEND: dict[str, str] = {
    "_agent.yaml": (
        "src/core/agents/config/loader.py:93 -- een ACHTERVOEGSEL voor naamsafleiding, "
        "geen bestandsnaam (2026-09-25)"
    ),
    "production_config.yaml": (
        "src/core/config/production_config.py:140 -- wordt in een omgeving aangeleverd, "
        "staat bewust niet in de repo (2026-09-25)"
    ),
    "agent.yaml": (
        "src/core/engine/skill_engine.py:31 -- generieke manifestnaam binnen een "
        "skillmap, geen vast bestand (2026-09-25)"
    ),
}


def _git_omgeving() -> dict[str, str]:
    """De omgeving ZONDER de git-variabelen.

    `git push` zet `GIT_DIR` in de omgeving van zijn hooks wanneer je vanuit een gelinkte
    worktree pusht, de pre-push hook start pytest, en git kiest ALTIJD `GIT_DIR` boven
    `cwd`. Zonder deze schrobbeurt draait een git-aanroep hier tegen een andere repo dan
    bedoeld. Bewaakt door `test_a_test_never_runs_git_against_another_repo.py`; de volledige
    meting staat in `_git_omgeving()` in
    tests/unit/mcp_server/test_de_poort_meet_de_echte_wijzigingen.py.
    """
    return {s: w for s, w in os.environ.items() if not s.startswith("GIT_")}


def _git(*args: str) -> list[str]:
    uit = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        env=_git_omgeving(),
        capture_output=True,
        text=True,
        check=True,
    )
    return uit.stdout.split()


def _is_bestandsnaam(waarde: str) -> bool:
    """Een patroon of extensie is geen bestandsnaam."""
    if "*" in waarde or "{" in waarde or "%" in waarde or waarde.startswith("."):
        return False
    romp = waarde.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return bool(romp)


def _genoemde_yamls() -> list[tuple[str, int, str]]:
    gevonden: list[tuple[str, int, str]] = []
    for pad in _git("ls-files", "src/**/*.py"):
        try:
            boom = ast.parse((REPO_ROOT / pad).read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for knoop in ast.walk(boom):
            if not (isinstance(knoop, ast.Constant) and isinstance(knoop.value, str)):
                continue
            waarde = knoop.value
            if waarde.endswith((".yaml", ".yml")) and _is_bestandsnaam(waarde):
                gevonden.append((pad, knoop.lineno, waarde))
    return gevonden


def _ontbrekend() -> list[tuple[str, int, str]]:
    aanwezig = {p.rsplit("/", 1)[-1] for p in _git("ls-files", "*.yaml", "*.yml")}
    return [
        (pad, regel, waarde)
        for pad, regel, waarde in _genoemde_yamls()
        if waarde.rsplit("/", 1)[-1] not in aanwezig
    ]


@pytest.mark.architecture
def test_elke_yaml_die_code_bij_naam_noemt_bestaat() -> None:
    genoemd = _genoemde_yamls()
    assert len(genoemd) > 100, (
        f"Slechts {len(genoemd)} yaml-namen gevonden in src/. Gemeten 2026-09-25: 146 "
        f"unieke namen over 164 vindplaatsen. Zo weinig betekent dat de scan stuk is."
    )

    onbekend = [
        f"{pad}:{regel} noemt '{waarde}', maar dat bestand staat niet in de repo"
        for pad, regel, waarde in _ontbrekend()
        if waarde.rsplit("/", 1)[-1] not in KNOWN_ONTBREKEND
    ]
    assert not onbekend, (
        "Productiecode noemt een yaml die niet bestaat. Is hij per ongeluk verwijderd of "
        "hernoemd? Zie BE-AGT-068.\n  " + "\n  ".join(sorted(onbekend))
    )


@pytest.mark.architecture
def test_de_uitzonderingslijst_bevat_niets_wat_inmiddels_bestaat() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst, anders rot hij dicht."""
    nog_ontbrekend = {waarde.rsplit("/", 1)[-1] for _, _, waarde in _ontbrekend()}
    verouderd = sorted(naam for naam in KNOWN_ONTBREKEND if naam not in nog_ontbrekend)
    assert not verouderd, (
        "Deze namen staan als uitzondering geregistreerd maar bestaan inmiddels (of worden "
        "niet meer genoemd). Haal ze uit KNOWN_ONTBREKEND:\n  " + "\n  ".join(verouderd)
    )
