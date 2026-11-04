"""Waakhond rond de testronde: een test die zijn tijdgrens overschrijdt FAALT, hij laat de ronde niet hangen.

Gebruik (alle argumenten zijn die van `python`, dus van pytest):

    python scripts/testronde_waakhond.py -m pytest tests/unit tests/architecture -n 4 --timeout=60 -q

**Waarom dit bestaat (gemeten 2026-10-24 en 2026-10-25, py-spy).** Twee keer hing een pushronde op 97% omdat
een werker in `pytest_timeout.cancel()` wachtte op de timerthread, die in `os._exit(1)` stond: het proces ging
niet dood, xdist zag geen crash en de ronde wachtte eeuwig. Waarom `os._exit` hier niet afsluit is NIET bewezen
(vijf proeven met `thread`-timeouts onder `-n 4` lieten steeds een nette crash zien: een rode ronde met de
naam van de test). Daarom een oorzaak-onafhankelijke bewaker.

**Wat hij doet.** Hij start de ronde, geeft de uitvoer ongewijzigd door en leest per werker (via de plugin
`scripts/testronde_voortgang.py`) welke test loopt, sinds wanneer en hoe lang die mag. Loopt een test langer dan
zijn eigen toegestane duur plus een marge, dan is hij vastgelopen: de waakhond noemt de test, stopt de hele
procesboom en laat de ronde met exitcode 1 eindigen. Een test met een eigen grote `timeout` (tot 1300 s in deze
repo) wordt dus niet afgebroken.

**Wat hij NOOIT doet.** Een uitkomst groener maken: de exitcode van pytest wordt doorgegeven, en na een ingreep is
de exitcode altijd niet nul. Een test overslaan of een grens verruimen.

**Slaapstand.** Zolang de ronde loopt houdt hij de pc wakker (`SetThreadExecutionState`, geen beheerdersrechten) en
trekt hij een sprong van de wandklok af van de duur van een test. Slaapt de pc toch, dan meldt hij dat aan het eind.

Instelbaar via omgevingsvariabelen (standaard tussen haakjes): `TESTRONDE_MARGE` (120 s boven de toegestane
duur), `TESTRONDE_STILSTAND` (1800 s zonder ENIGE uitvoer en zonder voortgang; dekt een ronde die bij het
verzamelen hangt) en `TESTRONDE_POLL` (5 s).
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import psutil

SCRIPTS = Path(__file__).resolve().parent

#: Vlaggen van SetThreadExecutionState (Windows). Geen powercfg en geen beheerdersrechten nodig.
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _getal(naam: str, standaard: float) -> float:
    waarde = os.environ.get(naam)
    return float(waarde) if waarde else standaard


def _zet_uitvoeringsstatus(vlaggen: int) -> int:
    """Dunne schil om SetThreadExecutionState; buiten Windows doet hij niets (geeft 0)."""
    if sys.platform != "win32":
        return 0
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return 0
    return int(windll.kernel32.SetThreadExecutionState(ctypes.c_uint(vlaggen)))


def houd_pc_wakker() -> bool:
    """Voorkom slaapstand zolang de ronde loopt. De status geldt voor DEZE thread: roep aan vanuit main().

    Gemeten 2026-10-25: vier tests van ~3316 s waren geen hang maar een pc die sliep (Windows-gebeurtenislog,
    slaapstand 3325 s). Een uitkomst van 0 betekent dat de aanroep niet gelukt of niet van toepassing is.
    """
    return _zet_uitvoeringsstatus(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) != 0


def laat_pc_los() -> None:
    _zet_uitvoeringsstatus(ES_CONTINUOUS)


def slaapgat(nu: float, vorige_poll: float, poll: float) -> float:
    """De seconden die de wandklok tussen twee polls verder sprong dan kan zonder slaapstand; anders 0.

    De drempel (12 polls + 5 s, standaard 65 s) ligt bewust ver boven een poll die onder zware belasting
    een halve minuut te laat komt: zo'n vertraging is geen slaapstand en mag een hang niet uitstellen.
    """
    verstreken = nu - vorige_poll
    return verstreken - poll if verstreken > 12 * poll + 5 else 0.0


def corrigeer_voor_slaapstand(
    voortgang: list[dict[str, object]],
    afgetrokken: dict[tuple[str, float], float],
    gat: float,
    begonnen_voor: float,
) -> None:
    """Schuif de starttijd op van tests die al liepen toen de pc sliep; tests die erna begonnen blijven staan.

    Een slaap vroeg in de ronde mag een test die er LATER echt hangt niet 3300 s langer onzichtbaar maken.
    """
    for regel in voortgang:
        sinds = float(str(regel["since"]))
        sleutel = (str(regel["nodeid"]), sinds)
        if gat > 0 and sinds <= begonnen_voor:
            afgetrokken[sleutel] = afgetrokken.get(sleutel, 0.0) + gat
        regel["since"] = sinds + afgetrokken.get(sleutel, 0.0)


def lees_voortgang(map_: Path) -> list[dict[str, object]]:
    """De lopende tests per werker; een onleesbaar of leeg bestand telt als 'niets lopend'."""
    gevonden: list[dict[str, object]] = []
    for bestand in sorted(map_.glob("*.json")):
        try:
            inhoud = json.loads(bestand.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(inhoud, dict) and inhoud.get("nodeid"):
            pid = inhoud.get("pid")
            # Een werker die is gecrasht laat zijn bestand achter en xdist start de vervanger onder een nieuwe
            # naam; zo'n bestand is geen lopende test meer en mag geen vals alarm geven.
            if isinstance(pid, int) and not psutil.pid_exists(pid):
                continue
            gevonden.append({**inhoud, "werker": bestand.stem})
    return gevonden


def vastgelopen(voortgang: list[dict[str, object]], nu: float, marge: float) -> list[str]:
    """De tests die langer lopen dan hun toegestane duur plus marge. Zonder bekende duur geen oordeel."""
    namen: list[str] = []
    for regel in voortgang:
        toegestaan = float(str(regel.get("toegestaan") or 0))
        if toegestaan <= 0:
            continue
        duur = nu - float(str(regel["since"]))
        if duur > toegestaan + marge:
            namen.append(
                f"{regel['nodeid']} ({regel['werker']}, {duur:.0f} s bezig, toegestaan {toegestaan:.0f} s)"
            )
    return namen


def stop_procesboom(proces: subprocess.Popen[str]) -> None:
    """Dood het proces en alles eronder; een hangende werker reageert niet op beleefd vragen.

    Eerst de ouder (de xdist-controller), zodat er geen vervangende werker meer wordt gestart; daarna de
    momentopname van de kinderen, die na het sterven van de ouder als wees blijven staan.
    """
    try:
        ouder = psutil.Process(proces.pid)
        kinderen = ouder.children(recursive=True)
    except psutil.Error:
        return
    for slachtoffer in [ouder, *kinderen]:
        try:
            slachtoffer.kill()
        except psutil.Error:
            pass
    psutil.wait_procs([ouder, *kinderen], timeout=30)


def main(argumenten: list[str]) -> int:
    marge = _getal("TESTRONDE_MARGE", 120.0)
    stilstand = _getal("TESTRONDE_STILSTAND", 1800.0)
    poll = _getal("TESTRONDE_POLL", 5.0)

    map_ = Path(tempfile.mkdtemp(prefix="testronde-voortgang-"))
    omgeving = dict(os.environ)
    omgeving["TESTRONDE_VOORTGANG"] = str(map_)
    bestaande = omgeving.get("PYTEST_PLUGINS", "")
    omgeving["PYTEST_PLUGINS"] = (
        f"{bestaande},testronde_voortgang" if bestaande else "testronde_voortgang"
    )
    omgeving["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(SCRIPTS), omgeving.get("PYTHONPATH", "")) if p
    )

    proces = subprocess.Popen(
        [sys.executable, *argumenten],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=omgeving,
    )
    laatste_uitvoer = [time.time()]
    wakker = False

    def doorgeven() -> None:
        assert proces.stdout is not None
        # Binair doorgeven: een byte die geen UTF-8 is mag deze thread nooit laten sterven, want dan leest
        # niemand de pijp meer, loopt hij vol en blijft de ronde hangen.
        for regel in iter(proces.stdout.readline, b""):
            laatste_uitvoer[0] = time.time()
            try:
                sys.stdout.buffer.write(regel)
                sys.stdout.buffer.flush()
            except (OSError, ValueError):
                pass

    lezer = threading.Thread(target=doorgeven, daemon=True)
    lezer.start()

    ingreep = False
    vorige_poll = time.time()
    slaapstand = 0.0
    afgetrokken: dict[tuple[str, float], float] = {}
    try:
        wakker = houd_pc_wakker()
        while proces.poll() is None:
            time.sleep(poll)
            nu = time.time()
            # De wandklok sprong (slaapstand van de pc): dat telt niet als rekentijd van een test.
            gat = slaapgat(nu, vorige_poll, poll)
            slaapstand += gat
            voortgang = lees_voortgang(map_)
            corrigeer_voor_slaapstand(voortgang, afgetrokken, gat, vorige_poll + poll)
            if gat > 0:
                laatste_uitvoer[0] = min(nu, laatste_uitvoer[0] + gat)
            vorige_poll = nu
            namen = vastgelopen(voortgang, nu, marge)
            stil = nu - laatste_uitvoer[0]
            if namen or (stil > stilstand and not voortgang):
                regels = namen or [f"geen enkele uitvoer of voortgang gedurende {stil:.0f} s"]
                print(
                    "\n[waakhond] TESTRONDE VASTGELOPEN -- de ronde wordt gestopt en eindigt ROOD:",
                    flush=True,
                )
                for regel in regels:
                    print(f"[waakhond]   {regel}", flush=True)
                stop_procesboom(proces)
                ingreep = True
                break
    finally:
        laat_pc_los()
        lezer.join(timeout=10)
        shutil.rmtree(map_, ignore_errors=True)

    if slaapstand > 0:
        print(
            f"[waakhond] LET OP: de pc sliep ongeveer {slaapstand:.0f} s tijdens deze ronde"
            + (" (ondanks keep-awake)" if wakker else " (keep-awake niet gelukt)")
            + "; duren in dit log zijn daardoor te lang.",
            flush=True,
        )

    if ingreep:
        return 1  # nooit groen na een ingreep
    return proces.returncode if proces.returncode is not None else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
