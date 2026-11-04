"""De aggregatiejob schrijft geen `pack_usage_aggregates`-rijen zolang er geen catalogus bestaat.

Besluit regie 2026-10-23 (schemadrift-rapport): `pack_id` is in de database een UUID met een
verwijzing naar `domain_packs`, de job kent alleen een pakketsleutel als tekst. Elke insert
faalde; de job staat daarom bewust uit, met een INFO-regel, zonder fout en zonder insert.

Mutatiebewijs (nog te draaien na "push klaar"): `SCHRIJF_PACK_USAGE_AGGREGATEN = True` in de
module -> de eerste drie tests ROOD; de schakelaartest (andere kant) blijft groen en bewijst
dat de uitschakeling de enige reden is dat er niets geschreven wordt.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.jobs import analytics_aggregation as job

DATUM = datetime(2026, 10, 22, tzinfo=timezone.utc)


@pytest.fixture
def db() -> MagicMock:
    sessie = MagicMock()
    sessie.add = MagicMock()
    sessie.commit = AsyncMock()
    return sessie


@pytest.fixture
def opstelling(monkeypatch: pytest.MonkeyPatch, db: MagicMock) -> AsyncMock:
    """Een sector die k-anoniem is, zodat de job WEL zou schrijven als hij aan stond."""

    @asynccontextmanager
    async def sessie() -> AsyncGenerator[MagicMock]:
        yield db

    aggregeer = AsyncMock(return_value=[MagicMock()])
    monkeypatch.setattr(job, "get_db_session", sessie)
    monkeypatch.setattr(job, "get_active_companies", AsyncMock(return_value=[MagicMock()]))
    monkeypatch.setattr(job, "get_opted_out_company_ids", AsyncMock(return_value=set()))
    monkeypatch.setattr(job, "group_companies_by_sector", lambda _c, _o: {"tech": [MagicMock()]})
    monkeypatch.setattr(job, "filter_k_anonymous_sectors", lambda _g: {"tech": [MagicMock()]})
    monkeypatch.setattr(job, "aggregate_sector_data", aggregeer)
    monkeypatch.setattr(job, "cleanup_old_aggregations", AsyncMock(return_value=0))
    return aggregeer


@pytest.mark.asyncio
async def test_de_job_probeert_geen_insert(opstelling: AsyncMock, db: MagicMock) -> None:
    await job.run_analytics_aggregation(DATUM)

    assert not db.add.called and not opstelling.called


@pytest.mark.asyncio
async def test_de_job_crasht_niet_en_meldt_de_reden(opstelling: AsyncMock) -> None:
    resultaat = await job.run_analytics_aggregation(DATUM)

    assert resultaat["errors"] == [] and resultaat["aggregates_created"] == 0
    assert resultaat["aggregation_disabled"] == job.UITGESCHAKELD_REDEN


@pytest.mark.asyncio
async def test_de_reden_komt_een_keer_op_info_en_niet_als_fout(
    opstelling: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=job.logger.name):
        await job.run_analytics_aggregation(DATUM)

    regels = [r for r in caplog.records if job.UITGESCHAKELD_REDEN in r.getMessage()]
    assert [r.levelno for r in regels] == [logging.INFO]


@pytest.mark.asyncio
async def test_met_de_schakelaar_aan_schrijft_de_job_wel(
    opstelling: AsyncMock, db: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(job, "SCHRIJF_PACK_USAGE_AGGREGATEN", True)

    await job.run_analytics_aggregation(DATUM)

    assert opstelling.await_count == 1 and db.add.call_count == 1
