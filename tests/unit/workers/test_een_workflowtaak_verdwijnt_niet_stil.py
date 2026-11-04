"""Een workflowtaak die niet bij de werker kan komen, geeft een zichtbare fout (ADR-036 OP-13).

Brief 2026-10-20 (ActivePieces per klant, dag 1), besluit 5.

**Wat er gebeurde.** `src/workers/workflow_worker.py` zet bij het importeren een `StubBroker` als
globale broker en wisselt pas om zodra `get_redis_broker()` wordt aangeroepen. Dat doet alleen het
werkerproces. De API-aanroepen `execute_workflow_task.send(...)` stuurden dus naar een
geheugenwachtrij die niemand uitleest: het antwoord was `202 pending` en de taak was weg. En als
het versturen WEL faalde, werd de fout alleen gelogd en kreeg de klant alsnog `202 pending` voor een
uitvoering die nooit zou starten.

**Wat deze tests bewaken.** Versturen gaat altijd via `verstuur_workflow_taak`: eerst de echte
broker binden, dan versturen; faalt dat, dan staat de uitvoering op FAILED met een reden, ligt er
een regel in de dead letter queue, en krijgt de aanroeper een Nederlandse fout (503) in plaats van
een 202.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.workflow.dead_letter_queue import DeadLetterEntry
from src.core.workflow.models import WorkflowStatus
from src.workers.workflow_verzending import (
    WorkflowTaakNietVerstuurdError,
    verstuur_workflow_taak,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ROUTERS = (
    "src/core/api/v1/workflow/workflow_execution_router.py",
    "src/core/api/v1/workflow/workflow_execution_core_router.py",
)


def _uitvoering() -> SimpleNamespace:
    return SimpleNamespace(
        execution_id="exec_abc123",
        workflow_id="wf-1",
        tenant_id=7,
        status=WorkflowStatus.PENDING,
        error_message=None,
        finished_at=None,
    )


def _db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    return db


@contextmanager
def _onbereikbare_broker() -> Iterator[None]:
    """Een onbereikbare Redis: de echte broker binden lukt, het versturen faalt."""
    from src.workers import workflow_worker

    with (
        patch.object(workflow_worker, "get_redis_broker"),
        patch.object(
            workflow_worker.execute_workflow_task, "send", side_effect=ConnectionError("redis weg")
        ),
    ):
        yield


@pytest.mark.asyncio
async def test_de_echte_broker_wordt_gebonden_voor_er_wordt_verstuurd() -> None:
    from src.workers import workflow_worker

    volgorde: list[str] = []
    with (
        patch.object(
            workflow_worker, "get_redis_broker", side_effect=lambda: volgorde.append("broker")
        ),
        patch.object(
            workflow_worker.execute_workflow_task,
            "send",
            side_effect=lambda *a, **k: volgorde.append("send"),
        ),
    ):
        await verstuur_workflow_taak(_db(), _uitvoering())

    assert volgorde == ["broker", "send"]


@pytest.mark.asyncio
async def test_de_klant_gaat_mee_met_de_opdracht() -> None:
    from src.workers import workflow_worker

    with (
        patch.object(workflow_worker, "get_redis_broker"),
        patch.object(workflow_worker.execute_workflow_task, "send") as send,
    ):
        await verstuur_workflow_taak(_db(), _uitvoering())

    send.assert_called_once_with("exec_abc123", 7)


@pytest.mark.asyncio
async def test_een_onbereikbare_broker_geeft_een_fout_en_geen_stille_202() -> None:
    with _onbereikbare_broker():
        with pytest.raises(WorkflowTaakNietVerstuurdError):
            await verstuur_workflow_taak(_db(), _uitvoering())


@pytest.mark.asyncio
async def test_een_mislukte_verzending_zet_de_uitvoering_op_failed_met_een_reden() -> None:
    uitvoering = _uitvoering()
    with _onbereikbare_broker():
        with pytest.raises(WorkflowTaakNietVerstuurdError):
            await verstuur_workflow_taak(_db(), uitvoering)

    assert uitvoering.status == WorkflowStatus.FAILED
    assert uitvoering.error_message


@pytest.mark.asyncio
async def test_een_mislukte_verzending_komt_in_de_dead_letter_queue() -> None:
    db = _db()
    with _onbereikbare_broker():
        with pytest.raises(WorkflowTaakNietVerstuurdError):
            await verstuur_workflow_taak(db, _uitvoering())

    toegevoegd = [c.args[0] for c in db.add.call_args_list]
    regels = [r for r in toegevoegd if isinstance(r, DeadLetterEntry)]
    assert [(r.execution_id, r.tenant_id) for r in regels] == [("exec_abc123", 7)]


@pytest.mark.asyncio
async def test_een_storing_in_de_dead_letter_queue_verbergt_de_echte_fout_niet() -> None:
    db = _db()
    db.add.side_effect = RuntimeError("database weg")
    with _onbereikbare_broker():
        with pytest.raises(WorkflowTaakNietVerstuurdError):
            await verstuur_workflow_taak(db, _uitvoering())


@pytest.mark.asyncio
async def test_de_foutmelding_is_nederlands_met_status_503() -> None:
    with _onbereikbare_broker():
        with pytest.raises(WorkflowTaakNietVerstuurdError) as fout:
            await verstuur_workflow_taak(_db(), _uitvoering())

    assert fout.value.status_code == 503
    assert "niet gestart" in fout.value.message.lower()


@pytest.mark.parametrize("router", ROUTERS)
def test_de_router_verstuurt_via_de_ene_verzendfunctie(router: str) -> None:
    boom = ast.parse((REPO_ROOT / router).read_text(encoding="utf-8"))

    rechtstreeks = [
        node.lineno
        for node in ast.walk(boom)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "send"
    ]
    verzendingen = [
        node.lineno
        for node in ast.walk(boom)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "verstuur_workflow_taak"
    ]

    assert not rechtstreeks and len(verzendingen) == 1, (
        f"{router}: rechtstreekse .send() op regel {rechtstreeks}; "
        f"aanroepen van verstuur_workflow_taak: {verzendingen}"
    )
