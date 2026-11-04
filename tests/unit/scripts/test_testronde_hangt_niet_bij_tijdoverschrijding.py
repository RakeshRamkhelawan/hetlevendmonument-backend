"""Een test die over zijn tijdgrens gaat laat de testronde ROOD eindigen met zijn naam; de ronde hangt niet.

Brief 2026-10-25 (de testronde loopt nooit vast). Gemeten op 2026-10-24 en 2026-10-25 met py-spy: twee keer hing
een pushronde op 97% omdat een werker in `pytest_timeout.cancel()` wachtte op de timerthread, die in
`os._exit(1)` stond. Reproductie van die OS-hang lukte NIET (vijf proeven onder `-n 4`, tests op de grens,
met geheugen en threads, en de twee echte bestanden: steeds een nette crash en een rode ronde). Daarom toetst
deze test de WAAKHOND (`scripts/testronde_waakhond.py` met de plugin `scripts/testronde_voortgang.py`) en niet
de oorzaak: een werker waarvan een test niet wordt gestopt wordt na zijn toegestane duur plus een marge
gestopt, de test wordt genoemd en de ronde eindigt met exitcode 1.

Hoe de hang nagebootst wordt: een geneste ronde met `-n 2` en `-p no:timeout` (er is dus NIETS dat de test
stopt) en een `@pytest.mark.timeout(2)` die alleen de toegestane duur voor de waakhond vastlegt.

MUTATIEBEWIJS (2026-10-26):
    de waakhond weglaten (`python -m pytest ...` rechtstreeks)         -> dezelfde ronde hangt (gemeten: na
                                                                          25 s nog bezig, exit 124 van mijn buitengrens)
    na een ingreep exitcode 0 teruggeven                                -> `..._eindigt_rood_met_zijn_naam` ROOD
    de toegestane duur negeren (alleen de marge als grens)              -> `..._eigen_grote_timeout...` ROOD en
                                                                          `..._binnen_zijn_duur_plus_marge...` ROOD
    de naam van de test niet meer printen                               -> `..._eindigt_rood_met_zijn_naam` ROOD
    legitiem: een snelle ronde, en een trage test met een eigen timeout  -> GROEN, niet afgebroken
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WAAKHOND = REPO_ROOT / "scripts/testronde_waakhond.py"

#: Een geneste ronde start xdist en twee werkers; op een drukke machine kost dat tientallen seconden.
GENESTE_RONDE_TIMEOUT = 180


def _waakhond_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("testronde_waakhond", WAAKHOND)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ronde(
    map_: Path, testbestand: str, marge: str = "3"
) -> tuple[subprocess.CompletedProcess[str], float]:
    (map_ / "test_geneste_ronde.py").write_text(testbestand, encoding="utf-8")
    omgeving = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    omgeving.update(
        {"TESTRONDE_MARGE": marge, "TESTRONDE_POLL": "0.5", "TESTRONDE_STILSTAND": "120"}
    )
    commando = [
        sys.executable,
        str(WAAKHOND),
        "-m",
        "pytest",
        str(map_),
        "-n",
        "2",
        "-p",
        "no:timeout",
        "-p",
        "no:cacheprovider",
        "--rootdir",
        str(map_),
        "-q",
        "--tb=line",
    ]
    start = time.time()
    uitslag = subprocess.run(
        commando,
        env=omgeving,
        capture_output=True,
        text=True,
        timeout=GENESTE_RONDE_TIMEOUT - 30,
        check=False,
    )
    return uitslag, time.time() - start


_VASTGELOPEN = """
import time
import pytest

@pytest.mark.timeout(2)
def test_hangt_voor_altijd():
    time.sleep(90)

def test_snel():
    pass
"""

_SNEL = """
def test_een():
    pass

def test_twee():
    pass
"""

_TRAAG_MET_EIGEN_GRENS = """
import time
import pytest

@pytest.mark.timeout(30)
def test_traag_maar_legitiem():
    time.sleep(7)  # langer dan toegestaan (2) + marge (3) zou stoppen, maar zijn EIGEN grens is 30
"""

_FALEND = """
def test_faalt():
    assert False
"""


@pytest.mark.timeout(GENESTE_RONDE_TIMEOUT)
def test_een_vastgelopen_test_eindigt_rood_met_zijn_naam(tmp_path: Path) -> None:
    uitslag, duur = _ronde(tmp_path, _VASTGELOPEN)

    assert (uitslag.returncode, "test_hangt_voor_altijd" in uitslag.stdout, duur < 80) == (
        1,
        True,
        True,
    ), uitslag.stdout[-800:]


@pytest.mark.timeout(GENESTE_RONDE_TIMEOUT)
def test_een_snelle_ronde_blijft_groen_en_wordt_niet_afgebroken(tmp_path: Path) -> None:
    uitslag, _ = _ronde(tmp_path, _SNEL)

    assert (uitslag.returncode, "VASTGELOPEN" in uitslag.stdout) == (0, False), uitslag.stdout[
        -800:
    ]


@pytest.mark.timeout(GENESTE_RONDE_TIMEOUT)
def test_een_trage_test_met_een_eigen_grote_timeout_wordt_niet_afgebroken(tmp_path: Path) -> None:
    uitslag, _ = _ronde(tmp_path, _TRAAG_MET_EIGEN_GRENS)

    assert (uitslag.returncode, "VASTGELOPEN" in uitslag.stdout) == (0, False), uitslag.stdout[
        -800:
    ]


@pytest.mark.timeout(GENESTE_RONDE_TIMEOUT)
def test_een_falende_test_houdt_de_ronde_rood_zonder_ingreep(tmp_path: Path) -> None:
    uitslag, _ = _ronde(tmp_path, _FALEND)

    assert (uitslag.returncode, "VASTGELOPEN" in uitslag.stdout) == (1, False), uitslag.stdout[
        -800:
    ]


def _regel(nodeid: str, since: float, toegestaan: float) -> dict[str, object]:
    return {"nodeid": nodeid, "since": since, "toegestaan": toegestaan, "werker": "gw0"}


def test_een_test_binnen_zijn_duur_plus_marge_is_niet_vastgelopen() -> None:
    module = _waakhond_module()

    assert module.vastgelopen([_regel("t", 1000.0, 60.0)], nu=1170.0, marge=120.0) == []


def test_een_test_boven_zijn_duur_plus_marge_is_vastgelopen() -> None:
    module = _waakhond_module()

    assert len(module.vastgelopen([_regel("t", 1000.0, 60.0)], nu=1181.0, marge=120.0)) == 1


def test_zonder_bekende_duur_is_er_geen_oordeel() -> None:
    """Een test zonder grens (0) wordt alleen door de algemene stilstandsgrens bewaakt."""
    module = _waakhond_module()

    assert module.vastgelopen([_regel("t", 0.0, 0.0)], nu=10**9, marge=120.0) == []


def _voortgang_module(monkeypatch: pytest.MonkeyPatch, map_: Path) -> ModuleType:
    monkeypatch.setenv("TESTRONDE_VOORTGANG", str(map_))
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)  # onder xdist heet het bestand anders
    spec = importlib.util.spec_from_file_location(
        "testronde_voortgang_proef", REPO_ROOT / "scripts/testronde_voortgang.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_een_tijdelijk_vergrendeld_bestand_wordt_herhaald_en_niet_opgegeven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows weigert os.replace zolang de waakhond het doel leest; gemeten 2026-10-26 (ronde exit 3)."""
    module = _voortgang_module(monkeypatch, tmp_path)
    echte_replace = os.replace
    pogingen = [0]

    def weigert_twee_keer(bron: object, doel: object) -> None:
        pogingen[0] += 1
        if pogingen[0] <= 2:
            raise PermissionError(5, "Toegang geweigerd")
        echte_replace(str(bron), str(doel))

    monkeypatch.setattr(module.os, "replace", weigert_twee_keer)

    module._schrijf({"nodeid": "t", "since": 1.0, "toegestaan": 5.0})

    assert (tmp_path / "hoofd.json").exists()


def test_een_blijvend_geweigerd_bestand_laat_de_test_niet_falen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _voortgang_module(monkeypatch, tmp_path)

    def weigert_altijd(bron: object, doel: object) -> None:
        raise PermissionError(5, "Toegang geweigerd")

    monkeypatch.setattr(module.os, "replace", weigert_altijd)
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)

    module._schrijf({"nodeid": "t", "since": 1.0, "toegestaan": 5.0})

    assert not (tmp_path / "hoofd.json").exists()


def test_uitvoer_die_geen_utf8_is_laat_de_waakhond_niet_hangen(tmp_path: Path) -> None:
    """Gemeten door de reviewer: een e-accent in cp1252-uitvoer doodde de doorgeefthread; de pijp liep vol."""
    kind = tmp_path / "kind.py"
    kind.write_text(
        "import sys\n"
        "for _ in range(30000):\n"
        "    sys.stdout.buffer.write(bytes([0x63, 0xE9, 0x80, 0x20]) + b'regel' + bytes([10]))\n"
        "sys.stdout.buffer.flush()\n",
        encoding="utf-8",
    )

    uitslag = subprocess.run(
        [sys.executable, str(WAAKHOND), str(kind)],
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert (uitslag.returncode, uitslag.stdout.count(b"regel")) == (0, 30000)


def test_het_voortgangsbestand_van_een_gestorven_werker_telt_niet_mee(tmp_path: Path) -> None:
    import json

    gestopt = subprocess.Popen([sys.executable, "-c", "pass"])
    gestopt.wait()
    (tmp_path / "gw7.json").write_text(
        json.dumps({"nodeid": "t", "since": 1.0, "toegestaan": 5.0, "pid": gestopt.pid}),
        encoding="utf-8",
    )

    assert _waakhond_module().lees_voortgang(tmp_path) == []


_MET_KIND = """
import subprocess, sys
import pytest

@pytest.mark.timeout(2)
def test_hangt_met_kind():
    kind = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"])
    open(sys.argv[0] + ".kindpid", "w").write(str(kind.pid))
    kind.wait()
"""


@pytest.mark.timeout(GENESTE_RONDE_TIMEOUT)
def test_na_een_ingreep_blijft_geen_kindproces_van_de_werker_staan(tmp_path: Path) -> None:
    import psutil

    pidbestand = tmp_path / "kindpid.txt"
    testbestand = _MET_KIND.replace('sys.argv[0] + ".kindpid"', repr(str(pidbestand)))

    uitslag, _ = _ronde(tmp_path, testbestand)
    kindpid = int(pidbestand.read_text(encoding="utf-8"))

    assert (uitslag.returncode, psutil.pid_exists(kindpid)) == (1, False), uitslag.stdout[-800:]


def test_de_waakhond_houdt_de_pc_wakker_tijdens_de_ronde_en_laat_hem_daarna_los(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TESTRONDE_POLL", "0.1")
    module = _waakhond_module()
    aanroepen: list[int] = []
    monkeypatch.setattr(module, "_zet_uitvoeringsstatus", lambda vlaggen: aanroepen.append(vlaggen) or 1)

    returncode = module.main(["-c", "pass"])

    assert (returncode, aanroepen) == (
        0,
        [module.ES_CONTINUOUS | module.ES_SYSTEM_REQUIRED, module.ES_CONTINUOUS],
    )


@pytest.mark.skipif(sys.platform != "win32", reason="SetThreadExecutionState bestaat alleen op Windows")
def test_de_echte_windows_aanroep_om_de_pc_wakker_te_houden_slaagt() -> None:
    module = _waakhond_module()
    try:
        gelukt = module.houd_pc_wakker()
    finally:
        module.laat_pc_los()

    assert gelukt is True


def test_een_sprong_van_de_wandklok_boven_de_pollgrens_telt_als_slaapstand() -> None:
    assert _waakhond_module().slaapgat(nu=3400.0, vorige_poll=100.0, poll=5.0) == 3295.0


def test_een_gewone_vertraging_van_een_poll_telt_niet_als_slaapstand() -> None:
    assert _waakhond_module().slaapgat(nu=112.0, vorige_poll=100.0, poll=5.0) == 0.0


def test_een_slaap_vroeg_in_de_ronde_verbergt_een_hang_daarna_niet() -> None:
    """Reviewer Gate 2: de som van alle slaapstand ging van elke test af en maakte een latere hang 3300 s onzichtbaar."""
    module = _waakhond_module()
    afgetrokken: dict[tuple[str, float], float] = {}
    vroeg = [_regel("vroeg", 1000.0, 60.0)]
    module.corrigeer_voor_slaapstand(vroeg, afgetrokken, gat=3300.0, begonnen_voor=1100.0)

    # Pas na de slaap begonnen, maar in dezelfde poll die de sprong zag: mag niets van de slaap krijgen.
    laat = [_regel("laat", 5000.0, 60.0)]
    module.corrigeer_voor_slaapstand(laat, afgetrokken, gat=3300.0, begonnen_voor=4000.0)

    assert [len(module.vastgelopen(vroeg, 4300.0, 120.0)), len(module.vastgelopen(laat, 5181.0, 120.0))] == [
        0,
        1,
    ]


def test_een_test_die_voor_de_slaap_liep_wordt_niet_afgebroken_om_de_slaap() -> None:
    module = _waakhond_module()
    regels = [_regel("liep", 1000.0, 60.0)]
    module.corrigeer_voor_slaapstand(regels, {}, gat=3300.0, begonnen_voor=1100.0)

    assert module.vastgelopen(regels, 4400.0, 120.0) == []


def test_een_poll_die_een_halve_minuut_te_laat_komt_is_geen_slaapstand() -> None:
    assert _waakhond_module().slaapgat(nu=135.0, vorige_poll=100.0, poll=5.0) == 0.0
