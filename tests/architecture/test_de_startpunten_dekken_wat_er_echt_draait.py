"""Elk proces dat we STARTEN moet een startpunt zijn in scripts/codebase_inventory.py.

Waarom dit bestaat (gemeten 2026-09-26). De inventarisatie deelt `src/` in bereikbaar en
onbereikbaar op basis van een lijst startpunten. Die lijst stond op DRIE modules terwijl er
acht processen worden gestart. Gevolg: 34 modules stonden als DOOD geboekt terwijl ze
draaien, waaronder `src/workers/scheduler.py` -- 662 regels, een eigen container in
`docker-compose.yml` en `docker-compose.prod.yml`, en nul tests.

Dat is de gevaarlijkste vorm van een verkeerde meting in dit project: "onbereikbaar" leest
als "mag weg", en de prioriteiten voor het testwerk worden erop gebaseerd. Na de correctie
ging het getal van 859 naar 825.

De bewaker leest de commando's uit de compose-bestanden (via de YAML-structuur, niet als
tekst), uit de `CMD`/`ENTRYPOINT`-regels van de Dockerfiles, en uit de entrypoint-scripts.
Voor alembic is er een aparte route: `alembic -c <pad>/alembic.ini upgrade head` noemt zijn
env-module nergens, maar `script_location` in dat ini-bestand wijst hem aan.
Uit elk commando haalt hij kandidaat-modulenamen, en een kandidaat telt alleen mee als er
ECHT een `.py`-bestand bij hoort -- zo valt `src/alembic.ini` uit een `-c`-vlag vanzelf af
zonder dat daar een uitzondering voor nodig is.

Mutatiebewijs (2026-09-26), in beide richtingen:
  voorwaarts -- `src.workers.scheduler` uit ROOTS gehaald: ROOD (de echte bevinding).
  voorwaarts -- `src.core.learning.worker` uit ROOTS gehaald: ROOD.
  tegen      -- een verzonnen `src.`-woord in een gescande regel: GROEN dankzij de
                bestandstoets, en ROOD zodra die toets wegvalt (mutatie P4).
  tegen      -- een compose-commando zonder `src.`-module toegevoegd: GROEN.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# `src.iets.anders`, eventueel gevolgd door `:attribuut` (de dramatiq-broker-vorm).
_KANDIDAAT = re.compile(r"\bsrc\.[A-Za-z0-9_.]+")

# Startcommando's in deze mappen horen niet bij de draaiende applicatie.
_NEGEER_PADEN = ("archive/", "frontend/", "services/", "tests/")


def _git_omgeving() -> dict[str, str]:
    """De omgeving ZONDER de git-variabelen.

    `git push` zet `GIT_DIR` in de omgeving van zijn hooks bij een push vanuit een gelinkte
    worktree, pytest erft die, en git kiest ALTIJD `GIT_DIR` boven `cwd`. Bewaakt door
    `test_a_test_never_runs_git_against_another_repo.py`.
    """
    import os

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


def _bestaat_als_module(kandidaat: str) -> bool:
    """`src.core.x` telt alleen als `src/core/x.py` of `src/core/x/__init__.py` bestaat.

    De regex hierboven is een TEKSTtreffer; deze toets maakt er een structurele van. Elk
    woord in een commando dat toevallig op `src.` begint -- een configuratiesleutel, een
    omgevingsvariabele, een pad met punten -- valt daarmee af zonder dat daar een
    uitzonderingslijst voor nodig is.

    **Gemeten 2026-09-26: hij filtert vandaag NIETS weg** (5 kandidaten voor, 5 na). Dat is
    geen argument om hem te schrappen, want zonder hem is elke toekomstige tekstruis meteen
    een valse rode uitslag -- maar het staat hier omdat de eerste versie van deze docstring
    een voorbeeld noemde dat niet klopt: `-c /app/src/alembic.ini` levert GEEN kandidaat op,
    want daar staat `src/alembic.ini` met een schuine streep en de regex eist een punt.
    Mutatie P4 toont aan dat hij wel degelijk iets doet: zet er een verzonnen `src.`-woord
    in een gescande regel bij, dan houdt deze toets de bewaker groen en zonder hem slaat hij
    vals alarm.
    """
    stuk = kandidaat.replace(".", "/")
    return (REPO_ROOT / f"{stuk}.py").is_file() or (REPO_ROOT / stuk / "__init__.py").is_file()


def _modules_uit(tekst: str) -> set[str]:
    gevonden: set[str] = set()
    for ruw in _KANDIDAAT.findall(tekst):
        kandidaat = ruw.split(":", 1)[0].rstrip(".")
        if _bestaat_als_module(kandidaat):
            gevonden.add(kandidaat)
    return gevonden


def _uit_compose() -> set[str]:
    """Leest `command` en `entrypoint` uit de YAML-STRUCTUUR, niet uit de ruwe tekst."""
    gevonden: set[str] = set()
    for pad in _git("ls-files", "docker-compose*.yml"):
        try:
            inhoud = yaml.safe_load((REPO_ROOT / pad).read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for dienst in (inhoud.get("services") or {}).values():
            if not isinstance(dienst, dict):
                continue
            for sleutel in ("command", "entrypoint"):
                waarde = dienst.get(sleutel)
                if isinstance(waarde, str):
                    gevonden |= _modules_uit(waarde)
                elif isinstance(waarde, list):
                    gevonden |= _modules_uit(" ".join(str(x) for x in waarde))
    return gevonden


def _uit_dockerfiles_en_scripts() -> set[str]:
    """Hier bestaat geen structuur om op te toetsen; Docker en shell zijn regelgebaseerd."""
    gevonden: set[str] = set()
    for pad in _git("ls-files", "*Dockerfile*", "scripts/entrypoint-*.sh"):
        genormaliseerd = pad.replace("\\", "/")
        if genormaliseerd.startswith(_NEGEER_PADEN):
            continue
        for regel in (REPO_ROOT / pad).read_text(encoding="utf-8", errors="replace").splitlines():
            gestript = regel.strip()
            if gestript.startswith("#"):
                continue
            if genormaliseerd.endswith(".sh") or gestript.startswith(("CMD", "ENTRYPOINT", "RUN")):
                gevonden |= _modules_uit(gestript)
    return gevonden


def _uit_alembic() -> set[str]:
    """`alembic -c <pad>/alembic.ini upgrade head` noemt zijn env-module NERGENS.

    De koppeling staat in het ini-bestand zelf: `script_location` wijst de map aan waarin
    alembic `env.py` zoekt. Dat is af te leiden en hoeft dus geen uitzondering te zijn.
    """
    gevonden: set[str] = set()
    for pad in _git("ls-files", "*alembic.ini"):
        regels = (REPO_ROOT / pad).read_text(encoding="utf-8", errors="replace").splitlines()
        for regel in regels:
            if not regel.strip().startswith("script_location"):
                continue
            waarde = regel.split("=", 1)[1].strip()
            # %(here)s is de map van het ini-bestand zelf.
            map_ = waarde.replace("%(here)s", str(Path(pad).parent).replace("\\", "/"))
            kandidaat = map_.strip("/").replace("/", ".") + ".env"
            if _bestaat_als_module(kandidaat):
                gevonden.add(kandidaat)
    return gevonden


def _uit_infra() -> set[str]:
    """Leest module-referenties uit CI/CD-deploybestanden en infra-configuratie.

    De deploy-workflows kunnen processen starten buiten compose om. Gemeten op 15f11d14:
    .github/workflows/cd-staging.yml start src.workers.workflow_worker:redis_broker (r734),
    src.workers.actors (r735) en src.workers.scheduler (r871); cd-production.yml start
    src.workers.scheduler (r666). Alle vier staan al in ROOTS -- de bewaker dekt nu ook het
    deploypad zodat een vijfde module die daar ooit bijkomt wordt betrapt.

    Mutatiebewijs (2026-09-26, scripts/mutation_harness.py, alle drie UITGEVOERD):
      P1 voorwaarts  -- src.core.shared.config toegevoegd aan cd-staging.yml: ROOD (de scanner
                        detecteert hem, hij staat niet in ROOTS).
      P2 tegenrichting -- src.made.up.nonexistent toegevoegd aan cd-staging.yml: GROEN
                          dankzij _bestaat_als_module() die hem filtert.
      P3 tegenrichting -- _uit_infra() uit _gestart() verwijderd, src.core.shared.config in
                          cd-staging.yml: GROEN (scanner ziet het niet, bewijst blinde vlek
                          zonder deze uitbreiding).
    """
    gevonden: set[str] = set()
    paden_workflows = _git("ls-files", ".github/workflows/")
    assert paden_workflows, (
        "git ls-files .github/workflows/ gaf niets terug -- controleer of REPO_ROOT correct is "
        "en of de CI-workflowbestanden bestaan."
    )
    for pad in paden_workflows:
        if not Path(pad).name.startswith("cd-"):
            continue
        for regel in (REPO_ROOT / pad).read_text(encoding="utf-8", errors="replace").splitlines():
            if regel.strip().startswith("#"):
                continue
            gevonden |= _modules_uit(regel)
    paden_infra = _git("ls-files", "infra/")
    assert paden_infra, (
        "git ls-files infra/ gaf niets terug -- controleer of REPO_ROOT correct is "
        "en of de infra-bestanden bestaan."
    )
    for pad in paden_infra:
        for regel in (REPO_ROOT / pad).read_text(encoding="utf-8", errors="replace").splitlines():
            if regel.strip().startswith("#"):
                continue
            gevonden |= _modules_uit(regel)
    return gevonden


def _gestart() -> set[str]:
    return _uit_compose() | _uit_dockerfiles_en_scripts() | _uit_alembic() | _uit_infra()


def _startpunten() -> tuple[list[str], list[str]]:
    from scripts.codebase_inventory import ROOT_PREFIXES, ROOTS

    return list(ROOTS), list(ROOT_PREFIXES)


@pytest.mark.architecture
def test_elk_gestart_proces_is_een_startpunt_van_de_inventarisatie() -> None:
    gestart = _gestart()
    assert len(gestart) >= 5, (
        f"De scan vond maar {len(gestart)} gestarte modules: {sorted(gestart)}. Gemeten "
        f"2026-09-26: 6 (5 uit compose/Dockerfile plus src.alembic.env uit het ini-bestand). "
        f"Zo weinig betekent dat de compose-bestanden, de Dockerfiles of alembic.ini zijn "
        f"verplaatst en dat deze bewaker niets meer bekijkt."
    )

    roots, prefixes = _startpunten()
    ontbreekt = sorted(
        m for m in gestart if m not in roots and not any(m.startswith(p) for p in prefixes)
    )
    assert not ontbreekt, (
        "Deze modules worden GESTART maar staan niet in ROOTS van "
        "scripts/codebase_inventory.py. Alles wat zij importeren wordt daardoor als DOOD "
        "geboekt -- en dat leest als 'mag weg'.\n  " + "\n  ".join(ontbreekt)
    )


@pytest.mark.architecture
def test_elk_startpunt_bestaat_ook_echt() -> None:
    """Een startpunt dat niet bestaat, breidt de bereikbaarheid met nul uit en valt stil."""
    roots, _ = _startpunten()
    weg = sorted(r for r in roots if not _bestaat_als_module(r))
    assert not weg, (
        "Deze startpunten staan in ROOTS maar er hoort geen module bij:\n  " + "\n  ".join(weg)
    )
