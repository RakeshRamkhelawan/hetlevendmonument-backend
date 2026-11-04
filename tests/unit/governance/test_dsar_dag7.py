"""Dag 7 -- DSAR coverage for agentic_tasks + copilot conversation memory (GDPR-A17-004).

Covers, with mocked DB/Redis:
- the two DSARService helpers (_delete_agentic_tasks / _clear_copilot_sessions);
- the WIRING: that hard- and soft-delete both call the helpers, and that export fills the
  agentic_tasks + copilot_conversations sections.
Deep end-to-end assertions over a real PostgreSQL + Redis are a CI integration concern.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.governance.dsar_service import DSARService


def _svc() -> DSARService:
    db = AsyncMock()

    @asynccontextmanager
    async def _nested():
        yield

    # begin_nested() must behave as an async context manager (savepoint).
    db.begin_nested = lambda: _nested()
    return DSARService(db=db)


@pytest.mark.unit
async def test_delete_agentic_tasks_returns_rowcount():
    svc = _svc()
    result = MagicMock()
    result.rowcount = 3
    svc._db.execute = AsyncMock(return_value=result)

    deleted = await svc._delete_agentic_tasks(tenant_id=7, user_id="5")

    assert deleted == 3


@pytest.mark.unit
@pytest.mark.security
async def test_delete_agentic_tasks_is_tenant_and_user_scoped():
    svc = _svc()
    result = MagicMock()
    result.rowcount = 0
    captured = {}

    async def _execute(stmt, *a, **k):
        captured["stmt"] = stmt
        return result

    svc._db.execute = _execute

    await svc._delete_agentic_tasks(tenant_id=7, user_id="5")

    # Scoped by both tenant_id AND created_by, and the BOUND VALUES are the given
    # tenant/user (a query on the wrong tenant would still fail this).
    stmt = captured["stmt"]
    sql = str(stmt)
    assert "agentic_tasks" in sql
    assert "tenant_id" in sql and "created_by" in sql
    bound = set(stmt.compile().params.values())
    assert 7 in bound  # tenant_id
    assert 5 in bound  # created_by (coerced to int)


@pytest.mark.unit
async def test_delete_agentic_tasks_returns_zero_on_error():
    svc = _svc()
    svc._db.execute = AsyncMock(side_effect=RuntimeError("db down"))

    deleted = await svc._delete_agentic_tasks(tenant_id=7, user_id="5")

    assert deleted == 0


@pytest.mark.unit
async def test_clear_copilot_sessions_calls_memory_clear():
    svc = _svc()
    mem = AsyncMock()
    mem.clear_user_sessions = AsyncMock(return_value=2)

    with (
        patch("src.core.shared.redis_client.get_redis", new=AsyncMock(return_value=MagicMock())),
        patch("src.core.copilot.conversation_memory.ConversationMemory", return_value=mem),
    ):
        cleared = await svc._clear_copilot_sessions(tenant_id=7, user_id="5")

    assert cleared == 2
    mem.clear_user_sessions.assert_awaited_once_with(7, 5)


@pytest.mark.unit
@pytest.mark.security
async def test_clear_copilot_sessions_best_effort_on_redis_failure():
    """DSAR-delete must not fail when Redis is unavailable (best_effort)."""
    svc = _svc()

    with patch(
        "src.core.shared.redis_client.get_redis",
        new=AsyncMock(side_effect=ConnectionError("redis down")),
    ):
        cleared = await svc._clear_copilot_sessions(tenant_id=7, user_id="5")

    assert cleared == 0


# ---------------------------------------------------------------------------
# Wiring: the helpers must actually be invoked from delete/export (not just exist)
# ---------------------------------------------------------------------------


def _user_result(user: MagicMock) -> MagicMock:
    res = MagicMock()
    res.scalar_one_or_none.return_value = user
    res.scalars.return_value.all.return_value = []
    res.mappings.return_value.all.return_value = []
    return res


@pytest.mark.unit
@pytest.mark.security
async def test_hard_delete_wires_tasks_and_copilot():
    svc = _svc()
    user = MagicMock()
    user.id = 123
    user.tenant_id = 1
    user.is_active = True
    svc._db.execute = AsyncMock(return_value=_user_result(user))
    svc._create_audit_log = AsyncMock()
    svc._delete_agentic_tasks = AsyncMock(return_value=2)
    svc._clear_copilot_sessions = AsyncMock(return_value=1)

    await svc.delete_user_data(
        user_id="123", tenant_id=1, hard_delete=True, requested_by_user_id="admin", is_admin=True
    )

    svc._delete_agentic_tasks.assert_awaited_once_with(1, "123")
    svc._clear_copilot_sessions.assert_awaited_once_with(1, "123")


@pytest.mark.unit
@pytest.mark.security
async def test_soft_delete_wires_tasks_and_copilot():
    svc = _svc()
    user = MagicMock()
    user.id = 123
    user.tenant_id = 1
    user.is_active = True
    svc._db.execute = AsyncMock(return_value=_user_result(user))
    svc._create_audit_log = AsyncMock()
    svc._delete_agentic_tasks = AsyncMock(return_value=2)
    svc._clear_copilot_sessions = AsyncMock(return_value=1)

    await svc.delete_user_data(
        user_id="123", tenant_id=1, hard_delete=False, requested_by_user_id="123", is_admin=False
    )

    svc._delete_agentic_tasks.assert_awaited_once_with(1, "123")
    svc._clear_copilot_sessions.assert_awaited_once_with(1, "123")


@pytest.mark.unit
async def test_export_includes_task_and_copilot_sections():
    svc = _svc()
    user = MagicMock()
    user.id = 123
    user.email = "a@b.c"
    user.is_active = True
    user.created_at = None
    svc._verify_tenant_isolation = AsyncMock(return_value=user)
    svc._create_audit_log = AsyncMock()
    svc._db.execute = AsyncMock(return_value=_user_result(user))

    sid = "11111111-1111-1111-1111-111111111111"
    msg = MagicMock()
    msg.role = "user"
    msg.content = "hi"
    msg.timestamp = 1.0
    mem = AsyncMock()
    mem.get_user_sessions = AsyncMock(return_value=[sid])
    mem.get_history = AsyncMock(return_value=[msg])

    with (
        patch("src.core.shared.redis_client.get_redis", new=AsyncMock(return_value=MagicMock())),
        patch("src.core.copilot.conversation_memory.ConversationMemory", return_value=mem),
    ):
        result = await svc.export_user_data(
            user_id="123", tenant_id=1, requested_by_user_id="123", is_admin=False
        )

    # Sections 10 + 11 must run and be present in the export.
    assert "agentic_tasks" in result.data
    assert "copilot_conversations" in result.data
    assert len(result.data["copilot_conversations"]) == 1
    assert result.data["copilot_conversations"][0]["session_id"] == sid
