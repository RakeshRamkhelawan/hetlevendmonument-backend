"""`write_audit_log_task` en `process_cva_message` slagen bij ELKE run (Keten B nazorg, punt B).

Zelfde defect als bij de debiteurenactors (`test_debiteuren_actor_draait_elke_run.py`): de
actor doet `asyncio.run(...)` op de processen-brede `db_manager` met een echte connectiepool.
Elke run is een nieuwe event loop; een verbinding die de eerste run in de pool achterlaat hangt
aan een gesloten loop, en de tweede run trekt hem eruit (`attached to a different loop`).

**Opstelling = de worker.** Zoals in het debiteurenbestand: `DatabaseInitMiddleware.after_process_boot`
(de echte hook uit `src/workers/workflow_worker.py`) zet `db_manager` op een GEPOOLDE engine; de
test roept de onderliggende functie van de actor (`.fn`) synchroon twee keer aan. De autouse-fixture
`setup_db_manager` (tests/integration/conftest.py) zet `db_manager` op `NullPool`, en dan bestaat
het defect niet: die fixture raakt dus wat hier gemeten wordt, en de `workerdatabase`-fixture hier
bouwt hem opnieuw op en herstelt hem. Een assertie controleert dat de pool niet `NullPool` is.

**Hoe een fout zichtbaar wordt.** `write_audit_log_task` VANGT elke uitzondering en logt alleen
(audit mag de hoofdhandeling niet blokkeren). Een loopfout bij de tweede run komt daarom niet als
exceptie naar buiten: de test meet dat de auditregel van de tweede run IN `audit_logs` staat.
`process_cva_message` laat de fout wel opborrelen; daar toetst de test dat de tweede aanroep
niets gooit. De cva-run gebruikt een tenant zonder integratie: de actor doet dan een SELECT op de
pool en keert terug, zonder CVA, LLM of netwerk; dat is genoeg om de pool over twee loops te
gebruiken.

**`execute_workflow_step` (B2) slikt de fout stil.** `AutonomousAgent._governance_contract_for`
laadt het opgeslagen contract in een `try/except Exception` die alleen WAARSCHUWT (fail-open, met
opzet) en daarna een vers, conservatief contract gebruikt. Een loopfout bij de tweede run komt dus
niet als exceptie naar buiten en het ontbreken van een exceptie bewijst niets. De test meet het
EFFECT: een opgeslagen contract (met een goedgekeurde actie en een marker) wordt door de run geladen
en teruggeschreven; geslaagd laden = marker weg (het verse contract overschrijft) en
`approved_actions` behouden. Mislukt het laden of opslaan, dan staat de rij nog ongewijzigd in de
database. De agent krijgt een vaste `agent_id` (de actor maakt anders per run een nieuwe uuid, en
dan is er nooit iets om te laden). Redis (poort 6380 in de testcontainers) is een echte grens die
de actor daarna nodig heeft; `REDIS_URL` moet er dus naar wijzen.

**Alleen PostgreSQL** (asyncpg-verbindingen zijn aan een loop gebonden; SQLite kent dit niet).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from src.core.database.database import db_manager
from tests.integration.conftest import TEST_DB_URL

TENANT_ID = 1
AUDIT_ACTIE = "actor_loop_test"
WORKFLOW_AGENT_ID = "actor-loop-test-agent"
STAAT_NOG_OP_DE_RIJ = "staat-nog-op-de-rij"


def _tel_auditregels(volgnummer: str) -> int:
    async def _doe() -> int:
        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        try:
            async with engine.connect() as verbinding:
                res = await verbinding.execute(
                    text("SELECT count(*) FROM audit_logs WHERE action = :a AND resource = :r"),
                    {"a": AUDIT_ACTIE, "r": volgnummer},
                )
                return int(res.scalar_one())
        finally:
            await engine.dispose()

    return asyncio.run(_doe())


def _ruim_auditregels_op(*volgnummers: str) -> None:
    async def _doe() -> None:
        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        try:
            async with engine.begin() as verbinding:
                await verbinding.execute(
                    text("DELETE FROM audit_logs WHERE action = :a AND resource = ANY(:r)"),
                    {"a": AUDIT_ACTIE, "r": list(volgnummers)},
                )
        finally:
            await engine.dispose()

    asyncio.run(_doe())


def _zet_opgeslagen_contract(marker: str) -> None:
    """Zet het opgeslagen contract van de testagent op een bekende toestand (NullPool, eigen loop)."""

    async def _doe() -> None:
        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        try:
            async with engine.begin() as verbinding:
                await verbinding.execute(
                    text(
                        "DELETE FROM agent_governance_contracts "
                        "WHERE tenant_id = :t AND agent_id = :a"
                    ),
                    {"t": TENANT_ID, "a": WORKFLOW_AGENT_ID},
                )
                await verbinding.execute(
                    text(
                        "INSERT INTO agent_governance_contracts "
                        "(tenant_id, agent_id, autonomy_level, risk_category, evidence) "
                        "VALUES (:t, :a, 'HUMAN_ON_LOOP', 'minimal', CAST(:e AS jsonb))"
                    ),
                    {
                        "t": TENANT_ID,
                        "a": WORKFLOW_AGENT_ID,
                        "e": json.dumps({"approved_actions": ["x"], "marker": marker}),
                    },
                )
        finally:
            await engine.dispose()

    asyncio.run(_doe())


def _lees_opgeslagen_evidence() -> dict[str, object]:
    async def _doe() -> dict[str, object]:
        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        try:
            async with engine.connect() as verbinding:
                res = await verbinding.execute(
                    text(
                        "SELECT evidence FROM agent_governance_contracts "
                        "WHERE tenant_id = :t AND agent_id = :a"
                    ),
                    {"t": TENANT_ID, "a": WORKFLOW_AGENT_ID},
                )
                return dict(res.scalar_one())
        finally:
            await engine.dispose()

    return asyncio.run(_doe())


def _ruim_opgeslagen_contract_op() -> None:
    async def _doe() -> None:
        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        try:
            async with engine.begin() as verbinding:
                await verbinding.execute(
                    text(
                        "DELETE FROM agent_governance_contracts "
                        "WHERE tenant_id = :t AND agent_id = :a"
                    ),
                    {"t": TENANT_ID, "a": WORKFLOW_AGENT_ID},
                )
        finally:
            await engine.dispose()

    asyncio.run(_doe())


@pytest.fixture
def workerdatabase() -> Iterator[None]:
    """`db_manager` zoals een workerproces hem krijgt: via de echte `after_process_boot`."""
    from src.workers.workflow_worker import DatabaseInitMiddleware

    bewaard = (db_manager.engine, db_manager.async_session_maker, db_manager._initialized)
    db_manager.engine = None
    db_manager.async_session_maker = None
    db_manager._initialized = False
    try:
        DatabaseInitMiddleware().after_process_boot(None)
        assert db_manager.engine is not None
        assert not isinstance(db_manager.engine.pool, NullPool), (
            "opstelling: de workerhook moet een gepoolde engine geven, anders meet de test niets"
        )
        yield
    finally:
        eigen = db_manager.engine
        if eigen is not None:
            asyncio.run(eigen.dispose())
        db_manager.engine, db_manager.async_session_maker, db_manager._initialized = bewaard


@pytest.mark.integration
class TestAuditActorDraaitElkeRun:
    def test_twee_runs_na_elkaar_schrijven_allebei_hun_auditregel(
        self, workerdatabase: None
    ) -> None:
        from src.core.tasks.audit_tasks import write_audit_log_task

        try:
            write_audit_log_task.fn(
                tenant_id=TENANT_ID, action=AUDIT_ACTIE, resource="run-1", user_id=None
            )
            write_audit_log_task.fn(
                tenant_id=TENANT_ID, action=AUDIT_ACTIE, resource="run-2", user_id=None
            )
            geschreven = (_tel_auditregels("run-1"), _tel_auditregels("run-2"))
        finally:
            _ruim_auditregels_op("run-1", "run-2")

        assert geschreven == (1, 1)


@pytest.mark.integration
class TestCvaActorDraaitElkeRun:
    def test_twee_runs_na_elkaar_gooien_geen_loopfout(self, workerdatabase: None) -> None:
        from src.core.tasks.cva_tasks import process_cva_message

        verzoek = {"tenant_id": TENANT_ID, "channel": "telegram", "text": "hallo", "sender_id": 1}

        process_cva_message.fn(verzoek)
        process_cva_message.fn(verzoek)


@pytest.mark.integration
class TestWorkflowActorDraaitElkeRun:
    def test_tweede_run_laadt_het_opgeslagen_governancecontract_nog(
        self, workerdatabase: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.agents.autonomous_agent import AutonomousAgent
        from src.core.tasks import workflow_tasks

        monkeypatch.setattr(
            workflow_tasks, "AutonomousAgent", lambda: AutonomousAgent(agent_id=WORKFLOW_AGENT_ID)
        )
        stap = {
            "task_id": "loop-test",
            "title": "lustest",
            "description": "twee runs",
            "tenant_id": TENANT_ID,
            "metadata": {},
        }
        try:
            _zet_opgeslagen_contract("voor-run-1")
            workflow_tasks.execute_workflow_step.fn(stap)
            _zet_opgeslagen_contract(STAAT_NOG_OP_DE_RIJ)
            workflow_tasks.execute_workflow_step.fn(stap)
            evidence = _lees_opgeslagen_evidence()
        finally:
            _ruim_opgeslagen_contract_op()

        # Geslaagd laden + terugschrijven: marker weg, goedgekeurde actie behouden.
        assert (evidence.get("marker"), evidence.get("approved_actions")) == (None, ["x"])
