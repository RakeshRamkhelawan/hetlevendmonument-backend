"""
Unit tests for the Digital Twin Memory domain (Sprint A + B).

Covers:
  - MemoryWriteService: write, dedup, bulk_write, auto_accept logic
  - MemoryRetrievalService: query routing (vector vs FTS), fallback, trace write
  - ContextPackerService: build(), upsert_profile(), snapshot creation
  - EmbeddingService: embed_item, embed_pending

All tests use MagicMock / AsyncMock — no live DB required.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session():
    """Return a minimal async SQLAlchemy session mock."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _make_item(**kwargs):
    """Return a mock MemoryItem."""
    defaults = dict(
        id=1,
        tenant_id=42,
        agent_id="cva",
        content="The sky is blue.",
        memory_type="semantic",
        status="proposed",
        confidence=0.8,
        importance=5,
        dedup_hash=None,
        privacy_scope="tenant",
        content_embedding=None,
        deleted_at=None,
        created_at=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode()).hexdigest()


# ===========================================================================
# MemoryWriteService
# ===========================================================================


class TestMemoryWriteService:
    @pytest.fixture
    def session(self):
        return _make_session()

    @pytest.fixture
    def write_svc(self, session):
        from src.domains.memory.services.memory_write_service import MemoryWriteService

        return MemoryWriteService(db=session, tenant_id=42)

    # --- dedup hash (module-level function) ---

    def test_dedup_hash_is_sha256_of_normalised_content(self):
        from src.domains.memory.services.memory_write_service import _dedup_hash

        content = "  Hello World  "
        expected = hashlib.sha256(content.strip().lower().encode()).hexdigest()
        assert _dedup_hash(content) == expected

    def test_dedup_hash_case_insensitive(self):
        from src.domains.memory.services.memory_write_service import _dedup_hash

        assert _dedup_hash("HELLO") == _dedup_hash("hello")

    # --- auto_accept whitelist ---

    def test_auto_accept_true_for_consolidation(self, write_svc):
        from src.domains.memory.services.memory_write_service import AUTO_ACCEPT_SOURCES

        assert "consolidation" in AUTO_ACCEPT_SOURCES

    def test_auto_accept_true_for_workflow(self, write_svc):
        from src.domains.memory.services.memory_write_service import AUTO_ACCEPT_SOURCES

        assert "workflow" in AUTO_ACCEPT_SOURCES

    def test_auto_accept_false_for_cva_turn(self, write_svc):
        from src.domains.memory.services.memory_write_service import AUTO_ACCEPT_SOURCES

        assert "cva_turn" not in AUTO_ACCEPT_SOURCES

    # --- write() calls db.add + flush ---

    @pytest.mark.asyncio
    async def test_write_adds_item_and_flushes(self, write_svc, session):
        """write() should add the item to the session and flush."""
        from src.domains.memory.schemas import MemoryItemWrite

        # Simulate: no duplicate found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        payload = MemoryItemWrite(
            content="The sky is blue.",
            memory_type="semantic",
            source_type="chat",
            agent_id="cva",
        )
        await write_svc.write(payload=payload)

        session.add.assert_called_once()
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_write_skips_duplicate(self, write_svc, session):
        """write() must return the existing item when a duplicate hash exists."""
        from src.domains.memory.schemas import MemoryItemWrite

        # Simulate: duplicate found
        existing = _make_item(status="accepted")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=existing)
        session.execute = AsyncMock(return_value=mock_result)

        payload = MemoryItemWrite(
            content="The sky is blue.",
            memory_type="semantic",
            source_type="chat",
            agent_id="cva",
        )
        result = await write_svc.write(payload=payload)

        # Should NOT call db.add (duplicate detected)
        session.add.assert_not_called()
        assert result is existing

    @pytest.mark.asyncio
    async def test_write_auto_accept_consolidation(self, write_svc, session):
        """Items written with auto_accept=True + consolidation source → status='accepted'."""
        from src.domains.memory.schemas import MemoryItemWrite

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        payload = MemoryItemWrite(
            content="Consolidated fact.",
            memory_type="semantic",
            source_type="consolidation",
            agent_id="cva",
        )
        await write_svc.write(payload=payload, auto_accept=True)

        added_item = session.add.call_args[0][0]
        assert added_item.status == "accepted"

    @pytest.mark.asyncio
    async def test_write_proposed_for_chat_without_auto_accept(self, write_svc, session):
        """Items without auto_accept must be created with status='proposed'."""
        from src.domains.memory.schemas import MemoryItemWrite

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        payload = MemoryItemWrite(
            content="User said hello.",
            memory_type="episodic",
            source_type="chat",
            agent_id="cva",
        )
        await write_svc.write(payload=payload)

        added_item = session.add.call_args[0][0]
        assert added_item.status == "proposed"


# ===========================================================================
# MemoryRetrievalService
# ===========================================================================


class TestMemoryRetrievalService:
    @pytest.fixture
    def session(self):
        return _make_session()

    @pytest.fixture
    def retrieval_svc(self, session):
        from src.domains.memory.services.memory_retrieval_service import MemoryRetrievalService

        return MemoryRetrievalService(db=session, tenant_id=42)

    def _make_query_request(self, query="blue sky", top_k=5):
        from src.domains.memory.schemas import MemoryQueryRequest

        return MemoryQueryRequest(
            query=query,
            top_k=top_k,
            agent_id="cva",
            min_confidence=0.5,
        )

    @pytest.mark.asyncio
    async def test_query_without_embedding_uses_fulltext(self, retrieval_svc, session):
        """Without a query_embedding, retrieval_method must be 'fulltext'."""
        items = [_make_item()]
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=items)
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        # trace write also calls execute; make all calls return the same mock
        session.execute = AsyncMock(return_value=result_mock)

        request = self._make_query_request()
        response = await retrieval_svc.query(request)

        assert response["retrieval_method"] == "fulltext"

    @pytest.mark.asyncio
    async def test_query_with_embedding_uses_vector(self, retrieval_svc, session):
        """With a query_embedding provided, retrieval_method must be 'vector'."""
        item = _make_item()
        # _vector_query uses raw SQL; simulate rows and ORM re-fetch
        rows_mock = MagicMock()
        rows_mock.fetchall = MagicMock(return_value=[(1,)])
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[item])
        orm_result = MagicMock()
        orm_result.scalars = MagicMock(return_value=scalars_mock)
        # First call = raw SQL, second call = ORM fetch, subsequent = trace flush
        session.execute = AsyncMock(side_effect=[rows_mock, orm_result, MagicMock()])

        request = self._make_query_request()
        embedding = [0.1] * 1536
        response = await retrieval_svc.query(request, query_embedding=embedding)

        assert response["retrieval_method"] == "vector"

    @pytest.mark.asyncio
    async def test_query_writes_retrieval_trace(self, retrieval_svc, session):
        """Every query must add a MemoryRetrievalTrace to the session."""
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        session.execute = AsyncMock(return_value=result_mock)

        request = self._make_query_request()
        await retrieval_svc.query(request)

        from src.domains.memory.models import MemoryRetrievalTrace

        added_objects = [call[0][0] for call in session.add.call_args_list]
        trace_objects = [o for o in added_objects if isinstance(o, MemoryRetrievalTrace)]
        assert len(trace_objects) == 1
        assert trace_objects[0].tenant_id == 42
        assert trace_objects[0].query_text == "blue sky"

    @pytest.mark.asyncio
    async def test_vector_fallback_to_fts_when_no_results(self, retrieval_svc, session):
        """If vector query returns nothing, retrieval_method must be 'hybrid_fallback'."""
        empty_rows = MagicMock()
        empty_rows.fetchall = MagicMock(return_value=[])

        item = _make_item()
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[item])
        fts_result = MagicMock()
        fts_result.scalars = MagicMock(return_value=scalars_mock)

        trace_result = MagicMock()
        trace_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

        session.execute = AsyncMock(side_effect=[empty_rows, fts_result, trace_result])

        request = self._make_query_request()
        embedding = [0.0] * 1536
        response = await retrieval_svc.query(request, query_embedding=embedding)

        assert response["retrieval_method"] == "hybrid_fallback"
        assert len(response["items"]) == 1


# ===========================================================================
# ContextPackerService
# ===========================================================================


class TestContextPackerService:
    @pytest.fixture
    def session(self):
        return _make_session()

    @pytest.fixture
    def packer(self, session):
        from src.domains.memory.services.context_packer_service import ContextPackerService

        return ContextPackerService(db=session, tenant_id=42)

    @pytest.mark.asyncio
    async def test_build_returns_required_keys(self, packer, session):
        """build() must always return the documented key set."""
        # _load_profile returns None (no profile)
        profile_result = MagicMock()
        profile_result.scalar_one_or_none = MagicMock(return_value=None)
        # episode/fact/pref queries return empty
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        empty_result = MagicMock()
        empty_result.scalars = MagicMock(return_value=scalars_mock)
        session.execute = AsyncMock(return_value=profile_result)

        ctx = await packer.build(agent_id="cva")

        required_keys = {
            "agent_id",
            "tenant_id",
            "profile",
            "active_goals",
            "recent_episodes",
            "top_facts",
            "top_preferences",
            "estimated_tokens",
            "built_at",
        }
        assert required_keys.issubset(ctx.keys())

    @pytest.mark.asyncio
    async def test_upsert_profile_writes_snapshot_on_create(self, packer, session):
        """Creating a new profile must also write an AgentProfileSnapshot."""
        # No existing profile
        no_profile = MagicMock()
        no_profile.scalar_one_or_none = MagicMock(return_value=None)

        # Simulate db.flush() assigning an id
        async def flush_side_effect():
            pass

        session.flush = AsyncMock(side_effect=flush_side_effect)
        session.execute = AsyncMock(return_value=no_profile)

        await packer.upsert_profile(
            agent_id="cva",
            persona_name="Chief Visionary Architect",
            active_goals=["Goal A"],
            operating_rules=["Rule 1"],
        )

        from src.domains.memory.models import AgentMemoryProfile, AgentProfileSnapshot

        added = [call[0][0] for call in session.add.call_args_list]
        profiles = [o for o in added if isinstance(o, AgentMemoryProfile)]
        snapshots = [o for o in added if isinstance(o, AgentProfileSnapshot)]

        assert len(profiles) == 1
        assert len(snapshots) == 1
        assert snapshots[0].snapshot["active_goals"] == ["Goal A"]

    @pytest.mark.asyncio
    async def test_upsert_profile_increments_version_on_update(self, packer, session):
        """Updating an existing profile must increment profile_version."""
        from src.domains.memory.models import AgentMemoryProfile

        existing = AgentMemoryProfile()
        existing.tenant_id = 42
        existing.agent_id = "cva"
        existing.profile_version = 3
        existing.active_goals = []
        existing.operating_rules = []
        existing.domain_expertise = []
        existing.persona_name = "CVA"
        existing.persona_description = ""

        found_result = MagicMock()
        found_result.scalar_one_or_none = MagicMock(return_value=existing)
        session.execute = AsyncMock(return_value=found_result)

        await packer.upsert_profile(agent_id="cva", active_goals=["New Goal"])

        assert existing.profile_version == 4
        assert existing.active_goals == ["New Goal"]


# ===========================================================================
# EmbeddingService
# ===========================================================================


class TestEmbeddingService:
    @pytest.fixture
    def session(self):
        return _make_session()

    @pytest.fixture
    def llm(self):
        mock = MagicMock()
        mock.get_embeddings = AsyncMock(return_value=[0.1] * 1536)
        return mock

    @pytest.fixture
    def embed_svc(self, session, llm):
        from src.domains.memory.services.embedding_service import EmbeddingService

        return EmbeddingService(db=session, tenant_id=42, llm=llm)

    @pytest.mark.asyncio
    async def test_embed_item_sets_content_embedding(self, embed_svc, llm):
        item = _make_item()
        result = await embed_svc.embed_item(item)

        assert result is True
        assert item.content_embedding == [0.1] * 1536
        llm.get_embeddings.assert_awaited_once_with(item.content)

    @pytest.mark.asyncio
    async def test_embed_item_returns_false_on_llm_error(self, embed_svc, llm):
        llm.get_embeddings = AsyncMock(side_effect=RuntimeError("LLM down"))
        item = _make_item()

        result = await embed_svc.embed_item(item)

        assert result is False
        assert item.content_embedding is None

    @pytest.mark.asyncio
    async def test_embed_item_returns_false_on_empty_embedding(self, embed_svc, llm):
        llm.get_embeddings = AsyncMock(return_value=[])
        item = _make_item()

        result = await embed_svc.embed_item(item)

        assert result is False

    @pytest.mark.asyncio
    async def test_embed_pending_processes_items_without_embedding(self, embed_svc, session, llm):
        """embed_pending must flush after each successful embedding."""
        items = [_make_item(id=i, content=f"fact {i}") for i in range(3)]
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=items)
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        session.execute = AsyncMock(return_value=result_mock)

        count = await embed_svc.embed_pending()

        assert count == 3
        assert session.flush.await_count == 3
