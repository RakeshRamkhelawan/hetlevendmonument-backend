"""Het poortslot neemt alleen over bij POSITIEF doodsbewijs (SP-WF-001 dag 2, 2026-09-19).

WAAROM DEZE TESTS BESTAAN
-------------------------
`testpoort_slot.py` schreef sinds zijn ontstaan `"pid": os.getpid()` weg en las dat getal
NERGENS terug -- gemeten met `grep -nE "pid|alive|levend|verlopen|stale"`: regel 148 was de
enige treffer. Het slot kon dus niet zien of zijn houder nog bestond en viel terug op de
leeftijdsgrens van 45 minuten. Op 2026-09-19 stond het slot daardoor dicht op een pre-push
hook die allang was teruggekeerd; de volgende sessie had op een dode houder staan wachten.

DE PID DIE ER AL STOND IS ONBRUIKBAAR, EN DAT IS GEEN DETAIL
------------------------------------------------------------
`os.getpid()` in `_probeer_te_pakken` is de pid van het KORTLEVENDE python-proces dat `pak`
draait; `cmd_pak` keert daarna meteen terug. Dat proces is dus al weg op het moment dat het
slot genomen is. Een levendheidstoets op DAT getal zou elk slot onmiddellijk overneembaar
maken -- geen zwakkere bewaker, maar GEEN bewaker. Daarom komt de pid van de houder er als
apart veld `houder_pid` bij, meegegeven door wie het slot echt vasthoudt (de pre-push hook
heeft een shell die blijft leven; handmatig gebruik heeft geen houder en geeft niets mee).

WAAROM `psutil` EN NIET `os.kill(pid, 0)`
-----------------------------------------
Gemeten op dit platform (Windows, 2026-09-19), vijf gevallen naast elkaar:

    dit python-proces (LEEFT)            os.kill: geen exceptie         psutil: True
    subproces net geeindigd              os.kill: geen exceptie         psutil: False
    idem, Popen-handle losgelaten        os.kill: geen exceptie         psutil: False
    pid van een uur eerder               os.kill: OSError winerror=87   psutil: False
    pid die nooit bestond (999999)       os.kill: OSError winerror=87   psutil: False

Het beslissende geval is regel 2: een DOOD proces meldt zich via `os.kill` als levend. Een
slot van een gestorven houder zou dan nooit worden overgenomen -- veilig, maar precies de
winst die deze wijziging moet opleveren valt weg.

**En de sterkste reden om `os.kill` hier niet te gebruiken is dat DRIE sessies er DRIE
verschillende uitkomsten mee maten**, op dezelfde machine, op dezelfde dag:
- deze sessie, eerste meting : dood proces -> OSError 87
- regie                      : levend NIET-kind -> OSError 87, levend kind -> geen fout
- deze sessie, hermeting     : levend niet-kind (de ouder) -> geen fout; dood kind -> geen fout

De uitkomst hangt af van wie een handle op het proces vasthoudt en van de
ouder/kind-verhouding, en dus van dingen die met levendheid niets te maken hebben. In ALLE
metingen van alle drie de sessies was `psutil.pid_exists()` wel juist. Een instrument dat
per meetopstelling een ander antwoord geeft, is hier het verkeerde instrument -- ongeacht
welke tabel klopt. psutil==5.9.5 staat gepind in `requirements-base.txt` en draait al in
productiecode, dus dit is geen nieuwe afhankelijkheid.

**Wat dat voor dit harnas betekent, en het is een valkuil die de regie terecht benoemde.**
Wie een "levend geval" bouwt met een KINDPROCES -- de voor de hand liggende manier -- meet
een andere tak dan die van het slot: de houder is altijd een andere sessie of een hook, nooit
een kind van wie de toets doet. Daarom staat hieronder ook een geval met een levend proces
dat GEEN kind is. En `test_..._DOOD_proces_wordt_wel_overgenomen` is degene die een
terugval naar `os.kill` zou betrappen: die zou een dood proces als levend lezen en het slot
laten staan.

FAIL-SAFE STAAT DE ANDERE KANT OP DAN JE ZOU DENKEN
---------------------------------------------------
Deze toets maakt het slot ZWAKKER, niet sterker: hij voegt een reden toe om eerder over te
nemen. Daarom wordt er alleen overgenomen bij een expliciet `False` van `pid_exists`. Geen
`houder_pid` (oude slotbestanden), geen geldig getal, of een fout in psutil: geen
levendheidstoets, alleen de leeftijdsgrens zoals voorheen. Pid-hergebruik levert dan een vals
"leeft" op, en dat is de goede kant om fout te zitten -- wachten is hersteld, een tweede
poortrun niet.

MUTATIEBEWIJS (2026-09-19, een regel per tak)
---------------------------------------------
    `_houder_is_aantoonbaar_dood` altijd False  -> 1 failed, 4 passed
                                                   (alleen de winst valt weg)
    `_houder_is_aantoonbaar_dood` altijd True   -> 4 failed, 1 passed
                                                   (levend, levend-niet-kind, geen pid,
                                                    onleesbare pid -- fail-safe omgedraaid)
    ongemuteerd                                 -> 5 passed
De tweede mutatie is de belangrijke: zonder de vier andere takken zou "neem altijd over"
een geldige oplossing zijn, en dan is het slot weg.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_WORTEL = Path(__file__).resolve().parents[3]
_SCRIPT = _WORTEL / "scripts" / "testpoort_slot.py"


def _laad_module():
    """`scripts/` is geen pakket, dus laden op pad."""
    spec = importlib.util.spec_from_file_location("testpoort_slot_voor_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["testpoort_slot_voor_test"] = module
    spec.loader.exec_module(module)
    return module


def _dode_pid() -> int:
    """Een pid van een proces dat aantoonbaar is geeindigd."""
    proces = subprocess.Popen([sys.executable, "-c", "pass"])
    proces.wait()
    import psutil

    assert not psutil.pid_exists(proces.pid), (
        "De pid die als DOOD bedoeld is, bestaat nog. Dan meet deze test niets."
    )
    return proces.pid


@pytest.fixture
def slot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Het slot met een eigen slotbestand, ver van het gedeelde bestand in .git."""
    module = _laad_module()
    pad = tmp_path / "slot.json"
    monkeypatch.setattr(module, "_slotpad", lambda: pad)
    return SimpleNamespace(module=module, pad=pad, mp=monkeypatch)


def _zet_slot(slot, *, houder_pid: object, leeftijd_s: int = 0) -> None:
    """Schrijf een slotbestand alsof een andere sessie het houdt."""
    from datetime import datetime, timedelta, timezone

    sinds = datetime.now(timezone.utc) - timedelta(seconds=leeftijd_s)
    inhoud: dict[str, object] = {
        "sessie": "andere-sessie",
        "werkmap": "C:/tmp/ergens",
        "pid": 1,
        "sinds": sinds.isoformat(),
        "reden": "toets",
    }
    if houder_pid is not None:
        inhoud["houder_pid"] = houder_pid
    slot.pad.write_text(json.dumps(inhoud), encoding="utf-8")


def _probeer_te_pakken(slot) -> int:
    """`pak` met nul wachttijd: 0 = gekregen, 1 = niet gekregen."""
    return slot.module.cmd_pak(
        SimpleNamespace(sessie="ik", reden="toets", wacht=0, houder_pid=None)
    )


def test_een_slot_van_een_LEVEND_proces_wordt_niet_overgenomen(slot) -> None:
    """Tak 1 -- de winst van de leeftijdsgrens mag niet verdwijnen."""
    _zet_slot(slot, houder_pid=os.getpid())

    assert _probeer_te_pakken(slot) == 1, (
        "Het slot van een LEVEND proces is overgenomen. Dan draaien er twee poortruns "
        "naast elkaar en dat is precies waar dit slot voor bestaat (ADR-036 OP-19)."
    )
    bewaard = json.loads(slot.pad.read_text(encoding="utf-8"))
    assert bewaard["sessie"] == "andere-sessie", "het slotbestand is overschreven"


def test_een_slot_van_een_DOOD_proces_wordt_wel_overgenomen(slot) -> None:
    """Tak 2 -- dit is de winst: niet meer wachten op een houder die weg is."""
    _zet_slot(slot, houder_pid=_dode_pid())

    assert _probeer_te_pakken(slot) == 0, (
        "Het slot van een DOOD proces is niet overgenomen. Dan wacht de volgende sessie "
        "tot de leeftijdsgrens van 45 minuten, op een houder die niet meer bestaat."
    )
    bewaard = json.loads(slot.pad.read_text(encoding="utf-8"))
    assert bewaard["sessie"] == "ik"


def test_een_slot_van_een_levend_proces_dat_GEEN_kind_is_blijft_ook_staan(slot) -> None:
    """Tak 1b -- het geval dat in productie geldt, en dat een kindproces NIET dekt.

    De houder van het poortslot is altijd een andere sessie of een pre-push hook: nooit
    een kind van het proces dat de toets uitvoert. Een harnas dat alleen met een eigen
    kindproces meet, toetst die tak niet.
    """
    import psutil

    ouder = os.getppid()
    if not psutil.pid_exists(ouder):
        pytest.skip("geen bruikbaar ouderproces om als levend niet-kind te gebruiken")

    _zet_slot(slot, houder_pid=ouder)

    assert _probeer_te_pakken(slot) == 1, (
        "Het slot van een LEVEND proces dat geen kind van de toetser is, werd overgenomen. "
        "Dat is precies de situatie die in productie geldt."
    )


def test_een_slot_ZONDER_houder_pid_gedraagt_zich_als_voorheen(slot) -> None:
    """Tak 3 -- oude slotbestanden en handmatig gebruik: alleen de leeftijdsgrens."""
    _zet_slot(slot, houder_pid=None)

    assert _probeer_te_pakken(slot) == 1, (
        "Een slot zonder houder_pid is overgenomen. Zonder pid is er GEEN doodsbewijs, "
        "en dan hoort alleen de leeftijdsgrens te gelden."
    )

    # En de leeftijdsgrens werkt daar nog wel.
    _zet_slot(slot, houder_pid=None, leeftijd_s=slot.module._MAX_LEEFTIJD_S + 60)
    assert _probeer_te_pakken(slot) == 0, "de leeftijdsgrens is stukgegaan"


def test_een_ONPARSEERBARE_houder_pid_geeft_geen_overname_en_geen_crash(slot) -> None:
    """Tak 4 -- geen geldig getal is geen doodsbewijs."""
    _zet_slot(slot, houder_pid="niet-een-getal")

    assert _probeer_te_pakken(slot) == 1, (
        "Een onleesbare houder_pid gold als doodsbewijs. Alles wat geen expliciet "
        "'dit proces bestaat niet' is, hoort het slot te laten staan."
    )


def test_een_slot_van_een_LEVEND_proces_ouder_dan_de_grens_wordt_NIET_overgenomen(slot) -> None:
    """Geval B (OP-263) -- levendheid wint van leeftijd.

    De bestaande test `test_een_slot_van_een_LEVEND_proces_wordt_niet_overgenomen`
    zet het slot MET standaard leeftijd_s=0 -- dus ruim binnen de grens. Daarmee valt
    de OR al om op de rechterhelft (niet oud genoeg) en draagt de levendheidstoets niets
    bij. Dit is het ontbrekende geval: de houder leeft aantoonbaar, maar het slot is ouder
    dan _MAX_LEEFTIJD_S. De levendheid moet dan winnen.

    Mutatiebewijs:
    - `if dood or _leeftijd_s(gegevens) > _MAX_LEEFTIJD_S` (oud) -> test ROOD
    - `if dood or (not leeft and _leeftijd_s(gegevens) > _MAX_LEEFTIJD_S)` (nieuw) -> groen
    """
    _zet_slot(slot, houder_pid=os.getpid(), leeftijd_s=slot.module._MAX_LEEFTIJD_S + 60)

    assert _probeer_te_pakken(slot) == 1, (
        "Het slot van een LEVEND proces is overgenomen, ook al is het ouder dan de "
        "leeftijdsgrens. Levendheid moet winnen van leeftijd (OP-263)."
    )
    bewaard = json.loads(slot.pad.read_text(encoding="utf-8"))
    assert bewaard["sessie"] == "andere-sessie", "het slotbestand is overschreven"
