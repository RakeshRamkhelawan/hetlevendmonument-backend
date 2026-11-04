"""Een herstel dat de levende database overschrijft wordt nooit AUTOMATISCH bevestigd (meetlat eis 6).

Brief `docs/agent-briefs/generated/2026-10-14-sprint-dag-harde-poort-eis-3-en-6-overnemen.md`:
`scripts/restore_db.sh` OVERSCHRIJFT de levende database en vraagt daarom om de NAAM van de
database, getypt door een mens (`--bevestig <naam>` of een prompt). Tot 2026-10-14 stuurden twee
deploy-scripts die bevestiging zelf mee: eerst een `y` via stdin, daarna (in een tussenversie) de
databasenaam als `--bevestig`. In beide gevallen is de bevestiging geen bevestiging meer.

Wat deze guard bewaakt:

1. Geen enkele regel die `restore_db.sh` aanroept bevat een automatische bevestiging (`--bevestig`,
   een here-string, `echo y |`, `yes |`, `printf y |`). Uitzondering: `scripts/herstelproef.sh`, dat
   alleen tegen zijn EIGEN wegwerpcontainer werkt (zie `UITZONDERINGEN`; met een staleness-test).
2. De twee deploy-scripts laten een mislukt herstel niet als gelukt tellen: de aanroep staat in
   een `pipefail`-omgeving (de afloopstatus van `tee` verbergt anders de fout).

De verzameling is benoemd: `SCRIPTBESTANDEN` is alles wat git kent met een extensie of naam in
`SCANBARE_SOORTEN`. Commentaarregels tellen niet mee (daar staat de uitleg).

Mutatiebewijs (2026-10-14): staat in het verslag bij de oplevering; per test de mutatie die hem
rood maakt en een legitiem geval dat groen blijft.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

SCANBARE_SOORTEN = (".sh", ".bash", ".yml", ".yaml", ".ps1", ".py", ".mk")
SCANBARE_NAMEN = ("Makefile",)

#: De deploy-scripts uit de brief; hier gelden ook de pipefail-eis en de eis dat ze `restore_db.sh`
#: nog echt aanroepen (anders bewaakt de guard niets).
DEPLOY_SCRIPTS = ("scripts/deploy_production.sh", "scripts/deploy_rollback.sh")

#: Bestanden die `restore_db.sh` met een bevestiging mogen aanroepen, met de reden.
UITZONDERINGEN: dict[str, str] = {
    "scripts/herstelproef.sh": (
        "2026-10-14 -- start zijn EIGEN wegwerpcontainer (`ss_herstelproef_<pid>`, tmpfs) en zet "
        "POSTGRES_CONTAINER daarop; het overschrijft dus nooit een echte database. Het script "
        "controleert die naam zelf voor het iets overschrijft."
    ),
}

#: Wat een bevestiging automatisch maakt, op de regel waar `restore_db.sh` wordt aangeroepen.
AUTOMATISCH = re.compile(
    r"--bevestig"  # een databasenaam of "y" op de opdrachtregel
    r"|<<"  # here-string (<<<) of heredoc (<<EOF)
    r"|\b(?:echo|printf|cat)\b[^|;&]*\|"  # echo y | ..., cat antwoorden | ...
    r"|\byes\b[^|;&]*\|"  # yes | ...
)


#: Dit bestand bevat de verboden vormen noodzakelijk als teststrings en staat daarom buiten de scan:
#: een bewuste blinde vlek van exact een bestand.
SELF = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()


def _tracked() -> list[str]:
    uit = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [
        p
        for p in uit
        if p != SELF and (p.endswith(SCANBARE_SOORTEN) or Path(p).name in SCANBARE_NAMEN)
    ]


SCRIPTBESTANDEN = _tracked()


def _commando_regels(pad: str) -> list[str]:
    """De regels van een bestand zonder commentaar, met regelvoortzettingen (`\\`) samengevoegd."""
    tekst = (REPO_ROOT / pad).read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    regels: list[str] = []
    huidig = ""
    for ruw in tekst.split("\n"):
        if ruw.lstrip().startswith("#"):
            continue
        if ruw.rstrip().endswith("\\"):
            huidig += ruw.rstrip()[:-1] + " "
            continue
        regels.append(huidig + ruw)
        huidig = ""
    if huidig:
        regels.append(huidig)
    return regels


def _aanroepen_van_restore(pad: str) -> list[str]:
    return [r.strip() for r in _commando_regels(pad) if "restore_db.sh" in r]


def test_the_scan_sees_the_files_it_should() -> None:
    """Controlegroep: de benoemde scripts zitten in de verzameling en bevatten een aanroep."""
    ontbreekt = [p for p in DEPLOY_SCRIPTS if p not in SCRIPTBESTANDEN]
    zonder_aanroep = [p for p in DEPLOY_SCRIPTS if not _aanroepen_van_restore(p)]

    assert ontbreekt == [] and zonder_aanroep == []


@pytest.mark.parametrize("pad", [p for p in SCRIPTBESTANDEN if p not in UITZONDERINGEN])
def test_no_script_confirms_a_restore_automatically(pad: str) -> None:
    gevonden = [r for r in _aanroepen_van_restore(pad) if AUTOMATISCH.search(r)]

    assert gevonden == [], (
        f"{pad} bevestigt een herstel automatisch:\n  "
        + "\n  ".join(gevonden)
        + "\nrestore_db.sh overschrijft de levende database; een mens typt de databasenaam."
    )


@pytest.mark.parametrize("pad", DEPLOY_SCRIPTS)
def test_the_deploy_script_does_not_hide_a_failed_restore(pad: str) -> None:
    regels = [r for r in _aanroepen_van_restore(pad) if "| tee" in r]

    assert regels, f"{pad} roept restore_db.sh niet via tee aan; pas de guard aan"
    assert all("pipefail" in r for r in regels), (
        f"{pad}: een herstel via `| tee` zonder pipefail meldt succes als het herstel faalt:\n  "
        + "\n  ".join(regels)
    )


#: Een eigen herstelpad naast `restore_db.sh`: een dump rechtstreeks in psql pijpen overschrijft de
#: database zonder voor-back-up en zonder dat een mens de naam typt.
RAUW_HERSTEL = re.compile(r"\b(?:gunzip|zcat|gzip\s+-dc?|gzip\s+-d\s+-c)\b[^;&]*\|[^;&]*\bpsql\b")


@pytest.mark.parametrize("pad", DEPLOY_SCRIPTS)
def test_the_deploy_script_has_no_restore_path_around_restore_db(pad: str) -> None:
    gevonden = [r.strip() for r in _commando_regels(pad) if RAUW_HERSTEL.search(r)]

    assert gevonden == [], (
        f"{pad} herstelt de database buiten restore_db.sh om:\n  " + "\n  ".join(gevonden)
    )


def test_the_raw_restore_pattern_catches_the_old_fallback_and_spares_a_plain_pipe() -> None:
    """Beide richtingen; de eerste regel is letterlijk de oude terugvaltak van deploy_rollback.sh."""
    fout = [
        'if gunzip -c "$F" | docker exec -i "$C" psql -U postgres sanskritisetu 2>&1 | tee -a "$L"; then',
        'zcat "$F" | docker exec -i "$C" psql -U postgres x',
    ]
    goed = [
        'gunzip -c "$F" | head -n 5',
        'docker exec "$C" psql -U postgres -c "select 1" | tee -a "$L"',
    ]

    assert [r for r in fout if not RAUW_HERSTEL.search(r)] == []
    assert [r for r in goed if RAUW_HERSTEL.search(r)] == []


def test_the_exceptions_are_not_stale() -> None:
    """Een uitzondering die geen `restore_db.sh` meer aanroept moet uit de lijst."""
    verouderd = [p for p in UITZONDERINGEN if not _aanroepen_van_restore(p)]

    assert verouderd == [], f"deze uitzonderingen roepen restore_db.sh niet meer aan: {verouderd}"


def test_the_pattern_catches_every_known_form_and_spares_a_plain_call() -> None:
    """Beide richtingen op het patroon zelf, met de vormen die echt hebben bestaan."""
    fout = [
        'bash scripts/restore_db.sh "$F" <<< "y"',
        'echo "y" | bash scripts/restore_db.sh "$F"',
        'bash scripts/restore_db.sh "$F" --bevestig "${POSTGRES_DB:-sanskritisetu}"',
        'yes | bash scripts/restore_db.sh "$F"',
        'printf y | bash scripts/restore_db.sh "$F"',
        'cat antwoorden.txt | bash scripts/restore_db.sh "$F"',
        'bash scripts/restore_db.sh "$F" <<EOF',
    ]
    goed = [
        'bash scripts/restore_db.sh "$F"',
        '(set -o pipefail; bash scripts/restore_db.sh "$F" 2>&1 | tee -a "$LOG")',
        'bash scripts/restore_db.sh "$F" --naar-database proef_nieuw',
    ]

    assert [r for r in fout if not AUTOMATISCH.search(r)] == []
    assert [r for r in goed if AUTOMATISCH.search(r)] == []
