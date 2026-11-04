"""De deur van de workflow-engine: een stilgezette klant start geen workflow en geen taak.

Klant 1 staat stil, klant 2 is actief. De engine is zonder database opgebouwd (`__new__`): alleen de
leesstap `_get_execution` en de dingen NA de deur zijn vervangen; de deur zelf draait echt.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.noodstop import guard
from src.core.noodstop.guard import MELDING_STIL, KlantStilgezet
from src.core.workflow.engine import ProductionWorkflowEngine
from src.core.workflow.models import TaskStatus, WorkflowStatus

STIL, ACTIEF = 1, 2


@pytest.fixture(autouse=True)
def _klant_1_staat_stil(monkeypatch: pytest.MonkeyPatch) -> None:
    async def lezer(tenant_id: int) -> bool:
        return tenant_id == STIL

    monkeypatch.setattr(guard, "_lees_stand", lezer)


def _engine(tenant_id: int) -> ProductionWorkflowEngine:
    engine = object.__new__(ProductionWorkflowEngine)
    uitvoering = SimpleNamespace(
        id=1,
        tenant_id=tenant_id,
        workflow=SimpleNamespace(workflow_id="w", version=1, spec_json={}),
        input_json={},
    )
    # De engine rolt in zijn foutpad terug via `self.db` (de legacy-sessie); zonder database is dat een
    # dubbelganger.
    engine._legacy_session = AsyncMock()  # type: ignore[assignment]
    engine._get_execution = AsyncMock(return_value=uitvoering)  # type: ignore[method-assign]
    engine._get_task = AsyncMock(side_effect=RuntimeError("DOORGELATEN"))  # type: ignore[method-assign]
    engine._parse_spec = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DOORGELATEN"))  # type: ignore[method-assign]
    engine._fail_execution = AsyncMock()  # type: ignore[method-assign]
    return engine


@pytest.mark.asyncio
async def test_een_workflow_van_de_stilgezette_klant_start_niet() -> None:
    engine = _engine(STIL)
    with pytest.raises(KlantStilgezet) as stop:
        await engine.execute_workflow("e-1")
    assert stop.value.bericht == MELDING_STIL
    # Gate 2 punt 4: een stop is geen mislukking. De uitvoering blijft `pending` en is te hervatten.
    engine._fail_execution.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_een_onleesbare_stand_laat_de_uitvoering_ook_niet_definitief_falen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def lezer(tenant_id: int) -> bool:
        raise ConnectionError("db weg")

    monkeypatch.setattr(guard, "_lees_stand", lezer)
    engine = _engine(ACTIEF)
    with pytest.raises(KlantStilgezet) as stop:
        await engine.execute_workflow("e-1")
    assert stop.value.onbekend
    engine._fail_execution.assert_not_awaited()  # type: ignore[attr-defined]


def _engine_midden_in_de_run(status: WorkflowStatus, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from src.core.workflow import engine as engine_module

    engine = _engine(ACTIEF)
    uitvoering = engine._get_execution.return_value
    uitvoering.status = status
    spec = SimpleNamespace(
        # De engine weigert een workflow zonder stappen (ADR-036 OP-13); een stap is hier genoeg.
        tasks={"stap": {"type": "llm"}},
        to_nodes_and_edges=lambda: ([], []),
        dependencies={},
        max_retries=0,
        retry_backoff_seconds=0,
        timeout_seconds=60,
    )
    engine._parse_spec = lambda *a, **k: spec  # type: ignore[method-assign]
    monkeypatch.setattr(engine_module, "validate_topology", lambda n, e: None)
    monkeypatch.setattr(engine_module, "topological_sort", lambda n, e: ["stap"])
    engine._update_execution_status = AsyncMock()  # type: ignore[method-assign]
    engine._initialize_tasks = AsyncMock()  # type: ignore[method-assign]
    engine._get_task = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(status=TaskStatus.PENDING, result_json=None)
    )
    engine._check_dependencies = AsyncMock(return_value=True)  # type: ignore[method-assign]
    engine._complete_execution = AsyncMock()  # type: ignore[method-assign]
    return engine


@pytest.mark.asyncio
async def test_een_stop_midden_in_de_run_laat_de_uitvoering_niet_definitief_falen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine_midden_in_de_run(WorkflowStatus.PENDING, monkeypatch)
    engine._execute_task_with_retry = AsyncMock(  # type: ignore[method-assign]
        side_effect=KlantStilgezet(MELDING_STIL)
    )
    with pytest.raises(KlantStilgezet):
        await engine.execute_workflow("e-1")
    engine._fail_execution.assert_not_awaited()  # type: ignore[attr-defined]
    engine._complete_execution.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_een_hervatte_run_zet_een_lopende_uitvoering_niet_nogmaals_op_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine_midden_in_de_run(WorkflowStatus.RUNNING, monkeypatch)
    engine._execute_task_with_retry = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(output={"ok": True})
    )
    await engine.execute_workflow("e-1")
    for aanroep in engine._update_execution_status.await_args_list:  # type: ignore[attr-defined]
        assert aanroep.args[1] != WorkflowStatus.RUNNING
    engine._complete_execution.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_een_verse_run_zet_de_uitvoering_wel_op_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine_midden_in_de_run(WorkflowStatus.PENDING, monkeypatch)
    engine._execute_task_with_retry = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(output={"ok": True})
    )
    await engine.execute_workflow("e-1")
    assert engine._update_execution_status.await_args_list[0].args[1] == WorkflowStatus.RUNNING  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_een_workflow_van_een_andere_klant_komt_voorbij_de_deur() -> None:
    engine = _engine(ACTIEF)
    with pytest.raises(RuntimeError, match="DOORGELATEN"):
        await engine.execute_workflow("e-1")


@pytest.mark.asyncio
async def test_een_taak_van_de_stilgezette_klant_start_niet() -> None:
    engine = _engine(STIL)
    with pytest.raises(KlantStilgezet):
        await engine.execute_task("e-1", "stap")
    engine._get_task.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_een_taak_van_een_andere_klant_komt_voorbij_de_deur() -> None:
    engine = _engine(ACTIEF)
    with pytest.raises(RuntimeError, match="DOORGELATEN"):
        await engine.execute_task("e-1", "stap")
