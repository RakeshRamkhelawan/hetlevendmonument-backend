"""Pytest-plugin voor de testronde-waakhond: schrijft per werker welke test loopt en hoe lang die mag.

Wordt NIET zelf aangeroepen. `scripts/testronde_waakhond.py` zet `PYTEST_PLUGINS=testronde_voortgang` en
`TESTRONDE_VOORTGANG=<map>` in de omgeving van de ronde; xdist-werkers erven dat. De plugin doet verder
niets: geen test overslaan, geen uitkomst wijzigen.

**Waarom een plugin en geen `-v`.** De pushronde draait met `-q` en een test die over zijn tijdgrens
gaat en niet gestopt wordt, laat in het log geen sporen na (gemeten 2026-10-24: een werker hing in
`pytest_timeout.cancel()` terwijl de timerthread in `os._exit(1)` stond, en niets in het log noemde de
test). Deze bestanden zijn er wel: per werker de lopende test, het starttijdstip en de toegestane duur.

**Waarom hookwrapper om `pytest_runtest_protocol`, `tryfirst`.** De plugin moet BUITEN pytest-timeout
staan: dat annuleert zijn timer binnen datzelfde protocol. Hangt `cancel()`, dan wordt het slot-schrijven
("klaar") hier nooit bereikt en blijft het bestand zeggen dat de test nog loopt. Dat is het signaal.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Generator
from pathlib import Path

import pytest

_MAP = os.environ.get("TESTRONDE_VOORTGANG")


def _schrijf(inhoud: dict[str, object]) -> None:
    if not _MAP:
        return
    werker = os.environ.get("PYTEST_XDIST_WORKER", "hoofd")
    doel = Path(_MAP) / f"{werker}.json"
    tijdelijk = doel.with_suffix(".tmp")
    try:
        tijdelijk.write_text(json.dumps(inhoud), encoding="utf-8")
    except OSError:
        return
    # Atomair: de waakhond leest nooit een half bestand. Op Windows weigert os.replace (PermissionError)
    # zolang de waakhond het doelbestand op dat moment open heeft (gemeten 2026-10-26: werker gw2 stortte
    # in, ronde exit 3). Daarom herhalen; lukt het niet, dan slaan we deze meting over -- een test mag nooit
    # falen omdat de bewaker meekijkt.
    for _ in range(20):
        try:
            os.replace(tijdelijk, doel)
            return
        except PermissionError:
            time.sleep(0.05)
        except OSError:
            return


def _toegestaan(item: pytest.Item) -> float:
    """De toegestane duur van een test, in dezelfde volgorde als pytest-timeout: marker, `--timeout`, ini.

    0 betekent onbekend of geen grens; de waakhond past dan alleen zijn algemene stilstandsgrens toe.
    """
    marker = item.get_closest_marker("timeout")
    if marker is not None:
        waarde = marker.args[0] if marker.args else marker.kwargs.get("timeout")
        if waarde is not None:
            return float(waarde)
    optie = item.config.getoption("timeout", default=None)
    if optie is not None:
        return float(optie)
    try:
        ini = item.config.getini("timeout")
    except ValueError:
        return 0.0
    return float(ini) if ini not in (None, "") else 0.0


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(
    item: pytest.Item, nextitem: pytest.Item | None
) -> Generator[None, None, None]:
    _schrijf({
            "nodeid": item.nodeid,
            "since": time.time(),
            "toegestaan": _toegestaan(item),
            "pid": os.getpid(),
        })
    yield
    _schrijf({"nodeid": None, "since": time.time(), "toegestaan": 0.0})
