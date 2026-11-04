"""Rendementscijfers (ROI) eerlijk gemeten (SP-KLANT-04, brief 2026-10-10-sprint-dag-roi-eerlijk-gemeten).

Wat deze test over de ECHTE app en de ECHTE database vaststelt:

1. De route `/api/v1/analytics/roi` bestaat in de app (hij werd overschaduwd door een pakket).
2. Een geslaagde pack-stap legt een rij vast in `agent_run_metrics`, met de juiste tenant en
   zonder enig medewerkersveld.
3. Zonder aanname van de klant toont het antwoord GEEN euro's; met aanname is het bedrag
   items x minuten x uurtarief. De aanname is zichtbaar in het antwoord.
4. Alleen wie `packs:manage` heeft stelt een aanname in.
5. Tenant A ziet geen runs van tenant B.

Wat NIET gemeten is: een draaiende applicatie met scherm (de acceptant doet dat), en RLS zelf (de
testdatabase komt uit `create_all`, waar RLS uit staat; zie de migratie-docstring).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from tests.integration.test_goedkeuren_is_een_procesbevoegdheid import (  # noqa: F401
    AANVRAGER,
    COLLEGA,
    TENANT,
    _sql,
    _zet_rollen,
    rollen_hersteld,
)
from tests.integration.test_laatste_beheerder import _aanroep, _token_van

ANDERE_TENANT = 2
PACK = "mkb.zero_admin"
AANNAME = {"manual_minutes_per_item": 10, "hourly_rate_eur": 60}


@pytest_asyncio.fixture
async def schone_roi_tabellen() -> AsyncGenerator[None, None]:
    """Begin en eindig met lege ROI-tabellen voor de twee testtenants."""
    for tabel in ("agent_run_metrics", "roi_assumptions"):
        await _sql(f"DELETE FROM {tabel} WHERE tenant_id IN (:a, :b)", a=TENANT, b=ANDERE_TENANT)
    yield
    for tabel in ("agent_run_metrics", "roi_assumptions"):
        await _sql(f"DELETE FROM {tabel} WHERE tenant_id IN (:a, :b)", a=TENANT, b=ANDERE_TENANT)


async def _registreer(
    tenant_id: int,
    *,
    status: str = "klaar",
    items: int | None = None,
    pack_id: str = PACK,
    task_id: str = "t-1",
) -> None:
    from datetime import datetime, timedelta, timezone

    from src.core.analytics.roi_service import ROIService
    from src.core.database.database import db_manager

    klaar = datetime.now(timezone.utc)
    async with db_manager.get_session() as db:
        await ROIService(db).record_run(
            tenant_id=tenant_id,
            agent_id="dunning",
            pack_id=pack_id,
            task_id=task_id,
            status=status,
            started_at=klaar - timedelta(seconds=30),
            finished_at=klaar,
            items_processed=items,
        )
        await db.commit()


async def _stel_aanname_in(app: Any, user_id: int = AANVRAGER) -> Any:
    return await _aanroep(
        app,
        await _token_van(user_id),
        "PUT",
        f"/api/v1/analytics/roi/assumptions/{PACK}",
        AANNAME,
    )


async def _roi(app: Any, user_id: int = AANVRAGER) -> Any:
    return await _aanroep(app, await _token_van(user_id), "GET", "/api/v1/analytics/roi")


def _pack(antwoord: Any, pack_id: str = PACK) -> dict[str, Any]:
    return next(p for p in antwoord.json()["packs"] if p["pack_id"] == pack_id)


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeRouteBestaat:
    async def test_the_roi_route_is_in_the_app(self, integration_app: Any) -> None:
        paden = {getattr(r, "path", "") for r in integration_app.routes}

        assert "/api/v1/analytics/roi" in paden

    async def test_the_roi_route_answers_for_a_tenant_without_runs(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        antwoord = await _roi(integration_app)

        assert antwoord.status_code == 200, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenPackRunLegtEenRijVast:
    async def test_a_successful_pack_step_writes_a_row_for_the_right_tenant(
        self, schone_roi_tabellen: None
    ) -> None:
        from src.core.als.enterprise.packs import DomainPackOrchestrator, WorkflowStep
        from src.core.shared.interfaces import ExecutionResult, ExecutionStatusContract

        orchestrator = DomainPackOrchestrator()
        gelukt = ExecutionResult(
            task_id="task-geslaagd",
            success=True,
            tenant_id=TENANT,
            agent_id="dunning",
            status=ExecutionStatusContract.KLAAR,
        )
        with patch.object(orchestrator, "_execute_step", AsyncMock(return_value=gelukt)):
            await orchestrator._run_single_step(
                WorkflowStep(agent_id="dunning", sla_seconds=30), TENANT, PACK
            )

        rijen = (
            await _sql(
                "SELECT tenant_id, pack_id, agent_id, task_id, status FROM agent_run_metrics "
                "WHERE task_id = 'task-geslaagd'"
            )
        ).all()
        assert [tuple(r) for r in rijen] == [(TENANT, PACK, "dunning", "task-geslaagd", "klaar")]

    async def test_a_failed_pack_step_is_recorded_as_mislukt(
        self, schone_roi_tabellen: None
    ) -> None:
        from src.core.als.enterprise.packs import DomainPackOrchestrator, WorkflowStep

        orchestrator = DomainPackOrchestrator()
        with patch.object(
            orchestrator, "_execute_step", AsyncMock(side_effect=RuntimeError("stuk"))
        ):
            await orchestrator._run_single_step(
                WorkflowStep(agent_id="dunning", sla_seconds=30), TENANT, PACK
            )

        statussen = (
            await _sql("SELECT status FROM agent_run_metrics WHERE tenant_id = :t", t=TENANT)
        ).all()
        assert [r[0] for r in statussen] == ["mislukt"]

    async def test_a_step_that_exceeds_its_sla_is_recorded_as_mislukt(
        self, schone_roi_tabellen: None
    ) -> None:
        import asyncio

        from src.core.als.enterprise.packs import DomainPackOrchestrator, WorkflowStep

        async def _te_traag(*_args: Any, **_kwargs: Any) -> None:
            await asyncio.sleep(2)

        orchestrator = DomainPackOrchestrator()
        with patch.object(orchestrator, "_execute_step", _te_traag):
            await orchestrator._run_single_step(
                WorkflowStep(agent_id="dunning", sla_seconds=0.05), TENANT, PACK
            )

        rijen = (
            await _sql("SELECT status, task_id FROM agent_run_metrics WHERE tenant_id = :t", t=TENANT)
        ).all()
        assert [tuple(r) for r in rijen] == [("mislukt", "timeout")]

    async def test_the_measurement_adopts_the_tenant_in_its_own_session(
        self, schone_roi_tabellen: None
    ) -> None:
        """Onder de applicatierol met RLS weigert de database een INSERT zonder tenantcontext."""
        from contextlib import asynccontextmanager

        from src.core.als.enterprise.packs import DomainPackOrchestrator

        gezien: list[int] = []

        @asynccontextmanager
        async def _spion(db: Any, tenant_id: int) -> AsyncGenerator[None, None]:
            gezien.append(tenant_id)
            yield

        with patch("src.core.database.bypass_session.adopt_tenant", _spion):
            await DomainPackOrchestrator()._leg_run_vast(
                tenant_id=TENANT,
                pack_id=PACK,
                agent_id="dunning",
                task_id="t-adopt",
                status="klaar",
                gestart_op=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            )

        assert gezien == [TENANT]

    async def test_the_table_has_no_employee_column(self) -> None:
        kolommen = {
            r[0]
            for r in (
                await _sql(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'agent_run_metrics'"
                )
            ).all()
        }

        assert kolommen, "de tabel agent_run_metrics bestaat niet"
        assert not kolommen & {"user_id", "initiated_by_user_id", "email", "department"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestGemetenEnGeschat:
    async def test_without_an_assumption_there_are_no_euros(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        await _registreer(TENANT, items=3)

        pack = _pack(await _roi(integration_app))

        assert pack["estimated"] is None

    async def test_without_an_assumption_the_measured_layer_is_still_shown(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        await _registreer(TENANT, items=3)

        pack = _pack(await _roi(integration_app))

        assert (pack["runs"], pack["succeeded"], pack["items_processed"]) == (1, 1, 3)

    async def test_with_an_assumption_the_euros_are_items_times_minutes_times_rate(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        await _registreer(TENANT, items=3)
        await _stel_aanname_in(integration_app)

        pack = _pack(await _roi(integration_app))

        assert pack["estimated"]["savings_eur"] == pytest.approx(30.0)

    async def test_the_assumption_is_visible_next_to_the_estimate(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        await _registreer(TENANT, items=3)
        await _stel_aanname_in(integration_app)

        aanname = _pack(await _roi(integration_app))["assumption"]

        assert (aanname["manual_minutes_per_item"], aanname["hourly_rate_eur"]) == (10, 60)

    async def test_a_failed_run_does_not_count_as_savings(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        await _registreer(TENANT, items=3, task_id="goed")
        await _registreer(TENANT, status="mislukt", items=5, task_id="stuk")
        await _stel_aanname_in(integration_app)

        pack = _pack(await _roi(integration_app))

        assert (pack["runs"], pack["succeeded"]) == (2, 1)
        assert pack["estimated"]["savings_eur"] == pytest.approx(30.0)

    async def test_a_run_without_a_measured_item_count_counts_as_one_item(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        await _registreer(TENANT, items=None)
        await _stel_aanname_in(integration_app)

        pack = _pack(await _roi(integration_app))

        assert pack["estimated"]["savings_eur"] == pytest.approx(10.0)

    async def test_there_is_no_breakdown_per_department_or_person(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        await _registreer(TENANT, items=3)

        antwoord = await _roi(integration_app)

        assert "byDepartment" not in antwoord.text and "by_department" not in antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestGelijktijdigeAannames:
    async def test_two_simultaneous_assumptions_for_the_same_pack_both_succeed_with_one_row(
        self, schone_roi_tabellen: None
    ) -> None:
        import asyncio

        from src.core.analytics.roi_service import ROIService
        from src.core.database.database import db_manager

        async def _zet(minuten: float) -> None:
            async with db_manager.get_session() as db:
                await ROIService(db).set_assumption(TENANT, PACK, minuten, 60)
                await db.commit()

        await asyncio.gather(_zet(10), _zet(20))

        rijen = (await _sql("SELECT count(*) FROM roi_assumptions WHERE tenant_id = :t", t=TENANT)).all()
        assert rijen[0][0] == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestWieDeAannameInstelt:
    async def test_a_user_without_packs_manage_gets_403(
        self, schone_roi_tabellen: None, integration_app: Any, rollen_hersteld: None
    ) -> None:
        await _zet_rollen(COLLEGA, ["user"])

        antwoord = await _stel_aanname_in(integration_app, COLLEGA)

        assert antwoord.status_code == 403, antwoord.text

    @pytest.mark.parametrize(
        "body",
        [
            {"manual_minutes_per_item": 0, "hourly_rate_eur": 60},
            {"manual_minutes_per_item": 10, "hourly_rate_eur": -1},
            {"manual_minutes_per_item": 10},
        ],
    )
    async def test_a_nonsense_assumption_is_refused(
        self, schone_roi_tabellen: None, integration_app: Any, body: dict[str, Any]
    ) -> None:
        antwoord = await _aanroep(
            integration_app,
            await _token_van(AANVRAGER),
            "PUT",
            f"/api/v1/analytics/roi/assumptions/{PACK}",
            body,
        )

        assert antwoord.status_code == 422, antwoord.text

    async def test_the_tenant_cannot_be_chosen_in_the_body(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        await _aanroep(
            integration_app,
            await _token_van(AANVRAGER),
            "PUT",
            f"/api/v1/analytics/roi/assumptions/{PACK}",
            {**AANNAME, "tenant_id": ANDERE_TENANT},
        )

        tenants = (await _sql("SELECT tenant_id FROM roi_assumptions")).all()
        assert {r[0] for r in tenants} == {TENANT}


@pytest.mark.integration
@pytest.mark.asyncio
class TestTenantIsolatie:
    async def test_tenant_a_does_not_see_the_runs_of_tenant_b(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        await _registreer(ANDERE_TENANT, items=50, task_id="van-b")

        antwoord = await _roi(integration_app)

        assert antwoord.json()["packs"] == []

    async def test_the_counts_of_tenant_a_exclude_tenant_b(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        await _registreer(TENANT, items=3, task_id="van-a")
        await _registreer(ANDERE_TENANT, items=50, task_id="van-b")

        pack = _pack(await _roi(integration_app))

        assert (pack["runs"], pack["items_processed"]) == (1, 3)

    async def test_the_assumption_of_tenant_b_is_not_used_for_tenant_a(
        self, schone_roi_tabellen: None, integration_app: Any
    ) -> None:
        await _registreer(TENANT, items=3)
        await _sql(
            "INSERT INTO roi_assumptions (tenant_id, pack_id, manual_minutes_per_item, "
            "hourly_rate_eur, source) VALUES (:t, :p, 999, 999, 'klant_ingevuld')",
            t=ANDERE_TENANT,
            p=PACK,
        )

        pack = _pack(await _roi(integration_app))

        assert pack["assumption"] is None
