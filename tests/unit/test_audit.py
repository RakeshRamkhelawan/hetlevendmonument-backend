import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import db_manager, initialize_database
from src.core.governance.audit import AuditService
from src.core.governance.models import AuditLog


@pytest.mark.asyncio
async def test_audit_log_creation(db_session: AsyncSession):
    """Test that audit logs can be created and retrieved."""
    tenant_id = 1
    action = "TEST_ACTION"
    resource = "test:resource:1"
    user_id = 1
    details = {"foo": "bar"}

    # Create log - pass the db_session so AuditService can persist
    log = await AuditService.log_action(
        tenant_id=tenant_id,
        action=action,
        resource=resource,
        user_id=user_id,
        details=details,
        session=db_session,
    )
    await db_session.flush()

    assert log.id is not None
    assert log.tenant_id == tenant_id
    assert log.action == action
    assert log.details == details

    # Retrieve log from same session
    result = await db_session.execute(select(AuditLog).where(AuditLog.id == log.id))
    retrieved_log = result.scalar_one()

    assert retrieved_log.tenant_id == tenant_id
    assert retrieved_log.action == action
    assert retrieved_log.resource == resource
    assert retrieved_log.user_id == user_id
    assert retrieved_log.details == details


@pytest.mark.asyncio
async def test_audit_log_immutability_check():
    """
    Verify that we don't have update methods exposed in the service.
    (True immutability is enforced by not having update methods)
    """
    assert not hasattr(AuditService, "update_log")
    assert not hasattr(AuditService, "delete_log")
