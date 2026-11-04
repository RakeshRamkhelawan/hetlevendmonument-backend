"""De deuren weigeren een stilgezette klant: actor, brievenverzender en proactieve scheduler.

Klant 1 staat stil, klant 2 is actief. Alleen de lezer van de stand en de dingen NA de deur zijn
vervangen; de deur zelf draait echt.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.noodstop import guard
from src.core.noodstop.guard import MELDING_STIL

STIL, ACTIEF = 1, 2


@pytest.fixture(autouse=True)
def _klant_1_staat_stil(monkeypatch: pytest.MonkeyPatch) -> None:
    async def lezer(tenant_id: int) -> bool:
        return tenant_id == STIL

    monkeypatch.setattr(guard, "_lees_stand", lezer)


def _draai_actor(monkeypatch: pytest.MonkeyPatch, tenant_id: int) -> tuple[dict, MagicMock]:
    import asyncio

    from src.core.tasks import workflow_tasks

    agent = MagicMock()
    agent.process_task = AsyncMock(return_value=MagicMock(model_dump=lambda: {"success": True}))
    monkeypatch.setattr(workflow_tasks, "AutonomousAgent", lambda: agent)
    monkeypatch.setattr(workflow_tasks, "TaskData", lambda **kw: MagicMock())
    monkeypatch.setattr(
        workflow_tasks, "draai_in_eigen_loop", lambda f: asyncio.run(f(MagicMock()))
    )
    uitslag = workflow_tasks.execute_workflow_step.fn({"tenant_id": tenant_id, "task_id": "t"})
    return uitslag, agent


def test_actor_voert_geen_stap_uit_voor_de_stilgezette_klant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uitslag, agent = _draai_actor(monkeypatch, STIL)
    assert uitslag["success"] is False
    assert uitslag["error"] == MELDING_STIL
    assert uitslag["geweigerd_door"] == "noodstop"
    agent.process_task.assert_not_awaited()


def test_actor_voert_de_stap_van_een_andere_klant_wel_uit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uitslag, agent = _draai_actor(monkeypatch, ACTIEF)
    assert uitslag == {"success": True}
    agent.process_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_brievenverzender_slaat_de_stilgezette_klant_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.tasks import debiteuren_tasks as dt

    verwerkt: list[int] = []

    async def kandidaten(sessie: object) -> list[tuple[int, int, int]]:
        return [(10, STIL, 0), (20, ACTIEF, 0)]

    async def verwerk(sessie: object, bericht_id: int, tenant_id: int, pogingen: int) -> None:
        verwerkt.append(tenant_id)
        return None

    @asynccontextmanager
    async def fabriek():
        yield MagicMock()

    monkeypatch.setattr(dt, "_kandidaten", kandidaten)
    monkeypatch.setattr(dt, "_verwerk", verwerk)
    await dt.verstuur_klare_berichten_async(sessie_fabriek=fabriek)
    assert verwerkt == [ACTIEF]


@pytest.mark.asyncio
async def test_scheduler_slaat_de_stilgezette_klant_over() -> None:
    from src.core.copilot.proactive.scheduler import ProactiveScheduler

    monitor = MagicMock()
    monitor.name = "m"
    monitor.interval_seconds = 60
    monitor.detect = AsyncMock(return_value=[])
    repo = MagicMock()
    repo.list_active_ids = AsyncMock(return_value=[STIL, ACTIEF])
    planner = ProactiveScheduler(scheduler=MagicMock(), tenant_repo=repo, monitors=[monitor])
    await planner._run_for_all_tenants(monitor)
    assert [c.args[0] for c in monitor.detect.await_args_list] == [ACTIEF]
