"""Unit tests: CritiqueStore HITL escalation for low-scoring critiques.

SP-AGT-007 Dag 1 -- Item B
Tests are RED before implementation (_create_hitl_ticket and _HITL_SCORE_THRESHOLD
do not yet exist on CritiqueStore).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.agents.critique_store import Critique, CritiqueStore


@pytest.fixture
def fresh_store():
    """Return a new CritiqueStore without singleton caching."""
    store = CritiqueStore.__new__(CritiqueStore)
    store._initialized = True
    from collections import defaultdict
    from datetime import datetime, timezone

    store._critiques = defaultdict(list)
    store._critiques_by_agent = defaultdict(lambda: defaultdict(list))
    store._critiques_by_task = defaultdict(dict)
    store._max_critiques_per_tenant = 10000
    store._last_mv_refresh = None
    store._mv_refresh_cooldown_s = 300
    import threading

    store._lock = threading.Lock()  # ADR-036 OP-16: threading.Lock, niet asyncio.Lock
    return store


def _make_critique(score: float, tenant_id: int = 1) -> Critique:
    return Critique(
        critique_id="test-id-001",
        agent_name="TestAgent",
        task_id="task-001",
        tenant_id=tenant_id,
        score=score,
        issues=[],
        suggestions=[],
        mode="advisory",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_store_triggers_hitl_when_score_below_threshold(fresh_store):
    """store() triggers _create_hitl_ticket when score < _HITL_SCORE_THRESHOLD (0.40)."""
    # _HITL_SCORE_THRESHOLD must exist on CritiqueStore (AttributeError if not added yet)
    assert hasattr(CritiqueStore, "_HITL_SCORE_THRESHOLD"), (
        "CritiqueStore._HITL_SCORE_THRESHOLD must be defined"
    )

    critique = _make_critique(score=0.30, tenant_id=1)

    with patch.object(fresh_store, "_persist_to_db", new=AsyncMock(return_value=None)):
        with patch.object(fresh_store, "_refresh_mv", new=AsyncMock(return_value=None)):
            with patch.object(
                fresh_store, "_create_hitl_ticket", new=AsyncMock(return_value=None)
            ) as mock_hitl:
                await fresh_store.store(critique)

    mock_hitl.assert_called_once_with(critique)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_store_does_not_trigger_hitl_when_score_above_threshold(fresh_store):
    """store() does NOT trigger _create_hitl_ticket when score >= _HITL_SCORE_THRESHOLD."""
    critique = _make_critique(score=0.75, tenant_id=1)

    with patch.object(fresh_store, "_persist_to_db", new=AsyncMock(return_value=None)):
        with patch.object(fresh_store, "_refresh_mv", new=AsyncMock(return_value=None)):
            with patch.object(
                fresh_store, "_create_hitl_ticket", new=AsyncMock(return_value=None)
            ) as mock_hitl:
                await fresh_store.store(critique)

    mock_hitl.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hitl_error_does_not_block_primary_store(fresh_store):
    """An exception in _create_hitl_ticket must not propagate through store()."""
    critique = _make_critique(score=0.20, tenant_id=1)

    with patch.object(fresh_store, "_persist_to_db", new=AsyncMock(return_value=None)) as mock_db:
        with patch.object(fresh_store, "_refresh_mv", new=AsyncMock(return_value=None)):
            with patch.object(
                fresh_store,
                "_create_hitl_ticket",
                new=AsyncMock(side_effect=RuntimeError("hitl unavailable")),
            ):
                result = await fresh_store.store(critique)

    assert result is True
    mock_db.assert_called_once_with(critique)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hitl_ticket_contains_correct_fields(fresh_store):
    """_create_hitl_ticket is called with the critique that contains agent_name, task_id, tenant_id, score."""
    critique = _make_critique(score=0.10, tenant_id=1)
    critique.agent_name = "ScoredAgent"
    critique.task_id = "task-xyz"

    with patch.object(fresh_store, "_persist_to_db", new=AsyncMock(return_value=None)):
        with patch.object(fresh_store, "_refresh_mv", new=AsyncMock(return_value=None)):
            with patch.object(
                fresh_store, "_create_hitl_ticket", new=AsyncMock(return_value=None)
            ) as mock_hitl:
                await fresh_store.store(critique)

    called_critique = mock_hitl.call_args[0][0]
    assert called_critique.agent_name == "ScoredAgent"
    assert called_critique.task_id == "task-xyz"
    assert called_critique.tenant_id == 1
    assert called_critique.score == 0.10


@pytest.mark.unit
@pytest.mark.asyncio
async def test_silent_mode_skips_hitl_ticket(fresh_store):
    """_create_hitl_ticket returns early for SILENT mode -- telemetry-only critiques must not escalate."""
    critique = _make_critique(score=0.10, tenant_id=1)
    critique.mode = "silent"

    with patch("src.core.database.database.db_manager") as mock_db:
        mock_db.initialize = AsyncMock()
        await fresh_store._create_hitl_ticket(critique)

    mock_db.initialize.assert_not_called()
