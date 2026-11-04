"""Unit tests voor CritiqueStore PostgreSQL persistentie (SP-AGT-005 Dag 1).

Verifieert: _persist_to_db() best-effort patroon -- DB-fouten mogen nooit store() laten falen.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.critique_store import Critique, CritiqueStore


def _make_critique(tenant_id: int = 42, score: float = 0.8) -> Critique:
    return Critique(
        critique_id="test-crit-001",
        agent_name="test_agent",
        task_id="task-001",
        tenant_id=tenant_id,
        score=score,
        issues=["issue_a"],
        suggestions=["suggestion_a"],
        mode="ADVISORY",
        timestamp=datetime.now(timezone.utc),
        metadata={"source": "unit_test"},
    )


@pytest.fixture(autouse=True)
def reset_critique_store():
    """Reset de CritiqueStore singleton voor elke test."""
    CritiqueStore._instance = None
    yield
    CritiqueStore._instance = None


@pytest.mark.asyncio
async def test_store_calls_persist_to_db():
    """store() moet _persist_to_db() aanroepen na in-memory opslag."""
    store = CritiqueStore()
    critique = _make_critique()

    # _refresh_mv is het TWEEDE databasepad in store(); zonder mock probeert het echt te
    # verbinden en kost de retry-backoff ~57s (2026-08-01).
    with (
        patch.object(store, "_persist_to_db", new_callable=AsyncMock) as mock_persist,
        patch.object(store, "_refresh_mv", new_callable=AsyncMock),
    ):
        result = await store.store(critique)

    assert result is True
    mock_persist.assert_called_once_with(critique)


@pytest.mark.asyncio
async def test_store_survives_db_failure():
    """store() mag NOOIT falen als PostgreSQL niet beschikbaar is.

    In-memory write is primary -- DB-fouten zijn silent (gelogged, niet geraised).
    """
    store = CritiqueStore()
    critique = _make_critique()

    with (
        patch.object(store, "_persist_to_db", new_callable=AsyncMock) as mock_persist,
        patch.object(store, "_refresh_mv", new_callable=AsyncMock),
    ):
        mock_persist.side_effect = Exception("DB unreachable")
        result = await store.store(critique)

    assert result is True
    critiques = await store.get_by_agent(42, "test_agent")
    assert len(critiques) == 1


@pytest.mark.asyncio
async def test_persist_to_db_writes_correct_fields():
    """_persist_to_db() moet een CritiqueRecord aanmaken met alle velden correct."""
    store = CritiqueStore()
    critique = _make_critique(tenant_id=99, score=0.65)

    mock_db = AsyncMock()
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("src.core.database.database.db_manager.initialize", new_callable=AsyncMock),
        patch(
            "src.core.database.database.db_manager.get_session",
            return_value=mock_session_ctx,
        ),
    ):
        await store._persist_to_db(critique)

    mock_db.add.assert_called_once()
    row = mock_db.add.call_args[0][0]
    assert row.critique_id == "test-crit-001"
    assert row.tenant_id == 99
    assert abs(row.score - 0.65) < 0.001
    assert row.issues == ["issue_a"]
    assert row.agent_name == "test_agent"


@pytest.mark.asyncio
async def test_persist_to_db_logs_and_swallows_exception():
    """_persist_to_db() moet exceptions loggen en NOOIT re-raisen."""
    store = CritiqueStore()
    critique = _make_critique()

    with (
        patch(
            "src.core.database.database.db_manager.initialize",
            side_effect=RuntimeError("DB not initialized"),
        ),
        patch("src.core.agents.critique_store.logger") as mock_logger,
    ):
        await store._persist_to_db(critique)

    mock_logger.error.assert_called_once()
    call_msg = mock_logger.error.call_args[0][0]
    assert "critique persist to postgres failed" in call_msg
