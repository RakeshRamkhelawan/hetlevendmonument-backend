"""De MCP-orchestrator loopt niet meer vast, en verliest zijn meetbasis niet in stilte.

**De aanleiding, gemeten op 2026-09-24.** `complete_task("BE-LLM-005", ...)` gaf twee keer
achter elkaar dertig minuten lang geen antwoord. De logica was niet de oorzaak: buiten de
server nagedraaid duurde dezelfde functie 0,24 seconde. Een py-spy-dump van het LEVENDE
serverproces wees de regel aan:

    join                (threading.py:1094)
    _communicate        (subprocess.py:1644)
    communicate         (subprocess.py:1222)
    run                 (subprocess.py:565)
    _git                (tools/coordination.py)
    _wijzigingen_in_werkkopie
    complete_task

`subprocess.py:565` is -- ALLEEN op Windows -- de tweede aanroep van `process.communicate()`
BINNEN de afhandeling van `TimeoutExpired`, en die krijgt geen timeout mee. Windows leest de
uitvoer in leesdraden en wacht daarop met `join(None)`. Zolang iets de schrijfkant van de pijp
open houdt -- een kleinkind van git dat de `kill()` overleefde -- komt er nooit EOF en wacht die
join voor altijd.

Het net effect: de tijdslimiet VUURDE, en juist het herstelpad daarna hing oneindig. Een grens
die alleen werkt zolang je hem niet nodig hebt.

**Drie gevolgen, hier alle drie afgedekt.**

1. `_git` gebruikt geen pijpen meer. Zonder pijpen bestaat dat herstelpad niet.
2. Het state-slot droeg geen eigenaar. Een vastgelopen server hield het uren vast, en elke
   schrijvende aanroep van ELKE sessie faalde daarna met "State-lock niet verkregen" zonder te
   zeggen wie hem had of dat dat proces nog leefde.
3. `claim_task` legde een lege meetbasis vast zodra git iets niet kon (`_current_head` geeft bij
   elke fout ""). `complete_task` las die leegte als "oudere serverversie" en zakte af naar de
   werkkopie-meting -- zwakker, want die mist al gecommit werk. Precies de
   succes-zonder-werk-vorm uit ADR-036 par. 1, in het gereedschap dat hem moet vangen.

Elke assertie hieronder heeft zijn tegenrichting, zoals `.claude/rules/quality-gates.md` eist.
Zonder die tweede helft zijn "gebruik nooit een subproces", "steel elk slot" en "weiger elke
claim" geldige oplossingen.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

sys.path.insert(0, "mcp-server")

import store  # noqa: E402
from tools import coordination, quality  # noqa: E402


@pytest.fixture
def eigen_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Leid de gedeelde state om naar tmp_path.

    De echte `.git/sanskritisetu-mcp-state.json` is gedeeld met andere sessies; een test
    raakt hem niet aan.
    """
    pad = tmp_path / "state.json"
    monkeypatch.setattr(store, "STATE_PATH", pad)
    monkeypatch.setattr(store, "LOCK_PATH", pad.with_suffix(".lock"))
    return pad


# --------------------------------------------------------------- 1. geen pijpen meer


def test_de_git_aanroep_gebruikt_geen_pijpen() -> None:
    """De kern van de reparatie, getoetst op wat er DOORGEGEVEN wordt, niet op de tekst.

    `capture_output=True` (of `stdout=PIPE`) brengt het deadlock-pad terug. Deze test kijkt
    naar de argumenten waarmee `Popen` echt wordt aangeroepen, zodat hij ook een herschrijving
    betrapt die er anders uitziet maar hetzelfde doet.
    """
    gezien: dict[str, object] = {}
    origineel = subprocess.Popen

    def _vanger(*args: object, **kwargs: object) -> object:
        gezien.update(kwargs)
        return origineel(*args, **kwargs)  # type: ignore[arg-type]

    subprocess.Popen = _vanger  # type: ignore[misc,assignment]
    try:
        coordination._git(["rev-parse", "HEAD"])
    finally:
        subprocess.Popen = origineel  # type: ignore[misc]

    assert gezien.get("stdout") is not subprocess.PIPE, (
        "git schrijft weer naar een PIJP. Op Windows leidt een tijdslimiet dan naar "
        "subprocess.py:565 -- een tweede communicate() ZONDER timeout die oneindig wacht op "
        "een EOF die een overlevend kleinkind tegenhoudt. Dat legde de hele orchestrator plat."
    )
    assert gezien.get("stderr") is not subprocess.PIPE, "stderr staat weer op een pijp"
    assert gezien.get("stdin") == subprocess.DEVNULL, (
        "git kan weer op invoer gaan wachten; in een MCP-server is er niemand die antwoordt"
    )


def test_de_git_aanroep_levert_nog_steeds_gewoon_zijn_uitvoer() -> None:
    """Tegenrichting 1: 'roep git helemaal niet meer aan' is geen geldige oplossing."""
    uit = coordination._git(["rev-parse", "HEAD"]).strip()

    assert len(uit) == 40 and all(teken in "0123456789abcdef" for teken in uit), (
        f"git leverde geen bruikbare commit-sha maar {uit!r}"
    )


def test_een_mislukte_git_aanroep_blijft_een_fout() -> None:
    """Tegenrichting 2: zonder `check=True` mag een fout niet stil een lege string worden.

    De hele meetbasis hangt hieraan: een git-fout die als leeg antwoord doorgaat, is precies
    hoe `claim_head` leeg raakte.
    """
    with pytest.raises(subprocess.CalledProcessError):
        coordination._git(["rev-parse", "deze-verwijzing-bestaat-niet-xyzzy"])


# --------------------------------------------------------------- 2. het slot heeft een eigenaar


def _dood_procesnummer() -> int:
    """Een procesnummer dat GEGARANDEERD niet meer draait."""
    proces = subprocess.Popen(
        [sys.executable, "-c", "pass"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proces.wait(timeout=30)
    return proces.pid


def test_een_slot_van_een_DOOD_proces_wordt_overgenomen(eigen_state: Path) -> None:
    """Zonder dit legt een enkele vastgelopen server elke sessie stil tot iemand handmatig
    een bestand weghaalt -- en dat is precies wat er op 2026-09-24 uren gebeurde."""
    store.LOCK_PATH.write_text(
        json.dumps({"pid": _dood_procesnummer(), "cwd": "C:\\weg", "at": "2026-09-24T00:00:00"}),
        encoding="utf-8",
    )

    with store._locked(timeout=1.0):
        inhoud = json.loads(store.LOCK_PATH.read_text(encoding="utf-8"))

    assert inhoud["pid"] == os.getpid(), "het slot is niet overgenomen door deze aanroep"
    assert not store.LOCK_PATH.exists(), "het slot is na afloop niet teruggegeven"


def test_een_slot_van_een_LEVEND_proces_wordt_NOOIT_overgenomen(eigen_state: Path) -> None:
    """De tegenrichting, en de belangrijkste helft.

    Zonder deze test is "steel altijd" een geldige implementatie, en dan schrijven twee
    processen tegelijk in dezelfde state -- schadelijker dan het probleem dat we oplosten.
    """
    store.LOCK_PATH.write_text(
        json.dumps({"pid": os.getpid(), "cwd": str(Path.cwd()), "at": "2026-09-24T00:00:00"}),
        encoding="utf-8",
    )

    with pytest.raises(TimeoutError) as fout:
        with store._locked(timeout=0.3):
            pass

    assert str(os.getpid()) in str(fout.value), (
        "de melding noemt niet WIE het slot vasthoudt; dat was precies wat ontbrak"
    )
    assert store.LOCK_PATH.exists(), "een slot van een levend proces is toch weggehaald"


def test_een_onleesbaar_slot_telt_als_LEVEND(eigen_state: Path) -> None:
    """Liever wachten dan raden. Een half geschreven slotbestand is geen bewijs van een
    dode eigenaar -- er is een venster tussen het aanmaken en het beschrijven ervan."""
    store.LOCK_PATH.write_text("dit is geen json", encoding="utf-8")

    with pytest.raises(TimeoutError):
        with store._locked(timeout=0.3):
            pass

    assert store.LOCK_PATH.exists()


def test_de_levenscontrole_doodt_het_proces_niet() -> None:
    """Op Windows doet `os.kill(pid, 0)` een TerminateProcess.

    De gebruikelijke POSIX-truc zou hier dus het proces DODEN dat hij moest controleren --
    en dat is geen theoretisch risico: `_locked` roept dit aan op het procesnummer van een
    COLLEGA-sessie. Deze test draait de controle op zichzelf; leeft hij daarna nog, dan
    klopt het.
    """
    assert store._proces_leeft(os.getpid()) is True
    assert store._proces_leeft(_dood_procesnummer()) is False
    assert store._proces_leeft(0) is False


# --------------------------------------------------------------- 3. de meetbasis


def test_claimen_zonder_meetbasis_wordt_GEWEIGERD(
    eigen_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Een claim zonder basis is geen claim.

    Voor deze wijziging werd `claim_head` gewoon "" en liep de taak door; `complete_task`
    las die leegte als "oudere serverversie" en mat alleen de werkkopie. Al gecommit werk viel
    daarmee buiten elke poort, en het enige signaal stond in een antwoordveld.
    """
    coordination.register_task("T-GEEN-BASIS", "toets", "P2", None, [])
    monkeypatch.setattr(coordination, "_current_head", lambda *a, **k: "")

    uit = coordination.claim_task("T-GEEN-BASIS", "toetser", "iter/toets")

    assert uit["ok"] is False
    assert "meetbasis" in uit["reason"].lower()

    data = json.loads(eigen_state.read_text(encoding="utf-8"))
    assert data["tasks"]["T-GEEN-BASIS"]["status"] != "in_progress", (
        "de taak staat toch in behandeling terwijl de claim is geweigerd"
    )


def test_claimen_MET_meetbasis_gaat_gewoon_door(eigen_state: Path) -> None:
    """Tegenrichting: 'weiger elke claim' is geen geldige oplossing."""
    coordination.register_task("T-WEL-BASIS", "toets", "P2", None, [])

    uit = coordination.claim_task("T-WEL-BASIS", "toetser", "iter/toets")

    assert uit["ok"] is True, uit
    data = json.loads(eigen_state.read_text(encoding="utf-8"))
    taak = data["tasks"]["T-WEL-BASIS"]
    assert taak["status"] == "in_progress"
    assert len(taak["claim_head"]) == 40, "de meetbasis is niet vastgelegd"


# ------------------------------------------- 4. de ratchet meet structuur, geen tekst


_MODEL_MET_VERZOEKVELD = """from pydantic import BaseModel


class MaakAgent(BaseModel):
    naam: str
    tenant_id: int
"""

_DIENST_MET_PARAMETER = """class Dienst:
    async def toon(self, tenant_id: int) -> list[str]:
        return []

    async def keten(self, tenant_id: int) -> list[str]:
        return []
"""


def test_een_tenant_id_in_een_VERZOEKLICHAAM_telt_mee(tmp_path: Path) -> None:
    """De regel die deze metriek hoort af te dwingen: nooit tenant_id uit een request body."""
    pad = tmp_path / "schema.py"
    pad.write_text(_MODEL_MET_VERZOEKVELD, encoding="utf-8")

    assert quality._tel_tenant_id_in_een_verzoeklichaam(pad) == 1


def test_een_tenant_id_als_FUNCTIEPARAMETER_telt_NIET_mee(tmp_path: Path) -> None:
    """De tegenrichting, en de reden dat deze reparatie bestaat.

    Gemeten 2026-09-24: het oude patroon `tenant_id: (str|UUID|int|Optional)` telde er vijf in
    `tenant_llm_provider_service.py` -- alle vijf methodes die hun tenant als argument KRIJGEN,
    wat precies het voorgeschreven patroon is. De ratchet blokkeerde daarmee het afsluiten van
    een taak wegens code die de regel juist naleeft. Dat is TEKST toetsen waar STRUCTUUR hoort.
    """
    pad = tmp_path / "dienst.py"
    pad.write_text(_DIENST_MET_PARAMETER, encoding="utf-8")

    assert quality._tel_tenant_id_in_een_verzoeklichaam(pad) == 0


def test_een_onleesbaar_bestand_wordt_niet_stil_schoon_verklaard(tmp_path: Path) -> None:
    """Nul teruggeven bij een ontleedfout zou een kapot bestand schoon verklaren.

    Dat is de succes-zonder-werk-vorm: geen fout, geen bevinding, geen werk gedaan. De
    terugval is daarom het OUDE patroon -- grover, maar het meldt nog iets.
    """
    pad = tmp_path / "kapot.py"
    pad.write_text("class X(BaseModel:\n    tenant_id: int\n", encoding="utf-8")

    assert quality._tel_tenant_id_in_een_verzoeklichaam(pad) == 1


def test_de_RATCHET_zelf_telt_een_functieparameter_niet_mee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Via `scan_file`, niet via de hulpfunctie -- anders bewaakt de test de bedrading niet.

    Gemeten tijdens het mutatiebewijs van deze reparatie: de mutatie "zet de aanroep in
    `scan_file` terug naar de oude regex" bleef GROEN, omdat de tests hierboven de hulpfunctie
    rechtstreeks aanroepen. Een bewaker die het onderdeel toetst maar niet de plek waar het
    gebruikt wordt, laat precies de terugdraaiing door die hij moet vangen.
    """
    pad = tmp_path / "dienst.py"
    pad.write_text(_DIENST_MET_PARAMETER, encoding="utf-8")
    monkeypatch.setattr(quality, "REPO_ROOT", tmp_path)

    assert quality.scan_file("dienst.py")["tenant_id_in_body"] == 0


# ------------------------------------- 5. datetime_naive telt gedrag, geen schrijfwijze


_NAIEVE_DATETIMES = """from datetime import datetime


def a():
    return datetime.now()


def b():
    return datetime.utcnow()
"""

_TIJDZONEBEWUSTE_DATETIMES = """from datetime import datetime, timezone, UTC


def a():
    return datetime.now(timezone.utc)


def b():
    return datetime.now(UTC)


def c():
    return datetime.now(tz=timezone.utc)


def d(self):
    return datetime.now(tz=self.created_at.tzinfo)
"""


def test_een_naieve_datetime_wordt_GETELD(tmp_path: Path) -> None:
    """De metriek moet kunnen tellen -- een uitslag van nul is anders geen resultaat.

    Gemeten na de reparatie: de nieuwe metriek meldt 0 overtredingen over heel `src/`, waar
    de oude er 27 meldde. Nul is in dit project eerst een verdenking van een defect, dus dit
    is de test die aantoont dat hij wel degelijk kan aanslaan.
    """
    pad = tmp_path / "naief.py"
    pad.write_text(_NAIEVE_DATETIMES, encoding="utf-8")

    assert quality._tel_naieve_datetimes(pad) == 2


def test_ELKE_schrijfwijze_van_een_tijdzone_telt_NIET_mee(tmp_path: Path) -> None:
    """De tegenrichting, en de hele reden van deze reparatie.

    Gemeten over alle python-bestanden in `src/`: de oude regex meldde 27 overtredingen en
    alle 27 gaven een tijdzone mee. De gemiste schrijfwijzen staan hieronder. Twee sessies
    telden ze onafhankelijk met het oog na en kwamen allebei te laag uit, omdat ze allebei
    een LIJST van bekende spellingen hanteerden. Een AST-controle kent geen spellingen: hij
    vraagt of er een argument STAAT.
    """
    pad = tmp_path / "bewust.py"
    pad.write_text(_TIJDZONEBEWUSTE_DATETIMES, encoding="utf-8")

    assert quality._tel_naieve_datetimes(pad) == 0


def test_een_now_op_iets_anders_dan_datetime_telt_niet_mee(tmp_path: Path) -> None:
    """`self.klok.now()` is geen datetime-aanroep.

    Zonder deze grens zou elke methode die toevallig `now` heet als overtreding gelden, en
    dan is de metriek op een andere manier onbruikbaar dan voorheen.
    """
    pad = tmp_path / "klok.py"
    pad.write_text("def a(self):\n    return self.klok.now()\n", encoding="utf-8")

    assert quality._tel_naieve_datetimes(pad) == 0


def test_de_RATCHET_zelf_telt_een_tijdzonebewuste_datetime_niet_mee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Via `scan_file`, want een test op de hulpfunctie bewaakt de bedrading niet.

    Dezelfde les als bij `tenant_id_in_body`: daar bleef de mutatie "zet de aanroep in
    scan_file terug naar de oude regex" groen tot deze vorm erbij kwam.
    """
    pad = tmp_path / "bewust.py"
    pad.write_text(_TIJDZONEBEWUSTE_DATETIMES, encoding="utf-8")
    monkeypatch.setattr(quality, "REPO_ROOT", tmp_path)

    assert quality.scan_file("bewust.py")["datetime_naive"] == 0
