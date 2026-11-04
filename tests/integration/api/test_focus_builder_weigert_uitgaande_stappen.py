"""De focus-builder weigert een uitgaande stap bij opslaan, publiceren en uitvoeren (wfb-dag1 stap 1).

Zelfde metingen en opstelling als
tests/unit/api/v1/activepieces/test_flowroutes_weigeren_uitgaande_stappen.py, maar op Postgres:
de tabel `flows` heeft JSONB-kolommen en draait niet op de SQLite van de unittests. De
focus-builderdienst slaat eerst lokaal op en slikt daarna elke fout van ActivePieces; daarom
wordt hier ook gemeten dat er bij een weigering NIETS is bewaard.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.unit.api.v1.activepieces.test_flowroutes_weigeren_uitgaande_stappen import (
    VERBODEN,
    _graaf,
    _overschrijf_rolcontrole,
    ap,  # noqa: F401 - fixture
)

@pytest_asyncio.fixture
async def focus(
    postgres_session: AsyncSession, ap: Any  # noqa: F811
) -> AsyncGenerator[AsyncClient, None]:
    from src.core.api.v1.focus_builder.dependencies import get_focus_builder_council
    from src.core.api.v1.focus_builder.router import router as focus_router
    from src.core.api.v1.focus_builder.shared import get_focus_builder_service
    from src.core.auth.api_deps import get_current_user_dependency
    from src.core.api.v1.focus_builder.dependencies import DecisionVerdict
    from src.domains.flows.service import FocusBuilderService

    class _Council:
        async def deliberate(self, _voorstel: object) -> SimpleNamespace:
            return SimpleNamespace(verdict=DecisionVerdict.APPROVED)

    app = FastAPI()
    app.include_router(focus_router, prefix="/api/v1")
    app.dependency_overrides[get_focus_builder_service] = lambda: FocusBuilderService(
        db=postgres_session, tenant_id=1
    )
    app.dependency_overrides[get_current_user_dependency] = lambda: SimpleNamespace(
        id=1, tenant_id=1, email="beheer@test.example", roles=["admin"]
    )
    app.dependency_overrides[get_focus_builder_council] = lambda: _Council()
    _overschrijf_rolcontrole(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _aantal_flows(db: AsyncSession) -> int:
    from src.domains.flows.models import Flow

    return int((await db.execute(select(func.count(Flow.id)))).scalar_one())


async def _bewaarde_flow(db: AsyncSession, agent: str, *, ap_id: str | None = None) -> int:
    """Een flow die al in de database staat (van voor deze controle)."""
    from src.domains.flows.models import Flow

    rij = Flow(
        tenant_id=1,
        name="Oud",
        react_flow_graph=_graaf(agent),
        activepieces_flow_id=ap_id,
        is_published=False,
    )
    db.add(rij)
    await db.commit()
    return rij.id


@pytest.mark.integration
@pytest.mark.asyncio
class TestFocusBuilderRoutes:
    @pytest.mark.parametrize("agent", VERBODEN)
    async def test_opslaan_met_een_verboden_stap_geeft_422_en_bewaart_niets(
        self, focus: AsyncClient, postgres_session: AsyncSession, agent: str
    ) -> None:
        antwoord = await focus.post(
            "/api/v1/focus-builder/flows", json={"name": "x", "react_flow_graph": _graaf(agent)}
        )

        assert (antwoord.status_code, await _aantal_flows(postgres_session)) == (422, 0), antwoord.text

    async def test_wijzigen_naar_een_mailstap_geeft_422(
        self, focus: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        flow_id = await _bewaarde_flow(postgres_session, "data_transformer")

        antwoord = await focus.put(
            f"/api/v1/focus-builder/flows/{flow_id}", json={"react_flow_graph": _graaf("email")}
        )

        assert antwoord.status_code == 422, antwoord.text

    async def test_publiceren_van_een_oude_flow_met_een_mailstap_geeft_422(
        self, focus: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        flow_id = await _bewaarde_flow(postgres_session, "email")

        antwoord = await focus.put(
            f"/api/v1/focus-builder/flows/{flow_id}", json={"is_published": True}
        )

        assert antwoord.status_code == 422, antwoord.text

    async def test_uitvoeren_van_een_oude_flow_met_een_mailstap_geeft_422(
        self, focus: AsyncClient, postgres_session: AsyncSession, ap: Any  # noqa: F811
    ) -> None:
        flow_id = await _bewaarde_flow(postgres_session, "email", ap_id="flow-1")
        starten = ap.post("/flows/flow-1/runs").mock(return_value=Response(201, json={"id": "r"}))

        antwoord = await focus.post(f"/api/v1/focus-builder/flows/{flow_id}/execute", json={})

        assert (antwoord.status_code, starten.called) == (422, False), antwoord.text


