"""Een workflowstap doet zijn werk en de klant ziet de uitkomst (ADR-036 OP-13, brief 2026-10-22).

Echte engine, echte Postgres uit de migratieketen; de taalmodel- en toolstap zijn nep, want de eigen tests van de
echte providers staan in `tests/unit/workflow/test_workflowstappen_via_de_deuren.py`.

**Wat hier bewezen wordt.**
1. Na een run staan `started_at`, `finished_at` en de tellers op de uitvoering en `finished_at` op de taak (de engine
   schreef `completed_at`, een kolom die niet bestaat, waardoor de statuspagina leeg bleef).
2. Na een mislukte run staat de reden in `error_message` van de uitvoering en in `error_json` van de taak.
3. Een toolstap met `success: False` laat de uitvoering op `failed` eindigen, niet op `succeeded`.
4. De taalmodelstap krijgt de klant van de UITVOERING mee (de modelkeuze van de klant geldt).
5. Een lege workflow wordt geweigerd met een Nederlandse reden.
6. `_initialize_tasks` maakt bij een herstart geen dubbele taken.

**Mutatiebewijs:** zie de oplevering van de brief (per element, beide richtingen).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from psycopg2.extensions import connection as PgConnection
from sqlalchemy import func, select
from tests.integration.test_workflow_loopt_echt_tot_het_eind import (  # noqa: F401 -- fixtures en hulpfuncties
    Wereld,
    _workersessie,
    db,
    wereld,
)

from src.core.middleware.tenant_context import set_tenant_id
from src.core.workflow.engine import ProductionWorkflowEngine
from src.core.workflow.models import C7ExecutionTask
from src.core.workflow.providers import FakeAgentRuntime, FakeLLMProvider, FakeToolBroker
from src.core.workflow.state_machine import WorkflowStateMachine

_NODES_EEN_LLMSTAP = '{"stap1": {"type": "llm", "prompt": "Zeg hallo"}}'
_NODES_EEN_TOOLSTAP = '{"stap1": {"type": "tool", "tool_name": "list_tasks", "parameters": {}}}'


class _OpnemendLLM(FakeLLMProvider):
    """Een nepmodel dat onthoudt met welke klant hij werd aangeroepen."""

    def __init__(self) -> None:
        super().__init__()
        self.aanroepen: list[dict[str, Any]] = []

    async def generate(self, prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        self.aanroepen.append(kwargs)
        return await super().generate(prompt, model, **kwargs)


class _KapotLLM(FakeLLMProvider):
    async def generate(self, prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        raise RuntimeError("model weg")


class _WeigerendeTools(FakeToolBroker):
    async def execute_tool(  # type: ignore[override]
        self,
        tool_name: str,
        parameters: dict[str, Any],
        timeout: int = 60,
        tenant_id: int | None = None,
        starter: str | None = None,
    ) -> dict[str, Any]:
        # `starter`: de engine geeft de starter van de uitvoering mee sinds f9e1f3af (2026-10-22), net als bij
        # `FakeToolBroker`. Zonder deze parameter gaf het testdubbel een TypeError in plaats van success=False.
        return {
            "success": False,
            "result": None,
            "error": "geen toestemming",
            "execution_time": 0.0,
        }


def _maak(db: PgConnection, klant: int, nodes: str, edges: str = "{}") -> str:
    achtervoegsel = uuid.uuid4().hex[:8]
    workflow = f"wf_stappen_{achtervoegsel}"
    uitvoering = f"exec_stappen_{achtervoegsel}"
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO c7_workflows (id, name, workflow_type, trigger_type, tenant_id, nodes, edges) "
            "VALUES (%s, 'Stappen', 'test', 'manual', %s, %s, %s)",
            (workflow, klant, nodes, edges),
        )
        cur.execute(
            "INSERT INTO c7_workflow_executions (id, execution_id, workflow_id, tenant_id, input_json) "
            "VALUES (%s, %s, %s, %s, '{}')",
            (f"id_{uitvoering}", uitvoering, workflow, klant),
        )
    return uitvoering


async def _voer_uit(
    uitvoering: str, klant: int, llm: Any = None, tools: Any = None
) -> BaseException | None:
    """Laat de echte engine de uitvoering draaien; geeft de uitzondering terug (of `None`). Zonder wachttijd."""
    async with _workersessie(als_eigenaar=True) as sessie:
        set_tenant_id(klant)
        motor = ProductionWorkflowEngine(
            db_session=sessie,
            llm_provider=llm or FakeLLMProvider(),
            tool_broker=tools or FakeToolBroker(),
            agent_runtime=FakeAgentRuntime(),
            state_machine=WorkflowStateMachine(),
        )
        with patch("src.core.workflow.engine.asyncio.sleep", new=AsyncMock()):
            try:
                await motor.execute_workflow(uitvoering)
            except Exception as fout:
                return fout
    return None


def _rij(db: PgConnection, uitvoering: str) -> dict[str, Any]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT status, started_at IS NOT NULL, finished_at IS NOT NULL, tasks_completed, tasks_failed, "
            "error_message FROM c7_workflow_executions WHERE execution_id = %s",
            (uitvoering,),
        )
        status, gestart, klaar, gedaan, mislukt, fout = cur.fetchone()
    return {
        "status": status,
        "gestart": gestart,
        "klaar": klaar,
        "gedaan": gedaan,
        "mislukt": mislukt,
        "fout": fout,
    }


def _taak(db: PgConnection, uitvoering: str) -> dict[str, Any]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT status, finished_at IS NOT NULL, error_json::text FROM c7_execution_tasks "
            "WHERE execution_id = %s",
            (f"id_{uitvoering}",),
        )
        status, klaar, fout = cur.fetchone()
    return {"status": status, "klaar": klaar, "fout": fout}


class TestDeStatuspaginaKrijgtWaarden:
    async def test_na_een_geslaagde_run_staan_tijden_en_tellers_op_de_uitvoering(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        uitvoering = _maak(db, wereld.klant_a, _NODES_EEN_LLMSTAP)

        await _voer_uit(uitvoering, wereld.klant_a)

        rij = _rij(db, uitvoering)
        assert (rij["status"], rij["gestart"], rij["klaar"], rij["gedaan"], rij["mislukt"]) == (
            "succeeded",
            True,
            True,
            1,
            0,
        )

    async def test_na_een_geslaagde_run_heeft_de_taak_een_eindtijd(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        uitvoering = _maak(db, wereld.klant_a, _NODES_EEN_LLMSTAP)

        await _voer_uit(uitvoering, wereld.klant_a)

        taak = _taak(db, uitvoering)
        assert (taak["status"], taak["klaar"]) == ("succeeded", True)

    async def test_na_een_mislukte_run_staat_de_reden_op_de_uitvoering_en_de_taak(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        uitvoering = _maak(db, wereld.klant_a, _NODES_EEN_LLMSTAP)

        await _voer_uit(uitvoering, wereld.klant_a, llm=_KapotLLM())

        rij, taak = _rij(db, uitvoering), _taak(db, uitvoering)
        assert (
            rij["status"],
            rij["klaar"],
            rij["mislukt"],
            "model weg" in (rij["fout"] or ""),
            "model weg" in (taak["fout"] or ""),
        ) == ("failed", True, 1, True, True)


class TestEenToolstapDieMisluktLaatDeUitvoeringFalen:
    async def test_een_toolstap_met_success_false_eindigt_op_failed(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        uitvoering = _maak(db, wereld.klant_a, _NODES_EEN_TOOLSTAP)

        await _voer_uit(uitvoering, wereld.klant_a, tools=_WeigerendeTools())

        rij = _rij(db, uitvoering)
        assert (rij["status"], "geen toestemming" in (rij["fout"] or "")) == ("failed", True)

    async def test_een_toolstap_die_slaagt_eindigt_op_succeeded(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        uitvoering = _maak(db, wereld.klant_a, _NODES_EEN_TOOLSTAP)

        await _voer_uit(uitvoering, wereld.klant_a)

        assert _rij(db, uitvoering)["status"] == "succeeded"


class TestDeTaalmodelstapKrijgtDeKlantVanDeUitvoering:
    async def test_het_model_wordt_aangeroepen_met_de_klant_van_de_uitvoering(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        uitvoering = _maak(db, wereld.klant_b, _NODES_EEN_LLMSTAP)
        llm = _OpnemendLLM()

        await _voer_uit(uitvoering, wereld.klant_b, llm=llm)

        assert [a.get("tenant_id") for a in llm.aanroepen] == [wereld.klant_b]


class TestEenLegeWorkflow:
    async def test_een_lege_workflow_wordt_geweigerd_met_een_nederlandse_reden(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        uitvoering = _maak(db, wereld.klant_a, "{}")

        fout = await _voer_uit(uitvoering, wereld.klant_a)

        rij = _rij(db, uitvoering)
        assert (type(fout).__name__, rij["status"], "geen stappen" in (rij["fout"] or "")) == (
            "ValueError",
            "failed",
            True,
        )


class TestEenHerstartMaaktGeenDubbeleTaken:
    async def test_initialize_tasks_twee_keer_geeft_een_taakrecord(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        uitvoering = _maak(db, wereld.klant_a, _NODES_EEN_LLMSTAP)

        async with _workersessie(als_eigenaar=True) as sessie:
            set_tenant_id(wereld.klant_a)
            motor = ProductionWorkflowEngine(
                db_session=sessie,
                llm_provider=MagicMock(),
                tool_broker=MagicMock(),
                agent_runtime=MagicMock(),
                state_machine=WorkflowStateMachine(),
            )
            uitvoering_rij = await motor._get_execution(uitvoering)
            spec = motor._parse_spec(
                uitvoering_rij.workflow.workflow_id,
                uitvoering_rij.workflow.version,
                uitvoering_rij.workflow.spec_json,
            )
            await motor._initialize_tasks(uitvoering_rij, spec, ["stap1"])
            await motor._initialize_tasks(uitvoering_rij, spec, ["stap1"])
            aantal = (
                await sessie.execute(
                    select(func.count())
                    .select_from(C7ExecutionTask)
                    .where(C7ExecutionTask.execution_id == uitvoering_rij.id)
                )
            ).scalar_one()

        assert aantal == 1
