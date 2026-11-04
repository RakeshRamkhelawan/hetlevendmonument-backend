"""
Digital Twin Memory — Real Integration Tests
============================================

No mocks.  No placeholders.  Live PostgreSQL (port 5435, dev DB with all
Alembic migrations already applied).

Test isolation:  every test function opens a real connection, begins a
SAVEPOINT transaction, runs the test, then ROLLS BACK the savepoint.
No data is left in the database after any test — even on failure.

The conftest.py `postgres_engine` fixture cannot be reused here because it
calls metadata.create_all which fails on FK constraints against tables that
are only in the production schema.  We use our own `dt_session` fixture.

Covers:
  1. MemoryWriteService — write, dedup, bulk_write against real DB
  2. MemoryRetrievalService — FTS query, retrieval trace written
  3. ContextPackerService — upsert_profile, snapshot created, build()
  4. MemoryConsolidationWorker — events → items, archival, run row
  5. ProfileDriftEngine — detect(), re_anchor() against real profile
  6. End-to-end pipeline (write → retrieve → consolidate → drift)
"""

from __future__ import annotations

import socket
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Database fixture: connects to dev DB (already has all memory tables)
# ---------------------------------------------------------------------------

# De database komt uit de centrale opgave (ADR-036 OP-243). Hier stond een hardgecodeerde
# 5435 met de toelichting "ALWAYS use the dev DB at port 5435 -- NOT overridden by
# conftest". Die uitzondering bestond omdat de conftest een GERADEN waarde zette; nu de
# opgave expliciet is, is er niets meer om je aan te onttrekken. Wie een andere database
# wil, wijst die aan.
from tests.fixtures.testdatabase import (  # noqa: E402
    TestdatabaseNietOpgegeven,
    testdatabase_poort,
    testdatabase_url,
)


def _dev_db_available() -> bool:
    """Check of de OPGEGEVEN database bereikbaar is."""
    try:
        testdatabase_url()
        poort = testdatabase_poort()
    except TestdatabaseNietOpgegeven:
        return False
    try:
        with socket.create_connection(("127.0.0.1", poort), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _dev_db_available(),
    reason="Digital twin tests require dev DB at localhost:5435 with Alembic migrations. "
    "Start the dev container: docker-compose up sanskritisetu_postgres",
)


@pytest_asyncio.fixture
async def dt_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Opens a connection to the live dev PostgreSQL, begins a transaction,
    yields a session, then rolls back — leaving no trace in the DB.

    Uses SAVEPOINT semantics so the rollback is clean even after flush().
    """
    engine = create_async_engine(testdatabase_url(), echo=False)
    conn = await engine.connect()
    # Outer transaction — will be rolled back at teardown
    txn = await conn.begin()
    # Set RLS bypass so our tenant_id=9999 rows are not rejected by policies
    await conn.execute(text("SET app.current_tenant = ''"))

    # Seed test tenant within the transaction (rolled back at teardown)
    await conn.execute(
        text(
            "INSERT INTO tenants(id, name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES(9999, 'integration_test_tenant', 'test-tenant-9999', true, 100, 50, 10) "
            "ON CONFLICT (id) DO NOTHING"
        )
    )

    session_factory = async_sessionmaker(
        bind=conn,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
    await txn.rollback()
    await conn.close()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT_ID = 9999  # isolated test tenant — rolled back after each test
AGENT_ID = "test_cva_integration"


async def _count(session, model, **where) -> int:
    conditions = [getattr(model, k) == v for k, v in where.items()]
    result = await session.execute(select(func.count(model.id)).where(*conditions))
    return result.scalar_one()


# ===========================================================================
# 1. MemoryWriteService
# ===========================================================================


class TestMemoryWriteServiceIntegration:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_write_creates_item_in_db(self, dt_session):
        """A written item must be retrievable from the real database."""
        from src.domains.memory.models import MemoryItem
        from src.domains.memory.schemas import MemoryItemWrite
        from src.domains.memory.services.memory_write_service import MemoryWriteService

        svc = MemoryWriteService(db=dt_session, tenant_id=TENANT_ID)
        payload = MemoryItemWrite(
            content="The Earth orbits the Sun in approximately 365 days.",
            memory_type="semantic",
            source_type="import",
            agent_id=AGENT_ID,
            confidence=0.95,
            importance=0.8,
        )
        item = await svc.write(payload=payload)
        await dt_session.flush()

        assert item is not None
        assert item.id is not None
        assert item.tenant_id == TENANT_ID
        assert item.status == "proposed"  # safe default

        # Verify it's in the DB
        result = await dt_session.execute(select(MemoryItem).where(MemoryItem.id == item.id))
        db_item = result.scalar_one()
        assert db_item.content == payload.content
        assert db_item.dedup_hash is not None  # hash was computed

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_dedup_prevents_duplicate_write(self, dt_session):
        """Writing the same content twice must not create two rows."""
        from src.domains.memory.models import MemoryItem
        from src.domains.memory.schemas import MemoryItemWrite
        from src.domains.memory.services.memory_write_service import MemoryWriteService

        svc = MemoryWriteService(db=dt_session, tenant_id=TENANT_ID)
        content = "Deduplication test: unique string XYZ-9992."
        payload = MemoryItemWrite(
            content=content, memory_type="semantic", source_type="import", agent_id=AGENT_ID
        )

        item1 = await svc.write(payload=payload)
        await dt_session.flush()

        item2 = await svc.write(payload=payload)
        await dt_session.flush()

        # Both calls must return the same item
        assert item1.id == item2.id

        # Only one row in DB
        count = await _count(
            dt_session, MemoryItem, tenant_id=TENANT_ID, dedup_hash=item1.dedup_hash
        )
        assert count == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_auto_accept_consolidation_creates_accepted_item(self, dt_session):
        """consolidation source with auto_accept=True → status=accepted in DB."""
        from src.domains.memory.schemas import MemoryItemWrite
        from src.domains.memory.services.memory_write_service import MemoryWriteService

        svc = MemoryWriteService(db=dt_session, tenant_id=TENANT_ID)
        payload = MemoryItemWrite(
            content="Consolidated semantic fact for integration test.",
            memory_type="semantic",
            source_type="consolidation",
            agent_id=AGENT_ID,
        )
        item = await svc.write(payload=payload, auto_accept=True)
        await dt_session.flush()

        assert item.status == "accepted"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bulk_write_creates_multiple_items(self, dt_session):
        """bulk_write must persist all items in a single flush."""
        from src.domains.memory.models import MemoryItem
        from src.domains.memory.schemas import MemoryItemWrite
        from src.domains.memory.services.memory_write_service import MemoryWriteService

        svc = MemoryWriteService(db=dt_session, tenant_id=TENANT_ID)
        payloads = [
            MemoryItemWrite(
                content=f"Bulk item {i} — integration test.",
                memory_type="episodic",
                source_type="import",
                agent_id=AGENT_ID,
            )
            for i in range(5)
        ]
        items = await svc.bulk_write(payloads=payloads)
        await dt_session.flush()

        assert len(items) == 5
        for item in items:
            assert item.id is not None


# ===========================================================================
# 2. MemoryRetrievalService
# ===========================================================================


class TestMemoryRetrievalServiceIntegration:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_query_returns_items_and_writes_trace(self, dt_session):
        """
        After writing items, a FTS query must:
          - Return at least one result (ILIKE fallback if FTS unavailable)
          - Write a MemoryRetrievalTrace row to the DB
        """
        from src.domains.memory.models import MemoryRetrievalTrace
        from src.domains.memory.schemas import MemoryItemWrite, MemoryQueryRequest
        from src.domains.memory.services.memory_retrieval_service import MemoryRetrievalService
        from src.domains.memory.services.memory_write_service import MemoryWriteService

        write_svc = MemoryWriteService(db=dt_session, tenant_id=TENANT_ID)
        payload = MemoryItemWrite(
            content="Quantum entanglement enables instantaneous correlation.",
            memory_type="semantic",
            source_type="consolidation",
            agent_id=AGENT_ID,
        )
        item = await write_svc.write(payload=payload, auto_accept=True)
        await dt_session.flush()

        retrieval_svc = MemoryRetrievalService(db=dt_session, tenant_id=TENANT_ID)
        request = MemoryQueryRequest(
            query="quantum entanglement",
            top_k=5,
            agent_id=AGENT_ID,
            min_confidence=0.0,
        )
        result = await retrieval_svc.query(request)
        await dt_session.flush()

        # At least the item we just wrote should match
        assert result["total_candidates"] >= 1
        returned_ids = [i.id for i in result["items"]]
        assert item.id in returned_ids

        # Trace must exist in DB
        trace_result = await dt_session.execute(
            select(MemoryRetrievalTrace).where(
                MemoryRetrievalTrace.tenant_id == TENANT_ID,
                MemoryRetrievalTrace.query_text == "quantum entanglement",
            )
        )
        trace = trace_result.scalar_one_or_none()
        assert trace is not None
        assert trace.result_count >= 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_retrieval_method_recorded_in_trace(self, dt_session):
        """The retrieval_method field in the trace matches what the service used."""
        from src.domains.memory.models import MemoryRetrievalTrace
        from src.domains.memory.schemas import MemoryQueryRequest
        from src.domains.memory.services.memory_retrieval_service import MemoryRetrievalService

        svc = MemoryRetrievalService(db=dt_session, tenant_id=TENANT_ID)
        request = MemoryQueryRequest(
            query="unique_integration_test_sentinel_query_no_match_expected",
            top_k=5,
            agent_id=AGENT_ID,
            min_confidence=0.0,
        )
        result = await svc.query(request)
        await dt_session.flush()

        method = result["retrieval_method"]
        assert method in ("fulltext", "vector", "hybrid_fallback")

        # Trace retrieval_method matches
        trace_result = await dt_session.execute(
            select(MemoryRetrievalTrace)
            .where(
                MemoryRetrievalTrace.tenant_id == TENANT_ID,
                MemoryRetrievalTrace.retrieval_method == method,
            )
            .order_by(MemoryRetrievalTrace.id.desc())
            .limit(1)
        )
        trace = trace_result.scalar_one_or_none()
        assert trace is not None


# ===========================================================================
# 3. ContextPackerService
# ===========================================================================


class TestContextPackerServiceIntegration:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_upsert_profile_creates_profile_and_snapshot(self, dt_session):
        """First upsert must create profile + AgentProfileSnapshot v1."""
        from src.domains.memory.models import AgentMemoryProfile, AgentProfileSnapshot
        from src.domains.memory.services.context_packer_service import ContextPackerService

        packer = ContextPackerService(db=dt_session, tenant_id=TENANT_ID)
        profile = await packer.upsert_profile(
            agent_id=AGENT_ID,
            persona_name="Test Agent",
            persona_description="Integration test persona.",
            active_goals=["Assist users", "Learn continuously"],
            operating_rules=["Be accurate", "Be concise"],
        )
        await dt_session.flush()

        assert profile.id is not None
        assert profile.profile_version == 1
        assert profile.tenant_id == TENANT_ID

        # Snapshot must exist
        snap_result = await dt_session.execute(
            select(AgentProfileSnapshot).where(
                AgentProfileSnapshot.profile_id == profile.id,
                AgentProfileSnapshot.profile_version == 1,
            )
        )
        snapshot = snap_result.scalar_one()
        assert snapshot.snapshot["active_goals"] == ["Assist users", "Learn continuously"]
        assert snapshot.change_reason == "upsert"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_upsert_profile_increments_version_and_writes_new_snapshot(self, dt_session):
        """Second upsert must increment version and write snapshot v2."""
        from src.domains.memory.models import AgentProfileSnapshot
        from src.domains.memory.services.context_packer_service import ContextPackerService

        packer = ContextPackerService(db=dt_session, tenant_id=TENANT_ID)
        await packer.upsert_profile(
            agent_id=AGENT_ID,
            active_goals=["Goal v1"],
        )
        await dt_session.flush()

        profile = await packer.upsert_profile(
            agent_id=AGENT_ID,
            active_goals=["Goal v1", "Goal v2"],
        )
        await dt_session.flush()

        assert profile.profile_version == 2
        assert profile.active_goals == ["Goal v1", "Goal v2"]

        # v2 snapshot exists
        snap_result = await dt_session.execute(
            select(AgentProfileSnapshot).where(
                AgentProfileSnapshot.profile_id == profile.id,
                AgentProfileSnapshot.profile_version == 2,
            )
        )
        snap_v2 = snap_result.scalar_one()
        assert snap_v2.snapshot["active_goals"] == ["Goal v1", "Goal v2"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_build_context_returns_correct_structure(self, dt_session):
        """build() must return all required keys with correct types."""
        from src.domains.memory.services.context_packer_service import ContextPackerService

        packer = ContextPackerService(db=dt_session, tenant_id=TENANT_ID)
        await packer.upsert_profile(
            agent_id=AGENT_ID,
            persona_name="Integration Agent",
            active_goals=["Help", "Learn"],
        )
        await dt_session.flush()

        ctx = await packer.build(agent_id=AGENT_ID, token_budget=4000)

        assert ctx["agent_id"] == AGENT_ID
        assert ctx["tenant_id"] == TENANT_ID
        assert ctx["profile"] is not None
        assert isinstance(ctx["active_goals"], list)
        assert isinstance(ctx["recent_episodes"], list)
        assert isinstance(ctx["top_facts"], list)
        assert isinstance(ctx["top_preferences"], list)
        assert isinstance(ctx["estimated_tokens"], int)
        assert ctx["estimated_tokens"] >= 0


# ===========================================================================
# 4. MemoryConsolidationWorker
# ===========================================================================


class TestConsolidationWorkerIntegration:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_worker_creates_run_row(self, dt_session):
        """run() must create a MemoryConsolidationRun row regardless of events."""
        from src.domains.memory.models import MemoryConsolidationRun
        from src.domains.memory.services.consolidation_worker import MemoryConsolidationWorker

        worker = MemoryConsolidationWorker(db=dt_session, tenant_id=TENANT_ID)
        run = await worker.run(agent_id=AGENT_ID)
        await dt_session.flush()

        assert run.id is not None
        assert run.status in ("completed", "failed", "partial")
        assert run.tenant_id == TENANT_ID

        # Verify in DB
        db_run = await dt_session.execute(
            select(MemoryConsolidationRun).where(MemoryConsolidationRun.id == run.id)
        )
        assert db_run.scalar_one() is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_worker_promotes_candidate_events(self, dt_session):
        """Candidate events must be promoted to MemoryItems."""
        from src.domains.memory.models import MemoryItem, SessionMemoryEvent
        from src.domains.memory.services.consolidation_worker import MemoryConsolidationWorker

        # Seed a candidate event
        event = SessionMemoryEvent(
            tenant_id=TENANT_ID,
            session_id=88888,
            agent_id=AGENT_ID,
            event_type="message",
            event_data={"content": "Integration test: the capital of France is Paris."},
            memory_candidate=True,
        )
        dt_session.add(event)
        await dt_session.flush()

        items_before = await _count(dt_session, MemoryItem, tenant_id=TENANT_ID, agent_id=AGENT_ID)

        worker = MemoryConsolidationWorker(db=dt_session, tenant_id=TENANT_ID)
        run = await worker.run(agent_id=AGENT_ID)
        await dt_session.flush()

        items_after = await _count(dt_session, MemoryItem, tenant_id=TENANT_ID, agent_id=AGENT_ID)

        assert items_after > items_before
        assert run.items_created >= 1

        # Event must be resolved
        await dt_session.refresh(event)
        assert event.resolved_item_id is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_worker_deduplicates_identical_events(self, dt_session):
        """Identical event content must produce only one MemoryItem."""
        from src.domains.memory.models import MemoryItem, SessionMemoryEvent
        from src.domains.memory.services.consolidation_worker import MemoryConsolidationWorker

        content = "Duplicate event content for dedup test."
        for i in range(3):
            ev = SessionMemoryEvent(
                tenant_id=TENANT_ID,
                session_id=77777,
                agent_id=AGENT_ID,
                event_type="observation",
                event_data={"content": content},
                memory_candidate=True,
            )
            dt_session.add(ev)
        await dt_session.flush()

        worker = MemoryConsolidationWorker(db=dt_session, tenant_id=TENANT_ID)
        run = await worker.run(agent_id=AGENT_ID)
        await dt_session.flush()

        # Only 1 new item created (dedup collapses the cluster)
        assert run.items_created == 1


# ===========================================================================
# 5. ProfileDriftEngine
# ===========================================================================


class TestDriftEngineIntegration:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_detect_returns_none_without_profile(self, dt_session):
        """detect() must return None when no profile exists for the agent."""
        from src.domains.memory.services.drift_engine import ProfileDriftEngine

        engine = ProfileDriftEngine(db=dt_session, tenant_id=TENANT_ID)
        result = await engine.detect("agent_that_does_not_exist_xyz")
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_detect_returns_drift_event_for_existing_profile(self, dt_session):
        """detect() returns a DriftEvent with required fields for a real profile."""
        from src.domains.memory.services.context_packer_service import ContextPackerService
        from src.domains.memory.services.drift_engine import ProfileDriftEngine

        # Create a profile
        packer = ContextPackerService(db=dt_session, tenant_id=TENANT_ID)
        await packer.upsert_profile(
            agent_id=AGENT_ID,
            active_goals=["Provide accurate information", "Assist users efficiently"],
            operating_rules=["Never hallucinate", "Always cite sources"],
        )
        await dt_session.flush()

        engine = ProfileDriftEngine(db=dt_session, tenant_id=TENANT_ID)
        event = await engine.detect(AGENT_ID)

        assert event is not None
        assert 0.0 <= event.drift_score <= 1.0
        assert event.severity in ("none", "warning", "critical")
        assert event.tenant_id == TENANT_ID
        assert event.agent_id == AGENT_ID
        assert isinstance(event.missing_goals, list)
        assert isinstance(event.violated_rules, list)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_detect_high_score_when_no_memories(self, dt_session):
        """Agent with profile but zero memories should score high (activity gap)."""
        from src.domains.memory.services.context_packer_service import ContextPackerService
        from src.domains.memory.services.drift_engine import (
            _ACTIVITY_GAP_MAX_DAYS,
            ProfileDriftEngine,
        )

        agent = "drift_test_no_memories"
        packer = ContextPackerService(db=dt_session, tenant_id=TENANT_ID)
        await packer.upsert_profile(
            agent_id=agent,
            active_goals=["Goal A", "Goal B"],
        )
        await dt_session.flush()

        engine = ProfileDriftEngine(db=dt_session, tenant_id=TENANT_ID)
        event = await engine.detect(agent)

        assert event is not None
        # No memories at all → activity_gap_score = 1.0 + goal_coverage_gap = 1.0
        assert event.drift_score >= 0.5

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_re_anchor_bumps_version_and_writes_snapshot(self, dt_session):
        """re_anchor() must increment profile_version and create a snapshot."""
        from src.domains.memory.models import AgentProfileSnapshot
        from src.domains.memory.services.context_packer_service import ContextPackerService
        from src.domains.memory.services.drift_engine import ProfileDriftEngine

        packer = ContextPackerService(db=dt_session, tenant_id=TENANT_ID)
        profile = await packer.upsert_profile(
            agent_id=AGENT_ID,
            active_goals=["Goal A"],
        )
        await dt_session.flush()

        version_before = profile.profile_version

        engine = ProfileDriftEngine(db=dt_session, tenant_id=TENANT_ID)
        event = await engine.detect(AGENT_ID)
        result = await engine.re_anchor(event)
        await dt_session.flush()

        await dt_session.refresh(profile)
        assert profile.profile_version == version_before + 1

        # Snapshot with re_anchor reason must exist
        snap_result = await dt_session.execute(
            select(AgentProfileSnapshot).where(
                AgentProfileSnapshot.profile_id == profile.id,
                AgentProfileSnapshot.change_reason == "drift_re_anchor",
            )
        )
        snap = snap_result.scalar_one()
        assert "drift_event" in snap.snapshot
        assert snap.snapshot["drift_event"]["drift_score"] == event.drift_score

        assert result["status"] == "re_anchored"
        assert result["new_profile_version"] == version_before + 1


# ===========================================================================
# 6. End-to-end: write → retrieve → consolidate → drift
# ===========================================================================


class TestEndToEndDigitalTwin:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_pipeline(self, dt_session):
        """
        End-to-end: write items → retrieve → run consolidation → detect drift.

        This test exercises every layer without any mocks.
        """
        from src.domains.memory.schemas import MemoryItemWrite, MemoryQueryRequest
        from src.domains.memory.services.consolidation_worker import MemoryConsolidationWorker
        from src.domains.memory.services.context_packer_service import ContextPackerService
        from src.domains.memory.services.drift_engine import ProfileDriftEngine
        from src.domains.memory.services.memory_retrieval_service import MemoryRetrievalService
        from src.domains.memory.services.memory_write_service import MemoryWriteService

        # 1. Create profile
        packer = ContextPackerService(db=dt_session, tenant_id=TENANT_ID)
        await packer.upsert_profile(
            agent_id=AGENT_ID,
            persona_name="E2E Test Agent",
            active_goals=["Help users solve problems"],
            operating_rules=["Be accurate"],
        )
        await dt_session.flush()

        # 2. Write semantic facts
        write_svc = MemoryWriteService(db=dt_session, tenant_id=TENANT_ID)
        facts = [
            "Water boils at 100 degrees Celsius at sea level.",
            "The speed of light in vacuum is approximately 299,792 km/s.",
            "Mitochondria are the powerhouse of the cell.",
        ]
        for fact in facts:
            payload = MemoryItemWrite(
                content=fact,
                memory_type="semantic",
                source_type="consolidation",
                agent_id=AGENT_ID,
                confidence=0.95,
                importance=0.7,
            )
            await write_svc.write(payload=payload, auto_accept=True)
        await dt_session.flush()

        # 3. Retrieve
        retrieval_svc = MemoryRetrievalService(db=dt_session, tenant_id=TENANT_ID)
        result = await retrieval_svc.query(
            MemoryQueryRequest(
                query="water boils degrees",
                top_k=5,
                agent_id=AGENT_ID,
                min_confidence=0.0,
            )
        )
        await dt_session.flush()

        # FTS may return 0 results depending on the tsquery config; just verify structure
        assert "total_candidates" in result
        assert "retrieval_method" in result

        # 4. Run consolidation
        worker = MemoryConsolidationWorker(db=dt_session, tenant_id=TENANT_ID)
        run = await worker.run(agent_id=AGENT_ID)
        await dt_session.flush()

        assert run.status in ("completed", "partial")

        # 5. Drift detection — expect non-null event
        engine = ProfileDriftEngine(db=dt_session, tenant_id=TENANT_ID)
        drift_event = await engine.detect(AGENT_ID)

        assert drift_event is not None
        # With recent items, activity_gap should be lower than without
        assert drift_event.activity_gap_score < 1.0

        # 6. Boot context
        ctx = await packer.build(agent_id=AGENT_ID, token_budget=4000)
        assert ctx["profile"] is not None
        assert len(ctx["top_facts"]) >= 1  # the 3 facts should be included
