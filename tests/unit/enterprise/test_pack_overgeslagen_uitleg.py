"""De uitleg bij een overgeslagen stap noemt geen technische agentnaam (pakketten nazorg, punt 4).

`run_pack` zette in de reden van elke overgeslagen stap `step.agent_id` ("Overgeslagen: de stap
dunning is mislukt"). Een klant leest `dunning` of `skillsgaptraining` niet als een stap van zijn
pakket. De reden noemt nu het volgnummer van de mislukte stap; de agent staat wel in het logboek.

De uitvoering van een stap (`_execute_step`) is op de grens vervangen; er is geen database of LLM.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.als.enterprise.packs import DomainPack, DomainPackOrchestrator, WorkflowStep
from src.core.shared.interfaces import ExecutionResult
from src.core.types import ExecutionStatusContract


def _pack() -> DomainPack:
    return DomainPack(
        pack_id="test.uitleg",
        name="Uitleg",
        steps=[
            WorkflowStep(agent_id="eerste_agent", mode="sequential"),
            WorkflowStep(agent_id="tweede_agent", mode="sequential"),
            WorkflowStep(agent_id="derde_agent", mode="sequential"),
        ],
    )


@pytest.fixture
def eerste_stap_faalt(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stap(
        self: Any,
        agent_id: str,
        tenant_id: int,
        params: dict[str, Any],
        *,
        initiated_by_user_id: int | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            task_id="error",
            success=False,
            error_message="stuk",
            tenant_id=tenant_id,
            agent_id=agent_id,
            status=ExecutionStatusContract.MISLUKT,
        )

    async def _geen_meting(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", _stap)
    monkeypatch.setattr(DomainPackOrchestrator, "_leg_run_vast", _geen_meting)


class TestUitlegBijOvergeslagenStappen:
    async def test_de_uitleg_bevat_geen_agent_id(self, eerste_stap_faalt: None) -> None:
        resultaten = await DomainPackOrchestrator().run_pack(_pack(), 1)

        overgeslagen = [r for r in resultaten if r.task_id == "skipped"]
        assert len(overgeslagen) == 2
        for r in overgeslagen:
            assert "eerste_agent" not in (r.error_message or ""), r.error_message

    async def test_de_uitleg_noemt_het_volgnummer_van_de_mislukte_stap(
        self, eerste_stap_faalt: None
    ) -> None:
        resultaten = await DomainPackOrchestrator().run_pack(_pack(), 1)

        overgeslagen = [r for r in resultaten if r.task_id == "skipped"]
        assert {r.error_message for r in overgeslagen} == {"Overgeslagen: stap 1 is mislukt"}

    async def test_de_mislukte_stap_zelf_blijft_herkenbaar_aan_zijn_agent(
        self, eerste_stap_faalt: None
    ) -> None:
        resultaten = await DomainPackOrchestrator().run_pack(_pack(), 1)

        assert resultaten[0].agent_id == "eerste_agent"
