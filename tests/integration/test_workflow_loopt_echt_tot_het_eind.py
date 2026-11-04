"""De workflow-worker vindt de uitvoering van de klant en bevestigt de klant (ADR-036 OP-13, brief 2026-10-21).

**Wat er mis was (gemeten op d054a114 in een database uit de migratieketen).** Een echte worker die een
workflowtaak oppakte faalde direct met `operator does not exist: integer = character varying`. De oorzaak had twee
lagen:

1. `neem_de_klant_van_de_opdracht_aan` vergeleek de tekst-id van de opdracht (`exec_...`) met `.id` van het model
   `src.core.models.workflow_models.WorkflowExecution`, en dat is een GEHEEL GETAL;
2. dat model hoort bij een ANDERE tabel (`workflow_executions`) dan waar de API en de engine in schrijven en lezen
   (`c7_workflow_executions`, model `C7WorkflowExecution`, tekst-id in `execution_id`). Alleen de kolom wisselen zou
   dus een lege tabel hebben doorzocht en elke opdracht geweigerd.

**Wat hier bewezen wordt, tegen een ECHTE Postgres:**
- als `sanskritisetu_app` (niet-eigenaar, met afscherming): een opdracht MET klantclaim wordt bevestigd en geeft de
  klant terug; een claim van een ANDERE klant, of een onbekende uitvoering, wordt geweigerd (`TenantOnbekend`);
  zonder claim weigert een niet-eigenaar altijd (de afscherming laat de rij zonder klantcontext niet zien), en er is
  GEEN terugval op klant 1;
- als eigenaar (zoals de applicatie vandaag nog kan verbinden): een opdracht ZONDER claim vindt de klant via
  `execution_id`. Dat is de lezing die de databasefout gaf.

**Mutatiebewijs (2026-10-22):** zie de oplevering van de brief (per element, beide richtingen).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, Iterator
from unittest.mock import MagicMock, patch
from contextlib import asynccontextmanager
from dataclasses import dataclass

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, connection as PgConnection
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from tests.fixtures.testdatabase import testdatabase_poort
from tests.integration.security.test_the_application_role_is_confined_to_its_tenant import (
    _ROL,
    _SCRATCH_DB,
    _bouw_verse_database,
    _dsn,
    _postgres_bereikbaar,
)

from src.core.middleware.tenant_context import set_tenant_id
from src.core.workflow.engine import ProductionWorkflowEngine
from src.core.workflow.providers import FakeAgentRuntime, FakeLLMProvider, FakeToolBroker
from src.core.workflow.state_machine import WorkflowStateMachine
from src.core.workflow.models import (
    C7ExecutionEvent,
    C7ExecutionTask,
    C7WorkflowExecution,
    EventType,
    TaskStatus,
    WorkflowStatus,
)
from src.workers.workflow_worker import TenantOnbekend, neem_de_klant_van_de_opdracht_aan

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op de netwerkpoort uit SANSKRITISETU_TEST_DATABASE_URL",
    ),
]


@dataclass(frozen=True)
class Wereld:
    klant_a: int
    klant_b: int
    uitvoering_a: str
    uitvoering_b: str


@pytest.fixture(scope="module")
def db() -> Iterator[PgConnection]:
    """Verse database uit de migratieketen; de eigenaarsverbinding dient alleen de opstelling."""
    _bouw_verse_database()
    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def wereld(db: PgConnection) -> Wereld:
    """Twee klanten met elk een workflow en een uitvoering in `c7_workflow_executions` (als eigenaar aangemaakt)."""
    achtervoegsel = uuid.uuid4().hex[:8]
    uitvoeringen: dict[str, str] = {}
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES ('Tot het eind A', 'tot-eind-a', true, 10, 50, 5), "
            "('Tot het eind B', 'tot-eind-b', true, 10, 50, 5)"
        )
        cur.execute("SELECT slug, id FROM tenants WHERE slug IN ('tot-eind-a', 'tot-eind-b')")
        klanten = dict(cur.fetchall())
        for slug, klant in klanten.items():
            workflow_id = f"wf_{slug}_{achtervoegsel}"
            uitvoering = f"exec_{slug}_{achtervoegsel}"
            cur.execute(
                "INSERT INTO c7_workflows (id, name, workflow_type, trigger_type, tenant_id, nodes, edges) "
                "VALUES (%s, 'Proef', 'test', 'manual', %s, '[]', '[]')",
                (workflow_id, klant),
            )
            cur.execute(
                "INSERT INTO c7_workflow_executions (id, execution_id, workflow_id, tenant_id) "
                "VALUES (%s, %s, %s, %s)",
                (f"id_{uitvoering}", uitvoering, workflow_id, klant),
            )
            uitvoeringen[slug] = uitvoering
    return Wereld(
        klant_a=klanten["tot-eind-a"],
        klant_b=klanten["tot-eind-b"],
        uitvoering_a=uitvoeringen["tot-eind-a"],
        uitvoering_b=uitvoeringen["tot-eind-b"],
    )


def _async_url() -> str:
    gebruiker = os.environ.get("POSTGRES_USER", "postgres")
    wachtwoord = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return (
        f"postgresql+asyncpg://{gebruiker}:{wachtwoord}@127.0.0.1:"
        f"{testdatabase_poort()}/{_SCRATCH_DB}"
    )


@asynccontextmanager
async def _workersessie(*, als_eigenaar: bool = False) -> AsyncGenerator[AsyncSession]:
    """Een sessie zoals de worker die heeft: standaard als `sanskritisetu_app`, ZONDER klantcontext in de ContextVar."""
    argumenten = {} if als_eigenaar else {"server_settings": {"role": _ROL}}
    engine = create_async_engine(_async_url(), poolclass=NullPool, connect_args=argumenten)
    set_tenant_id(None)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as sessie:
            yield sessie
    finally:
        set_tenant_id(None)
        await engine.dispose()


class TestDeWorkerVindtDeUitvoeringBijEenTekstId:
    async def test_een_opdracht_met_claim_wordt_bevestigd_en_geeft_de_klant_terug(
        self, wereld: Wereld
    ) -> None:
        async with _workersessie() as sessie:
            async with neem_de_klant_van_de_opdracht_aan(
                sessie, wereld.uitvoering_a, wereld.klant_a
            ) as klant:
                vastgesteld = klant

        assert vastgesteld == wereld.klant_a

    async def test_de_uitvoering_van_klant_b_is_ook_voor_klant_b_te_vinden(
        self, wereld: Wereld
    ) -> None:
        async with _workersessie() as sessie:
            async with neem_de_klant_van_de_opdracht_aan(
                sessie, wereld.uitvoering_b, wereld.klant_b
            ) as klant:
                vastgesteld = klant

        assert vastgesteld == wereld.klant_b

    async def test_een_opdracht_zonder_claim_vindt_de_klant_via_execution_id(
        self, wereld: Wereld
    ) -> None:
        """Een opdracht die al in de wachtrij stond voor OP-153 draagt geen klant mee (lezen als eigenaar)."""
        async with _workersessie(als_eigenaar=True) as sessie:
            async with neem_de_klant_van_de_opdracht_aan(
                sessie, wereld.uitvoering_a, None
            ) as klant:
                vastgesteld = klant

        assert vastgesteld == wereld.klant_a

    async def test_een_opdracht_zonder_claim_wordt_door_een_niet_eigenaar_geweigerd(
        self, wereld: Wereld
    ) -> None:
        """De afscherming laat de rij zonder klantcontext niet zien: geweigerd, GEEN terugval op klant 1."""
        async with _workersessie() as sessie:
            with pytest.raises(TenantOnbekend):
                async with neem_de_klant_van_de_opdracht_aan(sessie, wereld.uitvoering_a, None):
                    pass

    async def test_een_claim_van_een_andere_klant_wordt_geweigerd(self, wereld: Wereld) -> None:
        async with _workersessie() as sessie:
            with pytest.raises(TenantOnbekend):
                async with neem_de_klant_van_de_opdracht_aan(
                    sessie, wereld.uitvoering_a, wereld.klant_b
                ):
                    pass

    async def test_een_onbekende_uitvoering_wordt_geweigerd(self, wereld: Wereld) -> None:
        async with _workersessie() as sessie:
            with pytest.raises(TenantOnbekend):
                async with neem_de_klant_van_de_opdracht_aan(
                    sessie, "exec_bestaat_niet", wereld.klant_a
                ):
                    pass


class TestDeStatussenPassenBijDeDatabase:
    """Het model schrijft de waarden die de migratie kent (`pending`), niet de enum-NAMEN (`PENDING`).

    **Gemeten op d054a114:** `POST /api/v1/workflows/{id}/execute` gaf 500 met
    `invalid input value for enum workflow_status_enum: "PENDING"`. De migratie
    (`20260522b_stale_task_index.py`) maakt `status` en `event_type` als gewone tekstkolommen met `'pending'` als
    standaard; het model stuurde de namen in hoofdletters. Daardoor kon de API geen enkele uitvoering aanmaken.
    """

    @staticmethod
    async def _workflow_van(sessie: AsyncSession, klant: int) -> str:
        rij = await sessie.execute(
            text("SELECT id FROM c7_workflows WHERE tenant_id = :t LIMIT 1"), {"t": klant}
        )
        return str(rij.scalar_one())

    async def test_een_uitvoering_aanmaken_met_status_pending_slaat_de_databasewaarde_op(
        self, wereld: Wereld
    ) -> None:
        nieuw = f"exec_status_{uuid.uuid4().hex[:8]}"
        async with _workersessie(als_eigenaar=True) as sessie:
            workflow = await self._workflow_van(sessie, wereld.klant_a)
            sessie.add(
                C7WorkflowExecution(
                    id=nieuw,
                    execution_id=nieuw,
                    workflow_id=workflow,
                    tenant_id=wereld.klant_a,
                    status=WorkflowStatus.PENDING,
                )
            )
            await sessie.commit()
            opgeslagen = (
                await sessie.execute(
                    text("SELECT status FROM c7_workflow_executions WHERE id = :i"), {"i": nieuw}
                )
            ).scalar_one()

        assert opgeslagen == "pending"

    async def test_een_uitvoering_is_terug_te_vinden_op_zijn_status(self, wereld: Wereld) -> None:
        nieuw = f"exec_status_{uuid.uuid4().hex[:8]}"
        async with _workersessie(als_eigenaar=True) as sessie:
            workflow = await self._workflow_van(sessie, wereld.klant_a)
            sessie.add(
                C7WorkflowExecution(
                    id=nieuw,
                    execution_id=nieuw,
                    workflow_id=workflow,
                    tenant_id=wereld.klant_a,
                    status=WorkflowStatus.RUNNING,
                )
            )
            await sessie.commit()
            gevonden = (
                (
                    await sessie.execute(
                        select(C7WorkflowExecution.execution_id).where(
                            C7WorkflowExecution.status == WorkflowStatus.RUNNING,
                            C7WorkflowExecution.execution_id == nieuw,
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert gevonden == [nieuw]

    async def test_een_taak_en_een_gebeurtenis_slaan_de_databasewaarden_op(
        self, wereld: Wereld
    ) -> None:
        nieuw = f"exec_status_{uuid.uuid4().hex[:8]}"
        async with _workersessie(als_eigenaar=True) as sessie:
            workflow = await self._workflow_van(sessie, wereld.klant_a)
            sessie.add(
                C7WorkflowExecution(
                    id=nieuw,
                    execution_id=nieuw,
                    workflow_id=workflow,
                    tenant_id=wereld.klant_a,
                    status=WorkflowStatus.PENDING,
                )
            )
            await sessie.flush()
            sessie.add(
                C7ExecutionTask(
                    id=f"taak_{nieuw}",
                    execution_id=nieuw,
                    tenant_id=wereld.klant_a,
                    task_ref="stap1",
                    task_type="llm",
                    status=TaskStatus.RUNNING,
                )
            )
            sessie.add(
                C7ExecutionEvent(
                    id=f"gebeurtenis_{nieuw}",
                    execution_id=nieuw,
                    tenant_id=wereld.klant_a,
                    event_type=EventType.WORKFLOW_STARTED,
                )
            )
            await sessie.commit()
            taak = (
                await sessie.execute(
                    text("SELECT status FROM c7_execution_tasks WHERE execution_id = :i"),
                    {"i": nieuw},
                )
            ).scalar_one()
            gebeurtenis = (
                await sessie.execute(
                    text("SELECT event_type FROM c7_execution_events WHERE execution_id = :i"),
                    {"i": nieuw},
                )
            ).scalar_one()

        assert (taak, gebeurtenis) == ("running", "workflow_started")


class TestEenUitvoeringDieVoorDeStartFaaltBlijftNietHangen:
    """Faalt de engine voordat de uitvoering is gestart (bijv. een ongeldige definitie), dan eindigt hij op `failed`.

    **Gemeten op d054a114 in een echte worker:** `AttributeError: 'list' object has no attribute 'items'` bij het
    lezen van de definitie, gevolgd door `Invalid workflow state transition: pending -> failed`. De toestandsmachine
    kent geen `pending -> failed`, dus de echte fout verdween achter een tweede fout en de uitvoering bleef voor
    altijd op `pending` staan: de klant ziet nooit dat er iets mis is.
    """

    async def test_een_ongeldige_definitie_zet_de_uitvoering_op_failed_met_de_echte_reden(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        achtervoegsel = uuid.uuid4().hex[:8]
        workflow = f"wf_kapot_{achtervoegsel}"
        uitvoering = f"exec_kapot_{achtervoegsel}"
        with db.cursor() as cur:
            # Een taak zonder `id`: ongeldig, ook in de lijstvorm van het canvas.
            cur.execute(
                "INSERT INTO c7_workflows (id, name, workflow_type, trigger_type, tenant_id, nodes, edges) "
                "VALUES (%s, 'Kapot', 'test', 'manual', %s, '[{\"type\": \"llm\"}]', '[]')",
                (workflow, wereld.klant_a),
            )
            cur.execute(
                "INSERT INTO c7_workflow_executions (id, execution_id, workflow_id, tenant_id) "
                "VALUES (%s, %s, %s, %s)",
                (f"id_{uitvoering}", uitvoering, workflow, wereld.klant_a),
            )

        async with _workersessie(als_eigenaar=True) as sessie:
            set_tenant_id(wereld.klant_a)
            motor = ProductionWorkflowEngine(
                db_session=sessie,
                llm_provider=MagicMock(),
                tool_broker=MagicMock(),
                agent_runtime=MagicMock(),
                state_machine=WorkflowStateMachine(),
            )
            with pytest.raises(ValueError, match="geen id"):
                await motor.execute_workflow(uitvoering)

        with db.cursor() as cur:
            cur.execute(
                "SELECT status, output_json::text FROM c7_workflow_executions WHERE execution_id = %s",
                (uitvoering,),
            )
            status, uitkomst = cur.fetchone()
        assert (status, "geen id" in (uitkomst or "")) == ("failed", True)


class TestEenWorkflowLoopTotHetEind:
    """Een workflow met een stap loopt in de echte engine, op een echte Postgres, tot `succeeded`.

    **Gemeten op d054a114** (een echte worker plus de API, zie de oplevering): de keten brak achter elkaar op
    de statuswaarden, het zoeken van de uitvoering, de vorm van de definitie en het aanmaken van de taakrecords
    (`null value in column "id" of relation "c7_execution_tasks"`). Deze test loopt het hele pad van de engine met
    een nep-taalmodel, zodat een volgende breuk hier rood wordt in plaats van in een klantenomgeving.
    """

    async def test_een_workflow_met_een_stap_komt_op_succeeded(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        achtervoegsel = uuid.uuid4().hex[:8]
        workflow = f"wf_eind_{achtervoegsel}"
        uitvoering = f"exec_eind_{achtervoegsel}"
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO c7_workflows (id, name, workflow_type, trigger_type, tenant_id, nodes, edges) "
                "VALUES (%s, 'Een stap', 'test', 'manual', %s, %s, '{}')",
                (
                    workflow,
                    wereld.klant_a,
                    '{"stap1": {"type": "llm", "prompt": "Zeg hallo", "model": "nep"}}',
                ),
            )
            cur.execute(
                "INSERT INTO c7_workflow_executions (id, execution_id, workflow_id, tenant_id, input_json) "
                "VALUES (%s, %s, %s, %s, '{}')",
                (f"id_{uitvoering}", uitvoering, workflow, wereld.klant_a),
            )

        async with _workersessie(als_eigenaar=True) as sessie:
            set_tenant_id(wereld.klant_a)
            motor = ProductionWorkflowEngine(
                db_session=sessie,
                llm_provider=FakeLLMProvider(),
                tool_broker=FakeToolBroker(),
                agent_runtime=FakeAgentRuntime(),
                state_machine=WorkflowStateMachine(),
            )
            resultaat = await motor.execute_workflow(uitvoering)

        with db.cursor() as cur:
            cur.execute(
                "SELECT status FROM c7_workflow_executions WHERE execution_id = %s", (uitvoering,)
            )
            uitvoering_status = cur.fetchone()[0]
            cur.execute(
                "SELECT task_ref, status FROM c7_execution_tasks WHERE execution_id = %s",
                (f"id_{uitvoering}",),
            )
            taken = cur.fetchall()
        assert (resultaat["status"], uitvoering_status, taken) == (
            "succeeded",
            "succeeded",
            [("stap1", "succeeded")],
        )


class TestFalenIsTerminaalEnVerbergtDeEchteFoutNiet:
    """Gate 2 ronde 1 (H1 en M2): een tweede `_fail_execution` en een kapotte transactie.

    - De DAG-validatie roept `_fail_execution` aan en gooit daarna zelf een `ValueError`; de buitenste `except`
      riep hem opnieuw aan, op een al mislukte uitvoering (`failed -> failed` bestaat niet), en liet DIE fout
      boven komen in plaats van "Invalid DAG".
    - Valt de databasetransactie zelf om (bijv. een NOT NULL-fout), dan kon de buitenste `except` de uitvoering niet
      eens meer laden (`PendingRollbackError`) en bleef hij op `running` staan.
    """

    @staticmethod
    def _maak(db: PgConnection, klant: int, nodes: str, edges: str) -> str:
        achtervoegsel = uuid.uuid4().hex[:8]
        workflow = f"wf_terminaal_{achtervoegsel}"
        uitvoering = f"exec_terminaal_{achtervoegsel}"
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO c7_workflows (id, name, workflow_type, trigger_type, tenant_id, nodes, edges) "
                "VALUES (%s, 'Terminaal', 'test', 'manual', %s, %s, %s)",
                (workflow, klant, nodes, edges),
            )
            cur.execute(
                "INSERT INTO c7_workflow_executions (id, execution_id, workflow_id, tenant_id, input_json) "
                "VALUES (%s, %s, %s, %s, '{}')",
                (f"id_{uitvoering}", uitvoering, workflow, klant),
            )
        return uitvoering

    @staticmethod
    def _motor(sessie: AsyncSession) -> ProductionWorkflowEngine:
        return ProductionWorkflowEngine(
            db_session=sessie,
            llm_provider=FakeLLMProvider(),
            tool_broker=FakeToolBroker(),
            agent_runtime=FakeAgentRuntime(),
            state_machine=WorkflowStateMachine(),
        )

    async def test_een_cyclus_geeft_de_fout_invalid_dag_en_niet_een_statusfout(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        uitvoering = self._maak(
            db,
            wereld.klant_a,
            '{"a": {"type": "llm"}, "b": {"type": "llm"}}',
            '{"a": ["b"], "b": ["a"]}',
        )

        async with _workersessie(als_eigenaar=True) as sessie:
            set_tenant_id(wereld.klant_a)
            with pytest.raises(ValueError, match="Invalid DAG"):
                await self._motor(sessie).execute_workflow(uitvoering)

        with db.cursor() as cur:
            cur.execute(
                "SELECT status, output_json::text FROM c7_workflow_executions WHERE execution_id = %s",
                (uitvoering,),
            )
            status, uitkomst = cur.fetchone()
        assert (status, "Invalid DAG" in (uitkomst or "")) == ("failed", True)

    async def test_een_kapotte_transactie_laat_de_uitvoering_niet_op_running_staan(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        uitvoering = self._maak(
            db, wereld.klant_a, '{"stap1": {"type": "llm", "prompt": "x"}}', "{}"
        )

        async def _breek_de_transactie(self_: object, *_args: object) -> None:
            await sessie_voor_de_breuk.execute(
                text("INSERT INTO c7_execution_tasks (id) VALUES (NULL)")
            )

        async with _workersessie(als_eigenaar=True) as sessie:
            sessie_voor_de_breuk = sessie
            set_tenant_id(wereld.klant_a)
            with patch.object(ProductionWorkflowEngine, "_initialize_tasks", _breek_de_transactie):
                with pytest.raises(Exception):  # noqa: B017 -- het type is van asyncpg; de eis is "niet blijven hangen"
                    await self._motor(sessie).execute_workflow(uitvoering)

        with db.cursor() as cur:
            cur.execute(
                "SELECT status FROM c7_workflow_executions WHERE execution_id = %s", (uitvoering,)
            )
            status = cur.fetchone()[0]
        assert status == "failed"
