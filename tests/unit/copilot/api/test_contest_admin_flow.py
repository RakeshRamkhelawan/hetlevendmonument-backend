"""Dag 7 -- Contest admin-flow (GDPR art. 22 / GDPR-A22-001).

Admin queue + resolve endpoint + real submitter notification + audit entry.
Tests call the endpoint functions directly with mocked db/user (same style as
test_audit_endpoints.py). True cross-tenant isolation is additionally covered by
the query-filter assertion here; the RLS end-to-end path is an integration concern.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.core.copilot.api import audit_endpoints
from tests.helpers.limiet_request import echte_request


def _make_user(user_id: int = 1, roles=None, is_superuser: bool = False):
    user = MagicMock()
    user.id = user_id
    user.email = f"user{user_id}@example.com"
    user.roles = roles or []
    user.is_superuser = is_superuser
    return user


def _make_contest(tenant_id: int = 1, user_id: int = 5, status: str = "pending"):
    c = MagicMock()
    c.contest_id = uuid4()
    c.decision_id = uuid4()
    c.tenant_id = tenant_id
    c.user_id = user_id
    c.status = status
    c.submitted_at = datetime.now(timezone.utc)
    c.reason_category = "inaccurate"
    c.reason_text = "reason"
    c.resolution_text = None
    c.resolved_at = None
    c.resolver_user_id = None
    return c


def _db_with_executes(execute_side_effects):
    """AsyncSession mock; execute() yields the given results in order.

    Captures every executed statement in `session.executed_statements`.
    """
    session = AsyncMock()
    calls = list(execute_side_effects)
    idx = [0]
    session.executed_statements = []

    async def _execute(stmt, *args, **kwargs):
        session.executed_statements.append(stmt)
        if idx[0] < len(calls):
            r = calls[idx[0]]
            idx[0] += 1
            return r
        return MagicMock(scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: []))

    session.execute = _execute
    session.scalar = AsyncMock(return_value=0)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.begin_nested = MagicMock()
    return session


def _scalars_all(values):
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    return r


def _scalar_one_or_none(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


# ---------------------------------------------------------------------------
# 1.1 / 1.2 -- admin queue
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
async def test_list_contests_returns_own_tenant_contests():
    admin = _make_user(1, roles=["admin"])
    contest = _make_contest(tenant_id=7)
    db = _db_with_executes([MagicMock(), _scalars_all([contest])])  # rls set, then query
    db.scalar = AsyncMock(return_value=1)

    resp = await audit_endpoints.list_contests(
        request=echte_request(),
        current_user=admin, db=db, tenant_id=7, limit=50, offset=0
    )

    assert resp["success"] is True
    assert resp["total"] == 1
    assert len(resp["data"]) == 1
    assert resp["data"][0]["contest_id"] == str(contest.contest_id)


@pytest.mark.unit
@pytest.mark.security
async def test_list_contests_query_is_tenant_scoped():
    admin = _make_user(1, roles=["admin"])
    db = _db_with_executes([MagicMock(), _scalars_all([])])
    db.scalar = AsyncMock(return_value=0)

    await audit_endpoints.list_contests(request=echte_request(), current_user=admin, db=db, tenant_id=7, limit=50, offset=0)

    # The contest queries must filter on tenant_id AND bind the caller's tenant (7):
    # a query on the wrong tenant would still pass a mere "tenant_id" substring check
    # (same strengthening as the DSAR test).
    tenant_col_seen = False
    bound_values: set = set()
    for stmt in db.executed_statements:
        if "tenant_id" in str(stmt):
            tenant_col_seen = True
        try:
            bound_values.update(stmt.compile().params.values())
        except Exception:
            pass
    assert tenant_col_seen, "no tenant_id filter in the contest queries"
    assert 7 in bound_values, "contest query not bound to the caller's tenant"


@pytest.mark.unit
@pytest.mark.security
async def test_list_contests_non_admin_forbidden():
    user = _make_user(1, roles=["member"])
    db = _db_with_executes([])

    with pytest.raises(HTTPException) as exc:
        await audit_endpoints.list_contests(
            request=echte_request(),
            current_user=user, db=db, tenant_id=7, limit=50, offset=0
        )
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# 1.3 / 1.4 / 1.5 -- resolve
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
async def test_resolve_contest_non_admin_forbidden():
    user = _make_user(1, roles=["member"])
    db = _db_with_executes([])
    body = audit_endpoints.ContestResolveRequest(status="upheld", resolution_text="ok")

    with pytest.raises(HTTPException) as exc:
        await audit_endpoints.resolve_contest(
            request=echte_request(),
            contest_id=uuid4(), body=body, current_user=user, db=db, tenant_id=7, _csrf=None
        )
    assert exc.value.status_code == 403


@pytest.mark.unit
@pytest.mark.security
async def test_resolve_contest_happy_sets_resolution_fields():
    admin = _make_user(9, roles=["admin"])
    contest = _make_contest(tenant_id=7, user_id=5, status="pending")
    db = _db_with_executes([MagicMock(), _scalar_one_or_none(contest)])
    body = audit_endpoints.ContestResolveRequest(status="upheld", resolution_text="Reviewed")

    resp = await audit_endpoints.resolve_contest(
        request=echte_request(),
        contest_id=contest.contest_id, body=body, current_user=admin, db=db, tenant_id=7, _csrf=None
    )

    assert resp["success"] is True
    assert contest.status == "upheld"
    assert contest.resolution_text == "Reviewed"
    assert contest.resolver_user_id == 9
    assert contest.resolved_at is not None


@pytest.mark.unit
@pytest.mark.security
async def test_resolve_contest_already_resolved_conflict():
    admin = _make_user(9, roles=["admin"])
    contest = _make_contest(tenant_id=7, status="upheld")
    db = _db_with_executes([MagicMock(), _scalar_one_or_none(contest)])
    body = audit_endpoints.ContestResolveRequest(status="overturned", resolution_text="x")

    with pytest.raises(HTTPException) as exc:
        await audit_endpoints.resolve_contest(
            request=echte_request(),
            contest_id=contest.contest_id,
            body=body,
            current_user=admin,
            db=db,
            tenant_id=7,
            _csrf=None,
        )
    assert exc.value.status_code == 409


@pytest.mark.unit
@pytest.mark.security
async def test_resolve_contest_unknown_id_not_found():
    admin = _make_user(9, roles=["admin"])
    db = _db_with_executes([MagicMock(), _scalar_one_or_none(None)])
    body = audit_endpoints.ContestResolveRequest(status="upheld", resolution_text="x")

    with pytest.raises(HTTPException) as exc:
        await audit_endpoints.resolve_contest(
            request=echte_request(),
            contest_id=uuid4(), body=body, current_user=admin, db=db, tenant_id=7, _csrf=None
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# 1.6 notify (real) + 1.7 audit
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
async def test_resolve_contest_notifies_submitter():
    admin = _make_user(9, roles=["admin"])
    contest = _make_contest(tenant_id=7, user_id=5, status="pending")
    db = _db_with_executes([MagicMock(), _scalar_one_or_none(contest)])
    body = audit_endpoints.ContestResolveRequest(status="overturned", resolution_text="Done")

    await audit_endpoints.resolve_contest(
        request=echte_request(),
        contest_id=contest.contest_id, body=body, current_user=admin, db=db, tenant_id=7, _csrf=None
    )

    # A real Notification must be inserted for the submitter (user_id=5), not a log stub.
    from src.domains.notifications.models import Notification

    added = [c.args[0] for c in db.add.call_args_list if c.args]
    notifs = [o for o in added if isinstance(o, Notification)]
    assert len(notifs) == 1
    assert notifs[0].user_id == 5
    assert notifs[0].tenant_id == 7


@pytest.mark.unit
@pytest.mark.security
async def test_resolve_contest_writes_hash_chained_audit_entry():
    admin = _make_user(9, roles=["admin"])
    contest = _make_contest(tenant_id=7, user_id=5, status="pending")
    db = _db_with_executes([MagicMock(), _scalar_one_or_none(contest)])
    body = audit_endpoints.ContestResolveRequest(status="upheld", resolution_text="ok")

    with patch(
        "src.core.copilot.api.audit_endpoints.AuditService.log_action", new=AsyncMock()
    ) as mock_log:
        await audit_endpoints.resolve_contest(
            request=echte_request(),
            contest_id=contest.contest_id,
            body=body,
            current_user=admin,
            db=db,
            tenant_id=7,
            _csrf=None,
        )

    # Must route through AuditService (ADR-019 hash-chain), not a raw NULL-hash INSERT.
    mock_log.assert_awaited_once()
    kwargs = mock_log.await_args.kwargs
    assert kwargs["action"] == "contest_resolved"
    assert str(contest.contest_id) in kwargs["resource"]
    assert kwargs["tenant_id"] == 7
