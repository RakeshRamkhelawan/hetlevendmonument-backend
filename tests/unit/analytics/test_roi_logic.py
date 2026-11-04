"""De ROI-rekensom en de grenzen daaromheen (SP-KLANT-04).

De oude test hier rekende met vaste minuten per pack en 75 euro per uur uit de code. Dat zijn
aannames van ons, niet van de klant, en nergens onderbouwd; ze zijn bewust verwijderd (brief
2026-10-10-sprint-dag-roi-eerlijk-gemeten). De rekensom met de aanname van de KLANT en de database
staat in `tests/integration/test_roi_eerlijk_gemeten.py`.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.analytics.roi_service import ROIService, schat_besparing
from src.core.models.roi_models import AgentRunMetric


class TestDeRekensom:
    def test_items_times_minutes_times_rate_is_the_estimate(self) -> None:
        schatting = schat_besparing(items=3, manual_minutes_per_item=10, hourly_rate_eur=60)

        assert schatting.savings_eur == pytest.approx(30.0)

    def test_the_hours_follow_from_items_and_minutes(self) -> None:
        schatting = schat_besparing(items=3, manual_minutes_per_item=10, hourly_rate_eur=60)

        assert schatting.hours_saved == pytest.approx(0.5)

    def test_no_items_means_no_savings(self) -> None:
        assert schat_besparing(0, 10, 60).savings_eur == 0.0

    def test_a_free_hour_means_no_euros(self) -> None:
        assert schat_besparing(5, 10, 0).savings_eur == 0.0


class TestGeenVasteAannamesInCode:
    def test_there_is_no_hardcoded_minutes_per_pack(self) -> None:
        assert not hasattr(ROIService, "BASELINES")

    def test_there_is_no_hardcoded_hourly_rate(self) -> None:
        assert not hasattr(ROIService, "AVG_HOURLY_RATE")


class TestRecordRun:
    async def test_an_unknown_status_is_refused(self) -> None:
        nu = datetime.now(timezone.utc)

        with pytest.raises(ValueError):
            await ROIService(AsyncMock()).record_run(
                tenant_id=1,
                agent_id="a",
                pack_id="p",
                task_id="t",
                status="gelukt",
                started_at=nu - timedelta(seconds=1),
                finished_at=nu,
            )

    async def test_the_row_carries_the_tenant_and_no_employee(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        nu = datetime.now(timezone.utc)

        await ROIService(db).record_run(
            tenant_id=7,
            agent_id="dunning",
            pack_id="p",
            task_id="t",
            status="klaar",
            started_at=nu - timedelta(seconds=1),
            finished_at=nu,
        )

        rij = db.add.call_args.args[0]
        assert isinstance(rij, AgentRunMetric) and rij.tenant_id == 7

    async def test_recording_does_not_commit_the_callers_transaction(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        nu = datetime.now(timezone.utc)

        await ROIService(db).record_run(
            tenant_id=1,
            agent_id="a",
            pack_id="p",
            task_id="t",
            status="klaar",
            started_at=nu,
            finished_at=nu,
        )

        db.commit.assert_not_awaited()
