"""Een machinebreed slot op de volledige poort -- er draait er nooit meer dan een.

WAAROM DIT BESTAAT
------------------
Sinds commit `f57b82cb` (2026-09-10) draait de pre-push hook de VOLLEDIGE poort bij elke
push naar `develop`. Daarvoor deed die hook alleen `ci-local-fast.sh` (ruff/bandit,
seconden). Dat is de wijziging waarna deze machine begon om te vallen, en dat is geen
indruk maar een meting.

Wat een enkele poortrun kost, gemeten 2026-09-17 op deze machine (31,7 GB RAM, 20
logische kernen), met verder niets anders actief:

    pytest -n 4  ->  1 hoofdproces + 4 werkers
    piek python  ->  5078 MB
    vrij RAM     ->  zakt van 7300 MB naar 2794 MB
    duur         ->  10 a 11 minuten alleen op de machine

Daar past er GEEN tweede naast. Twee gelijktijdige runs vragen ruim 10 GB terwijl er
ongeveer 7 GB vrij is. Wat er dan gebeurt is precies gedocumenteerd in ADR-036 OP-19 en
op 2026-09-17 opnieuw gemeten door sessie `sanskritisetu-org-39`:

    [gw2] node down: Not properly terminated
    worker 'gw2' crashed while running 'tests/unit/test_memory_services.py::...'
    2 failed, 16612 passed ... in 1476.11s (0:24:36)

Een werker sterft door geheugengebrek, en pytest meldt de test die die werker toevallig
uitvoerde als FAILED. Elke run wijst andere tests aan en los slagen ze allemaal. Dat
leest als flakiness en is het niet. De run duurde bovendien 24m36 tegenover 16m41 voor
DEZELFDE commit -- de machine had het aantoonbaar zwaarder.

De schade is groter dan de verloren tijd: wie zo'n rode run voor een echte failure
aanziet, gaat een bug zoeken die er niet is. Dat is deze week meermaals gebeurd.

WAT DIT SLOT WEL EN NIET DOET
-----------------------------
WEL: het serialiseert de volledige poort over ALLE worktrees en sessies op deze machine.
Wie het slot niet krijgt, wacht -- met een melding wie het vasthoudt en sinds wanneer.

NIET: het beperkt niets anders. Een `pytest` die je met de hand draait, een `act`-run,
een Docker-build -- die zijn allemaal nog steeds vrij. Dit slot dekt het ENE geval dat
aantoonbaar de machine omtrok: de poort die bij elke push naar `develop` automatisch
start en elf tot vijfentwintig minuten vier werkers vol houdt.

Het slot leeft in de GEDEELDE `.git`-map, net als `scripts/claim_op.py` en
`scripts/push_gate.py`, zodat elke worktree hetzelfde slot ziet zonder commit.

EERLIJKE GRENS
--------------
Dit is een afspraak met technische rugdekking, geen slot in de kernel. Wie `pytest`
rechtstreeks start omzeilt het, en `git push --no-verify` ook. Het dekt het
geautomatiseerde pad, en dat is waar het misging.

GEBRUIK
-------
    python scripts/testpoort_slot.py pak --sessie <naam> --reden "push naar develop"
    python scripts/testpoort_slot.py geef --sessie <naam>
    python scripts/testpoort_slot.py status
    python scripts/testpoort_slot.py pak --sessie <naam> --wacht 0     # niet wachten, direct falen
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
import os
import subprocess  # nosec B404: alleen vaste git-argumenten, geen invoer van buiten
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

#: Hoe lang een slot maximaal geldig is zonder dat het wordt teruggegeven.
#: Een poortrun duurt gemeten 11 tot 25 minuten; 45 minuten laat ruime marge en zorgt
#: dat een afgebroken sessie de machine niet eindeloos blokkeert.
_MAX_LEEFTIJD_S = 45 * 60

#: Hoe lang `pak` standaard wacht op een bezet slot. Ruim boven de langste gemeten run
#: (24m36) plus de marge hierboven, zodat wachten normaal gesproken loont.
_STANDAARD_WACHT_S = 75 * 60

#: Hoe vaak we kijken of het slot vrij is. Tien seconden is fijn genoeg om niet te
#: treuzelen en grof genoeg om geen merkbare belasting te zijn.
_POLL_S = 10


def _git_gedeelde_map() -> Path:
    """De GEDEELDE `.git`-map, ook vanuit een gelinkte worktree.

    `--git-common-dir` en niet `--git-dir`: vanuit een worktree wijst de tweede naar
    `.git/worktrees/<naam>` en dan heeft elke worktree zijn eigen slot -- precies het
    tegenovergestelde van wat dit bestand moet doen.

    De omgeving wordt geschoond van `GIT_*`. Reden, gemeten 2026-09-16: `git push` zet
    vanuit een gelinkte worktree `GIT_DIR` in de omgeving van zijn hooks, en `GIT_DIR`
    wint van `cwd`. Dit script draait juist IN die hook.
    """
    omgeving = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    uit = subprocess.run(  # nosec B603 B607: vaste argumenten
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
        env=omgeving,
    )
    pad = Path(uit.stdout.strip())
    return pad if pad.is_absolute() else (Path.cwd() / pad).resolve()


def _slotpad() -> Path:
    return _git_gedeelde_map() / "sanskritisetu-poort-slot.json"


def _lees(pad: Path) -> dict | None:
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _leeftijd_s(gegevens: dict) -> float:
    try:
        sinds = datetime.fromisoformat(gegevens["sinds"])
    except (KeyError, ValueError):
        return _MAX_LEEFTIJD_S + 1
    return (datetime.now(timezone.utc) - sinds).total_seconds()


def _beschrijf(gegevens: dict) -> str:
    leeftijd = int(_leeftijd_s(gegevens) // 60)
    return (
        f"{gegevens.get('sessie', '(onbekend)')} "
        f"in {gegevens.get('werkmap', '(onbekende map)')} "
        f"sinds {gegevens.get('sinds', '?')} ({leeftijd} min) "
        f"-- {gegevens.get('reden', '')}"
    )


def _houder_is_aantoonbaar_dood(gegevens: Mapping[str, object]) -> bool:
    """True ALLEEN bij positief doodsbewijs. Twijfel betekent: laat het slot staan.

    Deze toets maakt het slot ZWAKKER, niet sterker -- hij voegt een reden toe om eerder
    over te nemen. Daarom staat de fail-safe hier andersom dan je zou verwachten: alles
    wat geen expliciet "dit proces bestaat niet" is, levert False op. Een ontbrekend of
    onleesbaar veld, een oud slotbestand, of een fout in psutil laten de leeftijdsgrens
    het werk doen zoals voorheen. Pid-hergebruik geeft dan een vals "leeft"; dat kost
    hooguit wachttijd, terwijl de andere fout twee poortruns naast elkaar oplevert.

    **Niet `os.kill(pid, 0)`, en dat is gemeten.** Op dit platform (Windows, 2026-09-19)
    geeft die voor een LEVEND proces en voor een NET GESTORVEN proces hetzelfde antwoord
    (geen exceptie); pas bij een pid van langer geleden komt er een OSError. Hij
    onderscheidt dus niet in precies het venster waarin een slot overgenomen moet worden.
    `psutil.pid_exists()` klopte in alle vijf de gemeten gevallen.

    **Let op welke pid hier hoort.** NIET het `pid`-veld: dat is `os.getpid()` van het
    kortlevende `pak`-proces, dat al weg is zodra het slot genomen is -- daarop toetsen
    zou elk slot onmiddellijk overneembaar maken. Alleen `houder_pid`, meegegeven door wie
    het slot werkelijk vasthoudt.
    """
    ruw = gegevens.get("houder_pid")
    if isinstance(ruw, bool) or not isinstance(ruw, (int, str)):
        return False
    try:
        pid = int(ruw)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        import psutil
    except ImportError:
        return False
    try:
        return not psutil.pid_exists(pid)
    except Exception:  # noqa: BLE001 -- twijfel is geen doodsbewijs
        return False


def _houder_is_aantoonbaar_levend(gegevens: Mapping[str, object]) -> bool:
    """True ALLEEN bij positief levendheidsbewijs. Twijfel betekent: leeftijdsgrens geldt.

    Het spiegelbeeld van `_houder_is_aantoonbaar_dood`, maar met omgekeerde semantiek:
    hier is de fail-safe FALSE -- onzekerheid (geen pid, geen psutil, exception) laat de
    leeftijdsgrens het werk doen zoals voorheen. Alleen een expliciet True van
    `psutil.pid_exists` levert True op.

    Gebruik: wanneer levendheid aantoonbaar is, mag leeftijd nooit grond zijn voor
    overname (OP-263). Wanneer het onbekend is, valt de code terug op de leeftijdsgrens.
    """
    ruw = gegevens.get("houder_pid")
    if isinstance(ruw, bool) or not isinstance(ruw, (int, str)):
        return False
    try:
        pid = int(ruw)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        import psutil
    except ImportError:
        return False
    try:
        return bool(psutil.pid_exists(pid))
    except Exception:  # noqa: BLE001 -- twijfel is geen levendheidsbewijs
        return False


def _probeer_te_pakken(
    pad: Path, sessie: str, reden: str, houder_pid: int | None = None
) -> bool:
    """Maakt het slotbestand ATOMISCH aan. False als een ander het al heeft.

    `O_CREAT | O_EXCL` en geen "bestaat het al?"-vraag vooraf: tussen die vraag en het
    schrijven past een andere sessie, en dan hebben er twee het slot.
    """
    inhoud = json.dumps(
        {
            "sessie": sessie,
            "werkmap": str(Path.cwd()),
            # `pid` is de pid van DIT kortlevende pak-proces. Hij is bewaard gebleven
            # voor de leesbaarheid van het bestand, maar is GEEN levendheidsbewijs: dit
            # proces keert hierna meteen terug. Zie `_houder_is_aantoonbaar_dood`.
            "pid": os.getpid(),
            # De pid van wie het slot WERKELIJK vasthoudt, als die zich meldt. De pre-push
            # hook geeft zijn eigen shell mee; handmatig gebruik heeft geen houder en laat
            # dit veld weg.
            "houder_pid": houder_pid,
            "sinds": datetime.now(timezone.utc).isoformat(),
            "reden": reden,
        },
        indent=2,
    )
    try:
        fd = os.open(pad, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as bestand:
        bestand.write(inhoud)
    return True


def cmd_pak(args: argparse.Namespace) -> int:
    pad = _slotpad()
    wacht_tot = time.monotonic() + args.wacht
    gemeld = False

    while True:
        if _probeer_te_pakken(pad, args.sessie, args.reden, getattr(args, "houder_pid", None)):
            print(f"[testpoort-slot] genomen door {args.sessie}")
            return 0

        gegevens = _lees(pad)
        if gegevens is None:
            # Onleesbaar of half geschreven. Behandel als verouderd na de maximale
            # leeftijd; tot die tijd gewoon wachten.
            gegevens = {"sessie": "(onleesbaar slotbestand)", "sinds": ""}

        dood = _houder_is_aantoonbaar_dood(gegevens)
        leeft = _houder_is_aantoonbaar_levend(gegevens)
        if dood or (not leeft and _leeftijd_s(gegevens) > _MAX_LEEFTIJD_S):
            reden_overname = (
                "houder bestaat niet meer" if dood else "ouder dan de leeftijdsgrens"
            )
            print(
                f"[testpoort-slot] slot overgenomen ({reden_overname}) -- "
                f"hield {_beschrijf(gegevens)}",
                file=sys.stderr,
            )
            try:
                pad.unlink()
            except OSError:
                pass
            continue

        if not gemeld:
            print(f"[testpoort-slot] BEZET door {_beschrijf(gegevens)}")
            print(
                "[testpoort-slot] Wachten tot hij vrij is. Twee volledige poortruns tegelijk "
                "putten het geheugen van deze machine uit; dan sterven er xdist-werkers en "
                "meldt pytest willekeurige tests als FAILED (ADR-036 OP-19)."
            )
            gemeld = True

        if time.monotonic() >= wacht_tot:
            print(
                f"[testpoort-slot] Na {args.wacht}s nog steeds bezet -- opgegeven.",
                file=sys.stderr,
            )
            return 1
        time.sleep(_POLL_S)


def cmd_geef(args: argparse.Namespace) -> int:
    pad = _slotpad()
    gegevens = _lees(pad)
    if gegevens is None:
        print("[testpoort-slot] er was geen slot om terug te geven")
        return 0
    if not args.forceer and gegevens.get("sessie") != args.sessie:
        print(
            f"[testpoort-slot] slot is van {gegevens.get('sessie')}, niet van {args.sessie} -- "
            "niets gedaan. Gebruik --forceer als je zeker weet dat het verweesd is.",
            file=sys.stderr,
        )
        return 1
    try:
        pad.unlink()
    except OSError as fout:
        print(f"[testpoort-slot] kon het slot niet verwijderen: {fout}", file=sys.stderr)
        return 1
    print(f"[testpoort-slot] teruggegeven door {args.sessie}")
    return 0


def houder() -> dict | None:
    """Wie houdt de testronde nu vast, of None als hij vrij is.

    **Publiek, en met een reden.** Tot 2026-09-25 bemiddelde dit slot alleen tussen
    POORTRUNS onderling -- zie de moduledocstring: "er draait er nooit meer dan een". Het
    wist niets van een sessie die er zware metingen naast zette, en kon dat ook niet weten,
    want niemand anders raadpleegde het.

    Dat is duur gebleken. CLAUDE.md verbiedt al sinds 2026-09-20 een reviewagent of een
    mutatietest naast de testronde, met de meting erbij (exit 124). Op 2026-09-25 liep een
    sessie er alsnog in -- een sessie die die regel die dag nog aan iemand anders had
    uitgelegd. Gevolg: twee workercrashes (`node down`) en 28m17 in plaats van 17m12, en dus
    een NIET-meting. Dat is geen kennisprobleem, en nog een regel erbij schrijven lost het
    niet op; een terugkerende fout is in dit project ONTBREKEND GEREEDSCHAP.

    Een verouderd slot (ouder dan de overnamegrens) geldt hier als VRIJ, net als bij het
    pakken zelf. Anders zou een gecrashte poortrun al het andere werk stilleggen -- precies
    de faalvorm die de MCP-orchestrator deze week liet zien.
    """
    gegevens = _lees(_slotpad())
    if gegevens is None or _leeftijd_s(gegevens) > _MAX_LEEFTIJD_S:
        return None
    return gegevens


def beschrijf_houder(gegevens: dict) -> str:
    """De houder in een regel, voor een foutmelding elders."""
    return _beschrijf(gegevens)


def cmd_status(_args: argparse.Namespace) -> int:
    pad = _slotpad()
    gegevens = _lees(pad)
    if gegevens is None:
        print("[testpoort-slot] vrij")
        return 0
    verouderd = (
        " [VEROUDERD -- mag overgenomen worden]" if _leeftijd_s(gegevens) > _MAX_LEEFTIJD_S else ""
    )
    print(f"[testpoort-slot] bezet: {_beschrijf(gegevens)}{verouderd}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pak = sub.add_parser("pak", help="Neem het slot, wacht zo nodig")
    p_pak.add_argument("--sessie", required=True)
    p_pak.add_argument("--reden", default="")
    p_pak.add_argument("--wacht", type=int, default=_STANDAARD_WACHT_S)
    p_pak.add_argument(
        "--houder-pid",
        dest="houder_pid",
        type=int,
        default=None,
        help=(
            "Windows-pid van het proces dat het slot VASTHOUDT, zodat een volgende sessie "
            "kan zien of die houder nog leeft. Laat weg bij handmatig gebruik: dan is er "
            "geen houder en geldt alleen de leeftijdsgrens. Geef NIET de bash-$$ mee -- "
            "dat is een MSYS-pid en geen Windows-pid; gebruik kolom 4 van `ps -p $$`."
        ),
    )
    p_pak.set_defaults(func=cmd_pak)

    p_geef = sub.add_parser("geef", help="Geef het slot terug")
    p_geef.add_argument("--sessie", required=True)
    p_geef.add_argument("--forceer", action="store_true")
    p_geef.set_defaults(func=cmd_geef)

    p_status = sub.add_parser("status", help="Wie heeft het slot?")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
