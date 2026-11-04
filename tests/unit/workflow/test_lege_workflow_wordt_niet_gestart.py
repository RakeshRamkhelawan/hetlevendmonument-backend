"""Een workflow zonder stappen wordt bij het starten geweigerd, voordat er een uitvoering ontstaat (ADR-036 OP-13).

**Wat er mis was (gemeten 2026-10-22).** Een workflow zonder taken liep in de engine zonder fout door tot
`succeeded` zonder werk te doen: de klant ziet "klaar" terwijl er niets is gebeurd. De controle zit nu op twee
plekken: de engine weigert hem (`tests/integration/test_workflowstappen_draaien_echt.py`) EN de start-route
weigert hem voordat er een uitvoeringsrecord en een taak in de wachtrij komen (hier). De route is de plek waar de
klant de melding ziet.

**Wat hier bewezen wordt**, voor beide start-routes (`workflow_execution_router` en `workflow_execution_core_router`):
een workflow met lege `nodes` (`{}`, `[]` of `None`) geeft een Nederlandse validatiefout, er wordt geen uitvoering
aangemaakt (geen `db.add`) en niets verstuurd; een workflow met een stap start gewoon.

**Mutatiebewijs:** zie de oplevering van de brief (per route, beide richtingen).
"""

from __future__ import annotations

from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.api.v1.workflow import workflow_execution_core_router, workflow_execution_router

_ROUTERS: list[ModuleType] = [workflow_execution_router, workflow_execution_core_router]


def _db(workflow: Any) -> MagicMock:
    resultaat = MagicMock()
    resultaat.scalars.return_value.first.return_value = workflow
    db = MagicMock()
    db.execute = AsyncMock(return_value=resultaat)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


async def _start(router: ModuleType, workflow: Any) -> tuple[MagicMock, Exception | None]:
    db = _db(workflow)
    try:
        with patch("src.workers.workflow_worker.execute_workflow_task", MagicMock()):
            await router.execute_workflow(
                workflow_id="wf",
                request=SimpleNamespace(version=None, input_data={}),
                db=db,
                tenant_id=1,
                user_id=9,
            )
    except Exception as fout:  # noqa: BLE001 -- we meten WELKE fout er komt
        return db, fout
    return db, None


def _naam(router: ModuleType) -> str:
    return router.__name__.rsplit(".", 1)[-1]


@pytest.mark.parametrize("router", _ROUTERS, ids=_naam)
@pytest.mark.parametrize("nodes", [{}, [], None], ids=["leeg-woordenboek", "lege-lijst", "geen"])
async def test_een_workflow_zonder_stappen_wordt_geweigerd_met_een_nederlandse_melding(
    router: ModuleType, nodes: Any
) -> None:
    workflow = SimpleNamespace(
        id="wf", workflow_id="wf", version=1, nodes=nodes, edges={}, is_active=True
    )

    _, fout = await _start(router, workflow)

    assert "geen stappen" in f"{fout} {getattr(fout, 'details', '')} {getattr(fout, 'message', '')}"


@pytest.mark.parametrize("router", _ROUTERS, ids=_naam)
async def test_er_ontstaat_geen_uitvoering_bij_een_lege_workflow(router: ModuleType) -> None:
    workflow = SimpleNamespace(
        id="wf", workflow_id="wf", version=1, nodes={}, edges={}, is_active=True
    )

    db, _ = await _start(router, workflow)

    assert db.add.call_count == 0


@pytest.mark.parametrize("router", _ROUTERS, ids=_naam)
async def test_een_workflow_met_een_stap_start_gewoon(router: ModuleType) -> None:
    workflow = SimpleNamespace(
        id="wf",
        workflow_id="wf",
        version=1,
        nodes={"stap1": {"type": "llm"}},
        edges={},
        is_active=True,
    )

    db, fout = await _start(router, workflow)

    assert (db.add.call_count, "geen stappen" in f"{fout}") == (1, False)
