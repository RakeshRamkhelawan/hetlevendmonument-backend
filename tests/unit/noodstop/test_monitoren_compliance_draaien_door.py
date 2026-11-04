"""Compliance-monitoren draaien DOOR voor een stilgezette klant (besluit B van de gebruiker, ronde 2).

Consent-verval en auditanomalie zijn wettelijke waakhonden: een noodstop mag ze niet blind maken.
Wat uit zo'n signaal voortkomt (een melding, een actie) weigert de Council voor een stilgezette
klant zelf. Alle andere monitoren blijven wel overgeslagen.
"""

from __future__ import annotations

import importlib
import pkgutil
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.noodstop import guard

STIL, ACTIEF = 1, 2

#: De monitoren die doordraaien, met de reden (staat ook bij de klasse).
DOORDRAAIERS = {
    "consent_expiry": "wettelijke termijn voor toestemming (AVG); mag niet blind worden",
    "audit_anomaly": "beveiligingswaakhond op het auditlog; mag niet blind worden",
}


@pytest.fixture(autouse=True)
def _klant_1_staat_stil(monkeypatch: pytest.MonkeyPatch) -> None:
    async def lezer(tenant_id: int) -> bool:
        return tenant_id == STIL

    monkeypatch.setattr(guard, "_lees_stand", lezer)


async def _draai(monitor: MagicMock) -> list[int]:
    from src.core.copilot.proactive.scheduler import ProactiveScheduler

    repo = MagicMock()
    repo.list_active_ids = AsyncMock(return_value=[STIL, ACTIEF])
    planner = ProactiveScheduler(scheduler=MagicMock(), tenant_repo=repo, monitors=[monitor])
    await planner._run_for_all_tenants(monitor)
    return [c.args[0] for c in monitor.detect.await_args_list]


def _monitor(doordraaien: bool) -> MagicMock:
    monitor = MagicMock()
    monitor.name = "m"
    monitor.interval_seconds = 60
    monitor.blijft_draaien_bij_noodstop = doordraaien
    monitor.detect = AsyncMock(return_value=[])
    return monitor


@pytest.mark.asyncio
async def test_een_compliance_monitor_detecteert_ook_voor_de_stilgezette_klant() -> None:
    assert await _draai(_monitor(True)) == [STIL, ACTIEF]


@pytest.mark.asyncio
async def test_een_gewone_monitor_blijft_overgeslagen_voor_de_stilgezette_klant() -> None:
    assert await _draai(_monitor(False)) == [ACTIEF]


@pytest.mark.asyncio
async def test_een_monitor_zonder_expliciete_vlag_blijft_overgeslagen() -> None:
    monitor = MagicMock()  # elk attribuut van een MagicMock is "waar": alleen een echte True telt
    monitor.name = "m"
    monitor.interval_seconds = 60
    monitor.detect = AsyncMock(return_value=[])
    assert await _draai(monitor) == [ACTIEF]


def test_alleen_de_twee_compliance_monitoren_draaien_door() -> None:
    import src.core.copilot.proactive.monitors as pakket
    from src.core.copilot.proactive.monitor import ProactiveMonitor

    for module in pkgutil.iter_modules(pakket.__path__):
        importlib.import_module(f"{pakket.__name__}.{module.name}")
    doorlopers = {
        m.name for m in ProactiveMonitor.__subclasses__() if m.blijft_draaien_bij_noodstop is True
    }
    assert doorlopers == set(DOORDRAAIERS), (
        f"Doordraaiers zijn {sorted(doorlopers)}, verwacht {sorted(DOORDRAAIERS)}. Een nieuwe "
        "doorloper vraagt een besluit en een reden in DOORDRAAIERS (en bij de klasse)."
    )
