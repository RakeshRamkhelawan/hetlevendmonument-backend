"""Elke CronTrigger in de scheduler heeft een expliciete tijdzone (plan-van-aanpak-nazorg II-2).

Een `CronTrigger(...)`-instantie zonder `timezone` valt in APScheduler 3.x terug op
`get_localzone()`, niet op de zone van de scheduler. In de container is dat UTC, op de
ontwikkelmachine Europe/Amsterdam, en het log zei altijd "(UTC)".

Twee metingen, met opzet:
- AST: elke `CronTrigger(...)`-aanroep in `src/workers/scheduler.py` heeft een
  `timezone=`-argument. Die faalt ook als de lokale zone toevallig gelijk is aan de bedoelde.
- Gedrag: na `initialize()` heeft elke job precies de zone uit de indeling, en de
  debiteurenjob valt rond de zomer-/wintertijdwissel op 04:15 lokaal.
"""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

_SCHEDULER = Path(__file__).resolve().parents[3] / "src" / "workers" / "scheduler.py"

#: Jobs die de klant merkt; de rest is onderhoud en draait in UTC.
KLANTJOBS = {"volg_debiteuren_op", "verstuur_klare_berichten", "signaleer_hr_termijnen"}


def _cron_aanroepen_zonder_tijdzone() -> list[int]:
    boom = ast.parse(_SCHEDULER.read_text(encoding="utf-8"))
    zonder: list[int] = []
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.Call):
            continue
        naam = knoop.func.id if isinstance(knoop.func, ast.Name) else None
        if naam != "CronTrigger":
            continue
        if not any(kw.arg == "timezone" for kw in knoop.keywords):
            zonder.append(knoop.lineno)
    return zonder


def _aantal_cron_aanroepen() -> int:
    boom = ast.parse(_SCHEDULER.read_text(encoding="utf-8"))
    return sum(
        1
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.Call)
        and isinstance(knoop.func, ast.Name)
        and knoop.func.id == "CronTrigger"
    )


def test_elke_crontrigger_heeft_een_tijdzone() -> None:
    zonder = _cron_aanroepen_zonder_tijdzone()

    assert zonder == [], (
        f"CronTrigger zonder timezone op regel {zonder} van {_SCHEDULER.name}. Zonder zone "
        "valt APScheduler terug op de lokale klok van de machine (get_localzone())."
    )


def test_de_bron_is_echt_gelezen() -> None:
    """Vangnet: een parse die niets vindt maakt de test hierboven trivially groen."""
    assert _aantal_cron_aanroepen() >= 15


async def _jobs() -> dict[str, Any]:
    from src.workers.scheduler import TaskScheduler

    ts = TaskScheduler()
    assert await ts.initialize()
    assert ts.scheduler is not None
    return {job.id: job for job in ts.scheduler.get_jobs()}


@pytest.mark.asyncio
async def test_klantjobs_draaien_in_europe_amsterdam() -> None:
    jobs = await _jobs()

    zones = {jid: str(jobs[jid].trigger.timezone) for jid in KLANTJOBS}

    assert zones == {jid: "Europe/Amsterdam" for jid in KLANTJOBS}


@pytest.mark.asyncio
async def test_onderhoudsjobs_draaien_in_utc() -> None:
    jobs = await _jobs()

    afwijkend = {
        jid: str(job.trigger.timezone)
        for jid, job in jobs.items()
        if jid not in KLANTJOBS and str(job.trigger.timezone) != "UTC"
    }

    assert afwijkend == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("nu", "verwacht_utc"),
    [
        # Wintertijd begint zondag 2026-10-25: 04:15 lokaal is dan 03:15 UTC.
        ("2026-10-25T00:00:00+00:00", "2026-10-25T03:15:00+00:00"),
        # Zomertijd begint zondag 2027-03-28: 04:15 lokaal is dan 02:15 UTC.
        ("2027-03-28T00:00:00+00:00", "2027-03-28T02:15:00+00:00"),
    ],
)
async def test_debiteurenjob_valt_rond_de_wissel_op_04_15_lokaal(
    nu: str, verwacht_utc: str
) -> None:
    jobs = await _jobs()
    trigger = jobs["volg_debiteuren_op"].trigger

    volgende = trigger.get_next_fire_time(None, datetime.fromisoformat(nu))

    assert volgende.astimezone(ZoneInfo("UTC")) == datetime.fromisoformat(verwacht_utc)


@pytest.mark.asyncio
async def test_pack_health_om_02_00_valt_niet_in_het_wisselvenster() -> None:
    """02:00 in UTC is op de wisseldag 03:00 lokaal: buiten 02:00-03:00 Europe/Amsterdam."""
    jobs = await _jobs()
    trigger = jobs["pack_health_aggregation"].trigger

    volgende = trigger.get_next_fire_time(None, datetime.fromisoformat("2026-10-25T00:00:00+00:00"))

    assert volgende.astimezone(ZoneInfo("Europe/Amsterdam")).hour == 3
