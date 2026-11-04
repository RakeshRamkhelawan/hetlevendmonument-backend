"""
F3 self-healing -- Redis-backed state persistence tests (TDD RED phase).

Covers:
1. Attempt counts ARE written to Redis with the correct key prefix
2. Cooldown timestamps ARE written to Redis with the correct key prefix
3. Attempt count stored in Redis is read back on subsequent calls
4. Redis ConnectionError falls back gracefully to in-memory state
5. Default (no redis_client) uses in-memory-only (no regression from F2)
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.core.autonomy.self_healing_system import RepairPlan, RepairStrategy, SelfHealingSystem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan(
    failure_id: str = "f3-test",
    strategy: RepairStrategy = RepairStrategy.RESTART,
) -> RepairPlan:
    return RepairPlan(
        plan_id=f"plan_{failure_id}",
        failure_id=failure_id,
        actions=["restart_component"],
        estimated_duration=timedelta(seconds=5),
        success_probability=0.9,
        strategy=strategy,
    )


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _make_redis_mock() -> AsyncMock:
    """Return an AsyncMock that simulates an empty Redis (no stored values)."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    return mock


# ---------------------------------------------------------------------------
# 1. Redis writes
# ---------------------------------------------------------------------------


class TestRedisStateWrites:
    """Repair execution must persist attempt + cooldown state to Redis."""

    def _written_keys(self, mock_redis: AsyncMock) -> list:  # type: ignore[type-arg]
        return [str(call.args[0]) for call in mock_redis.set.call_args_list]

    def test_attempt_count_key_written_to_redis(self) -> None:
        mock_redis = _make_redis_mock()
        system = SelfHealingSystem(redis_client=mock_redis)
        _run(system.execute_repair_plan(_make_plan()))
        keys = self._written_keys(mock_redis)
        assert any(
            "healing:attempts" in k for k in keys
        ), f"Expected 'healing:attempts' key in Redis writes; got: {keys}"

    def test_cooldown_key_written_to_redis(self) -> None:
        mock_redis = _make_redis_mock()
        system = SelfHealingSystem(redis_client=mock_redis)
        _run(system.execute_repair_plan(_make_plan()))
        keys = self._written_keys(mock_redis)
        assert any(
            "healing:cooldown" in k for k in keys
        ), f"Expected 'healing:cooldown' key in Redis writes; got: {keys}"

    def test_attempt_key_includes_failure_id(self) -> None:
        mock_redis = _make_redis_mock()
        system = SelfHealingSystem(redis_client=mock_redis)
        _run(system.execute_repair_plan(_make_plan(failure_id="my-failure")))
        keys = self._written_keys(mock_redis)
        assert any("my-failure" in k and "attempts" in k for k in keys)


# ---------------------------------------------------------------------------
# 2. Redis reads (previously stored state is honoured)
# ---------------------------------------------------------------------------


class TestRedisStateReads:
    """State stored in Redis on instance A must be read back by instance B."""

    def test_attempt_count_read_from_redis(self) -> None:
        """If Redis reports count=2, a new instance must start from 2 (not 0)."""
        mock_redis = _make_redis_mock()

        async def _get(key: str) -> str | None:
            if "healing:attempts" in key and "f3-test" in key:
                return "2"
            return None

        mock_redis.get = AsyncMock(side_effect=_get)

        system = SelfHealingSystem(redis_client=mock_redis)
        # Must bypass cooldown so we can execute immediately
        system._repair_cooldowns["f3-test"] = datetime.now(timezone.utc) - timedelta(seconds=61)
        plan = _make_plan()
        result = _run(system.execute_repair_plan(plan))
        # count was 2 from Redis; +1 = 3, still within limit -> success
        assert result.success is True
        assert system.get_attempt_count("f3-test") == 3

    def test_cooldown_read_from_redis_blocks_attempt(self) -> None:
        """If Redis reports a recent cooldown, the attempt must be blocked."""
        mock_redis = _make_redis_mock()
        recent_ts = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()

        async def _get(key: str) -> str | None:
            if "healing:cooldown" in key and "f3-test" in key:
                return recent_ts
            return None

        mock_redis.get = AsyncMock(side_effect=_get)

        system = SelfHealingSystem(redis_client=mock_redis)
        plan = _make_plan()
        result = _run(system.execute_repair_plan(plan))
        # Cooldown from Redis (10 s ago) blocks the attempt
        assert result.success is False
        assert "cooldown" in result.final_status.lower()


# ---------------------------------------------------------------------------
# 3. Graceful fallback on Redis errors
# ---------------------------------------------------------------------------


class TestRedisGracefulFallback:
    """Redis errors must NOT propagate -- in-memory fallback kicks in."""

    def test_redis_get_error_falls_back_to_in_memory(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        mock_redis.set = AsyncMock(return_value=True)
        system = SelfHealingSystem(redis_client=mock_redis)
        plan = _make_plan()
        result = _run(system.execute_repair_plan(plan))
        assert result.success is True
        assert system.get_attempt_count("f3-test") == 1

    def test_redis_set_error_does_not_break_repair(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis down"))
        system = SelfHealingSystem(redis_client=mock_redis)
        plan = _make_plan()
        result = _run(system.execute_repair_plan(plan))
        assert result.success is True

    def test_no_redis_client_uses_in_memory(self) -> None:
        """Default construction (no redis_client) must work exactly as before."""
        system = SelfHealingSystem()  # redis_client=None
        plan = _make_plan()
        result = _run(system.execute_repair_plan(plan))
        assert result.success is True
        assert system.get_attempt_count("f3-test") == 1
