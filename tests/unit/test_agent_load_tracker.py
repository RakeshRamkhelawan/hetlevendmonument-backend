"""Unit tests for AgentLoadTracker - Redis-backed per-agent load tracking."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.agents.agent_load_tracker import AgentLoadTracker


def _make_tracker(tenant_id: int = 1) -> AgentLoadTracker:
    tracker = AgentLoadTracker(tenant_id=tenant_id)
    return tracker


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_load_calls_setex_with_ttl():
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        await tracker.set_load("agent_001", 0.5)
    mock_redis.setex.assert_awaited_once_with(tracker._key("agent_001"), 30, "0.5")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_load_clamps_above_one():
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        await tracker.set_load("agent_001", 1.5)
    mock_redis.setex.assert_awaited_once_with(tracker._key("agent_001"), 30, "1.0")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_load_clamps_below_zero():
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        await tracker.set_load("agent_001", -0.3)
    mock_redis.setex.assert_awaited_once_with(tracker._key("agent_001"), 30, "0.0")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_load_returns_float_on_hit():
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"0.75"
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        result = await tracker.get_load("agent_001")
    assert result == pytest.approx(0.75)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_load_returns_none_on_miss():
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        result = await tracker.get_load("agent_001")
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_load_returns_none_when_redis_unavailable():
    tracker = _make_tracker()
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=None)):
        result = await tracker.get_load("agent_001")
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_load_returns_none_on_exception():
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = ConnectionError("Redis down")
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        result = await tracker.get_load("agent_001")
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clear_load_calls_delete():
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        await tracker.clear_load("agent_001")
    mock_redis.delete.assert_awaited_once()


@pytest.mark.unit
def test_key_includes_tenant_id():
    tracker_a = _make_tracker(tenant_id=1)
    tracker_b = _make_tracker(tenant_id=2)
    key_a = tracker_a._key("agent_001")
    key_b = tracker_b._key("agent_001")
    assert "1" in key_a
    assert "2" in key_b
    assert key_a != key_b


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_loads_uses_single_mget_call():
    """MGET batches all agent IDs into one Redis round-trip."""
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    mock_redis.mget.return_value = [b"0.3", b"0.7", None]
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        result = await tracker.get_loads(["agent_a", "agent_b", "agent_c"])
    mock_redis.mget.assert_awaited_once()
    assert result == {"agent_a": pytest.approx(0.3), "agent_b": pytest.approx(0.7), "agent_c": None}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_loads_empty_list_returns_empty_dict():
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        result = await tracker.get_loads([])
    assert result == {}
    mock_redis.mget.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_loads_returns_none_per_key_on_redis_error():
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    mock_redis.mget.side_effect = ConnectionError("Redis down")
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        result = await tracker.get_loads(["agent_a", "agent_b"])
    assert result == {"agent_a": None, "agent_b": None}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_load_ignores_nan():
    """set_load() with NaN must not write to Redis — NaN load would permanently exclude agent."""
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        await tracker.set_load("agent_001", float("nan"))
    mock_redis.setex.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_load_ignores_inf():
    tracker = _make_tracker()
    mock_redis = AsyncMock()
    with patch.object(tracker, "_get_client", new=AsyncMock(return_value=mock_redis)):
        await tracker.set_load("agent_001", float("inf"))
    mock_redis.setex.assert_not_called()
