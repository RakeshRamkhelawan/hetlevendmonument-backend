"""Dag 7 -- ToolBroker-audit read endpoint (BPA-009 read-pad).

Read-only endpoint; the DB-backed write path is unchanged. Tests call the endpoint
function directly with a mocked tenant-bound repository.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.api.v1.tool_audit import router as tool_audit_router
from tests.helpers.limiet_request import echte_request


def _make_user(user_id: int = 1, roles=None, is_superuser: bool = False):
    user = MagicMock()
    user.id = user_id
    user.roles = roles or []
    user.is_superuser = is_superuser
    return user


def _make_log():
    log = MagicMock()
    log.id = 1
    log.agent_id = "agent-x"
    log.tool_name = "create_task"
    log.risk_level = "medium"
    log.status = "success"
    log.task_id = None
    log.duration_seconds = 0.5
    log.timestamp = datetime.now(timezone.utc)
    log.audit_hash = "abc123"
    return log


def _make_repo(logs, total):
    repo = MagicMock()
    repo.get_logs = AsyncMock(return_value=logs)
    repo.count_logs = AsyncMock(return_value=total)
    return repo


@pytest.mark.unit
async def test_list_tool_audit_logs_happy():
    admin = _make_user(1, roles=["admin"])
    repo = _make_repo([_make_log()], total=1)

    resp = await tool_audit_router.list_tool_audit_logs(
        request=echte_request(), current_user=admin, repo=repo, limit=50, offset=0
    )

    assert resp["success"] is True
    assert resp["total"] == 1
    assert len(resp["data"]) == 1
    assert resp["data"][0]["tool_name"] == "create_task"


@pytest.mark.unit
@pytest.mark.security
async def test_list_tool_audit_logs_non_admin_forbidden():
    user = _make_user(1, roles=["member"])
    repo = _make_repo([], total=0)

    with pytest.raises(HTTPException) as exc:
        await tool_audit_router.list_tool_audit_logs(
            request=echte_request(), current_user=user, repo=repo, limit=50, offset=0
        )
    assert exc.value.status_code == 403


@pytest.mark.unit
async def test_list_tool_audit_logs_empty_returns_ok():
    admin = _make_user(1, roles=["admin"])
    repo = _make_repo([], total=0)

    resp = await tool_audit_router.list_tool_audit_logs(
        request=echte_request(), current_user=admin, repo=repo, limit=50, offset=0
    )

    assert resp["success"] is True
    assert resp["data"] == []
    assert resp["total"] == 0


@pytest.mark.unit
@pytest.mark.security
async def test_repository_get_logs_is_tenant_scoped():
    """The read query must filter by tenant_id (no cross-tenant leakage)."""
    from src.core.tool_broker.audit_repository import ToolAuditRepository

    captured = {}

    db = MagicMock()

    async def _execute(stmt, *a, **k):
        captured["stmt"] = stmt
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    db.execute = _execute
    repo = ToolAuditRepository(db, tenant_id=7)

    await repo.get_logs(limit=50, offset=0)

    stmt = captured["stmt"]
    sql = str(stmt)
    assert "tool_audit_logs" in sql
    assert "tenant_id" in sql
    # Bound value must be the caller's tenant (7): a query on the wrong tenant would
    # still pass a mere "tenant_id" substring check (same strengthening as the DSAR test).
    assert 7 in set(stmt.compile().params.values())
