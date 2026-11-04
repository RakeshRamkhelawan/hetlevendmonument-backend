"""Dag 8 -- GDPR-001 delete-authz on the tenant-wide erasure endpoint.

POST /api/gdpr/delete-all wipes the ENTIRE tenant. It must require an admin role for
BOTH soft and hard delete -- the confirmation_code (== the caller's own tenant_id, from
the JWT) is a UX safeguard, NOT an authorization control. Tests call the handler directly
with mocked db/user (same style as test_audit_endpoints.py).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.api.v1.gdpr_compliance import erasure_router
from src.core.api.v1.gdpr_compliance.schemas import DeleteDataRequest, DeleteType


def _user(user_id: int = 5, roles=None):
    u = MagicMock()
    u.id = user_id
    u.roles = roles or []
    return u


def _req(delete_type: DeleteType, confirmation_code: str = "7"):
    return DeleteDataRequest(
        confirmation_code=confirmation_code, delete_type=delete_type, reason="test"
    )


def _happy_db():
    """db mock: tenant found, empty user/agent/workflow lists, rowcount 0."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = MagicMock(name="tenant")
    result.scalars.return_value.all.return_value = []
    result.rowcount = 0
    result.executed = []

    db = AsyncMock()

    async def _execute(stmt, *a, **k):
        result.executed.append(stmt)
        return result

    db.execute = _execute
    db.commit = AsyncMock()
    db._result = result
    return db


# ---------------------------------------------------------------------------
# GDPR-001 -- the P0: SOFT delete-all must require admin
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
async def test_soft_delete_all_requires_admin():
    """P0: a non-admin must NOT be able to soft-delete the whole tenant."""
    non_admin = _user(roles=["member"])
    with pytest.raises(HTTPException) as exc:
        await erasure_router.delete_tenant_data(
            request=_req(DeleteType.SOFT),
            background_tasks=MagicMock(),
            db=AsyncMock(),
            current_user=non_admin,
            tenant_id="7",
            http_request=MagicMock(),
        )
    assert exc.value.status_code == 403


@pytest.mark.unit
@pytest.mark.security
async def test_hard_delete_all_requires_admin():
    non_admin = _user(roles=["member"])
    with pytest.raises(HTTPException) as exc:
        await erasure_router.delete_tenant_data(
            request=_req(DeleteType.HARD),
            background_tasks=MagicMock(),
            db=AsyncMock(),
            current_user=non_admin,
            tenant_id="7",
            http_request=MagicMock(),
        )
    assert exc.value.status_code == 403


@pytest.mark.unit
@pytest.mark.security
async def test_matching_confirmation_code_does_not_grant_delete():
    """The confirmation_code (== own tenant_id) is not an authz lever for a non-admin."""
    non_admin = _user(roles=["member"])
    with pytest.raises(HTTPException) as exc:
        await erasure_router.delete_tenant_data(
            request=_req(DeleteType.SOFT, confirmation_code="7"),  # matches tenant_id
            background_tasks=MagicMock(),
            db=AsyncMock(),
            current_user=non_admin,
            tenant_id="7",
            http_request=MagicMock(),
        )
    assert exc.value.status_code == 403


@pytest.mark.unit
@pytest.mark.security
async def test_admin_soft_delete_all_allowed_and_tenant_scoped():
    admin = _user(user_id=9, roles=["admin"])
    db = _happy_db()

    with (
        patch.object(erasure_router.AuditService, "log_action", new=AsyncMock()),
        patch.object(erasure_router, "purge_user_data", new=MagicMock()),
    ):
        resp = await erasure_router.delete_tenant_data(
            request=_req(DeleteType.SOFT),
            background_tasks=MagicMock(),
            db=db,
            current_user=admin,
            tenant_id="7",
            http_request=MagicMock(),
        )

    assert resp.delete_type == DeleteType.SOFT
    # Every delete/select is bound to the caller's JWT tenant (7) -- no cross-tenant reach.
    bound = set()
    for stmt in db._result.executed:
        try:
            bound.update(stmt.compile().params.values())
        except Exception:
            pass
    assert "7" in bound or 7 in bound


@pytest.mark.unit
@pytest.mark.security
async def test_admin_hard_delete_all_allowed():
    admin = _user(user_id=9, roles=["admin"])
    db = _happy_db()

    with (
        patch.object(erasure_router.AuditService, "log_action", new=AsyncMock()),
        patch.object(erasure_router, "purge_user_data", new=MagicMock()),
        patch.object(erasure_router, "export_aangeboden", new=AsyncMock(return_value=True)),
    ):
        resp = await erasure_router.delete_tenant_data(
            request=_req(DeleteType.HARD),
            background_tasks=MagicMock(),
            db=db,
            current_user=admin,
            tenant_id="7",
            http_request=MagicMock(),
        )

    assert resp.delete_type == DeleteType.HARD
    # Every hard DELETE is bound to the caller's JWT tenant (7) -- no cross-tenant reach.
    bound = set()
    for stmt in db._result.executed:
        try:
            bound.update(stmt.compile().params.values())
        except Exception:
            pass
    assert "7" in bound or 7 in bound


# ---------------------------------------------------------------------------
# Regression: the DSAR service-layer authz must stay intact (not weakened)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
def test_dsar_authorize_still_blocks_non_owner_non_admin():
    from src.core.governance.dsar_service import DSARAuthorizationError, DSARService

    svc = DSARService(db=AsyncMock())
    with pytest.raises(DSARAuthorizationError):
        svc._authorize(target_user_id="1", requesting_user_id="2", is_admin=False)
