"""De uitvoeringsstatus levert per stap een Nederlandse regel (agentstap dag 2, Keten G, "uitkomst terugkijken").

De stappen komen uit de taakrijen van DEZE uitvoering en DEZE klant: de zoekopdracht filtert op tenant en uitvoering.

Mutatiebewijs (2026-10-25): zie de eindmelding van de sessie.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.api.v1.workflow import workflow_execution_core_router as router


def _resultaat(rijen: list[object]) -> MagicMock:
    antwoord = MagicMock()
    antwoord.scalars.return_value.first.return_value = rijen[0] if rijen else None
    antwoord.scalars.return_value.all.return_value = rijen
    return antwoord


def _uitvoering() -> SimpleNamespace:
    return SimpleNamespace(
        id="uit-1",
        execution_id="uit-1",
        workflow_id=7,
        tenant_id=5,
        status=SimpleNamespace(value="failed"),
        input_json={},
        output_json=None,
        started_at=None,
        finished_at=None,
        tasks_completed=0,
        tasks_failed=1,
        tasks_total=1,
        error_message="stap mislukt",
    )


def _taak() -> SimpleNamespace:
    return SimpleNamespace(
        task_ref="n1",
        task_type="agent",
        status=SimpleNamespace(value="failed"),
        result_json=None,
        error_json={"type": "StapMislukt", "message": "u mag deze agent niet starten"},
        created_at=None,
    )


@pytest.mark.asyncio
async def test_de_status_bevat_een_nederlandse_regel_per_stap() -> None:
    db = AsyncMock()
    db.execute.side_effect = [
        _resultaat([_uitvoering()]),
        _resultaat([SimpleNamespace(workflow_id="wf-1")]),
        _resultaat([_taak()]),
    ]

    antwoord = await router.get_execution_status("uit-1", db=db, tenant_id=5, _=1)

    assert antwoord.stappen[0]["reden"] == "u mag deze agent niet starten"
    assert antwoord.stappen[0]["status"] == "Mislukt"


@pytest.mark.asyncio
async def test_de_zoekopdracht_voor_de_stappen_filtert_op_klant_en_uitvoering() -> None:
    db = AsyncMock()
    db.execute.side_effect = [
        _resultaat([_uitvoering()]),
        _resultaat([SimpleNamespace(workflow_id="wf-1")]),
        _resultaat([_taak()]),
    ]

    await router.get_execution_status("uit-1", db=db, tenant_id=5, _=1)

    zoekopdracht = str(db.execute.call_args_list[2].args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "c7_execution_tasks.tenant_id = 5" in zoekopdracht
    assert "c7_execution_tasks.execution_id = 'uit-1'" in zoekopdracht


@pytest.mark.asyncio
async def test_de_stapnaam_komt_uit_de_knopen_van_de_workflow() -> None:
    db = AsyncMock()
    taak = _taak()
    taak.task_ref = "node_1"
    db.execute.side_effect = [
        _resultaat([_uitvoering()]),
        _resultaat(
            [SimpleNamespace(workflow_id="wf-1", nodes=[{"id": "node_1", "name": "Klantvraag samenvatten"}])]
        ),
        _resultaat([taak]),
    ]

    antwoord = await router.get_execution_status("uit-1", db=db, tenant_id=5, _=1)

    assert antwoord.stappen[0]["naam"] == "Klantvraag samenvatten"


@pytest.mark.asyncio
async def test_een_workflow_zonder_knopen_geeft_geen_fout() -> None:
    db = AsyncMock()
    db.execute.side_effect = [
        _resultaat([_uitvoering()]),
        _resultaat([SimpleNamespace(workflow_id="wf-1", nodes=None)]),
        _resultaat([_taak()]),
    ]

    antwoord = await router.get_execution_status("uit-1", db=db, tenant_id=5, _=1)

    assert antwoord.stappen[0]["naam"] == "n1"
