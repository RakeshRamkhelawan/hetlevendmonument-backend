"""
Unit tests for ConversationMemory.

Uses mocked Redis (AsyncMock) to verify key format, sliding window,
tenant isolation, and TTL without requiring a real Redis server.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.core.copilot.conversation_memory import (
    MAX_MESSAGES,
    TTL_SECONDS,
    ConversationMemory,
    ConversationMessage,
)


@pytest.fixture
def fake_redis() -> AsyncMock:
    """Return an AsyncMock that simulates a Redis list."""
    mock = AsyncMock()
    mock._data: dict[str, list[str]] = {}

    async def _rpush(key: str, value: str) -> int:
        mock._data.setdefault(key, [])
        mock._data[key].append(value)
        return len(mock._data[key])

    async def _ltrim(key: str, start: int, end: int) -> str:
        lst = mock._data.get(key, [])
        if not lst:
            return "OK"
        length = len(lst)

        def _idx(i: int) -> int:
            return i if i >= 0 else length + i

        s = max(0, _idx(start))
        e = min(length - 1, _idx(end))
        mock._data[key] = lst[s : e + 1]
        return "OK"

    async def _expire(key: str, seconds: int) -> int:
        return 1

    async def _lrange(key: str, start: int, end: int) -> list[str]:
        lst = mock._data.get(key, [])
        if end == -1:
            return lst[start:]
        return lst[start : end + 1]

    async def _delete(key: str) -> int:
        return 1 if mock._data.pop(key, None) is not None else 0

    mock._sets: dict[str, set[str]] = {}

    async def _sadd(key: str, *values: str) -> int:
        mock._sets.setdefault(key, set())
        before = len(mock._sets[key])
        mock._sets[key].update(values)
        return len(mock._sets[key]) - before

    async def _smembers(key: str) -> set[bytes]:
        return {v.encode() for v in mock._sets.get(key, set())}

    mock.sadd.side_effect = _sadd
    mock.smembers.side_effect = _smembers
    mock.rpush.side_effect = _rpush
    mock.ltrim.side_effect = _ltrim
    mock.expire.side_effect = _expire
    mock.lrange.side_effect = _lrange
    mock.delete.side_effect = _delete
    return mock


@pytest.fixture
def memory(fake_redis: AsyncMock) -> ConversationMemory:
    return ConversationMemory(redis=fake_redis)


@pytest.mark.unit
async def test_add_then_get_history_returns_in_order(
    memory: ConversationMemory, fake_redis: AsyncMock
) -> None:
    session_id = UUID("12345678-1234-5678-1234-567812345678")
    await memory.add(tenant_id=1, session_id=session_id, role="user", content="hello")
    await memory.add(tenant_id=1, session_id=session_id, role="assistant", content="hi")

    history = await memory.get_history(tenant_id=1, session_id=session_id)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "hello"
    assert history[1].role == "assistant"
    assert history[1].content == "hi"


@pytest.mark.unit
async def test_window_trims_to_20_messages(
    memory: ConversationMemory, fake_redis: AsyncMock
) -> None:
    session_id = UUID("12345678-1234-5678-1234-567812345678")
    for i in range(25):
        await memory.add(tenant_id=1, session_id=session_id, role="user", content=f"msg-{i}")

    history = await memory.get_history(tenant_id=1, session_id=session_id)
    assert len(history) == MAX_MESSAGES
    assert history[0].content == "msg-5"
    assert history[-1].content == "msg-24"


@pytest.mark.unit
async def test_clear_removes_all_messages(
    memory: ConversationMemory, fake_redis: AsyncMock
) -> None:
    session_id = UUID("12345678-1234-5678-1234-567812345678")
    await memory.add(tenant_id=1, session_id=session_id, role="user", content="hello")
    await memory.clear(tenant_id=1, session_id=session_id)

    history = await memory.get_history(tenant_id=1, session_id=session_id)
    assert history == []


@pytest.mark.unit
async def test_keyed_by_tenant_and_session_isolates_data(
    memory: ConversationMemory, fake_redis: AsyncMock
) -> None:
    session_a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    session_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    await memory.add(tenant_id=1, session_id=session_a, role="user", content="tenant1-a")
    await memory.add(tenant_id=2, session_id=session_a, role="user", content="tenant2-a")
    await memory.add(tenant_id=1, session_id=session_b, role="user", content="tenant1-b")

    hist_1_a = await memory.get_history(tenant_id=1, session_id=session_a)
    hist_2_a = await memory.get_history(tenant_id=2, session_id=session_a)
    hist_1_b = await memory.get_history(tenant_id=1, session_id=session_b)

    assert len(hist_1_a) == 1
    assert hist_1_a[0].content == "tenant1-a"
    assert len(hist_2_a) == 1
    assert hist_2_a[0].content == "tenant2-a"
    assert len(hist_1_b) == 1
    assert hist_1_b[0].content == "tenant1-b"


@pytest.mark.unit
async def test_ttl_set_to_3600_seconds(memory: ConversationMemory, fake_redis: AsyncMock) -> None:
    session_id = UUID("12345678-1234-5678-1234-567812345678")
    await memory.add(tenant_id=1, session_id=session_id, role="user", content="hello")

    key = memory._key(tenant_id=1, session_id=session_id)
    assert key == f"copilot:session:1:{session_id}"
    fake_redis.expire.assert_awaited()
    # Verify the TTL value passed to expire
    call_args = fake_redis.expire.await_args
    assert call_args is not None
    assert call_args.args[0] == key
    assert call_args.args[1] == TTL_SECONDS


# ---------------------------------------------------------------------------
# Dag 7 -- user -> session index (GDPR-A17 per-user copilot erasure)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_add_with_user_id_indexes_session(
    memory: ConversationMemory, fake_redis: AsyncMock
) -> None:
    session_id = UUID("12345678-1234-5678-1234-567812345678")
    await memory.add(tenant_id=1, session_id=session_id, role="user", content="hi", user_id=5)

    index_key = "copilot:user_sessions:1:5"
    assert str(session_id) in fake_redis._sets.get(index_key, set())


@pytest.mark.unit
async def test_add_without_user_id_does_not_index(
    memory: ConversationMemory, fake_redis: AsyncMock
) -> None:
    session_id = UUID("12345678-1234-5678-1234-567812345678")
    await memory.add(tenant_id=1, session_id=session_id, role="user", content="hi")

    fake_redis.sadd.assert_not_awaited()


@pytest.mark.unit
async def test_get_user_sessions_returns_indexed_ids(
    memory: ConversationMemory, fake_redis: AsyncMock
) -> None:
    s1 = UUID("11111111-1111-1111-1111-111111111111")
    s2 = UUID("22222222-2222-2222-2222-222222222222")
    await memory.add(tenant_id=1, session_id=s1, role="user", content="a", user_id=5)
    await memory.add(tenant_id=1, session_id=s2, role="user", content="b", user_id=5)

    sessions = await memory.get_user_sessions(tenant_id=1, user_id=5)
    assert set(sessions) == {str(s1), str(s2)}


@pytest.mark.unit
async def test_clear_user_sessions_deletes_each_session_and_index(
    memory: ConversationMemory, fake_redis: AsyncMock
) -> None:
    s1 = UUID("11111111-1111-1111-1111-111111111111")
    await memory.add(tenant_id=1, session_id=s1, role="user", content="a", user_id=5)

    deleted = await memory.clear_user_sessions(tenant_id=1, user_id=5)

    assert deleted == 1
    deleted_keys = {c.args[0] for c in fake_redis.delete.await_args_list}
    assert f"copilot:session:1:{s1}" in deleted_keys
    assert "copilot:user_sessions:1:5" in deleted_keys


@pytest.mark.unit
async def test_clear_user_sessions_tenant_scoped(
    memory: ConversationMemory, fake_redis: AsyncMock
) -> None:
    s1 = UUID("11111111-1111-1111-1111-111111111111")
    await memory.add(tenant_id=1, session_id=s1, role="user", content="a", user_id=5)
    # Same user_id in a different tenant must not be touched.
    deleted = await memory.clear_user_sessions(tenant_id=2, user_id=5)

    assert deleted == 0
    deleted_keys = {c.args[0] for c in fake_redis.delete.await_args_list}
    assert f"copilot:session:1:{s1}" not in deleted_keys
