import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.security.security_audit_service import SecurityAuditService


@pytest.fixture
def service():
    return SecurityAuditService()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_recent_events_raises_without_tenant_context(service):
    """Without a tenant context, AuditLog queries must fail-secure (not return all tenants)."""
    db = AsyncMock()
    with patch("src.core.security.security_audit_service.get_tenant_id", return_value=None):
        with pytest.raises(RuntimeError, match="Tenant context required"):
            await service.get_recent_events(db=db)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_recent_events_explicit_tenant_id_overrides_context(service):
    """Passing an explicit tenant_id bypasses the ContextVar read."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    # Should not raise -- explicit tenant_id provided
    result = await service.get_recent_events(db=db, tenant_id=5)
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_security_summary_raises_without_tenant_context(service):
    db = AsyncMock()
    with patch("src.core.security.security_audit_service.get_tenant_id", return_value=None):
        with pytest.raises(RuntimeError, match="Tenant context required"):
            await service.get_security_summary(db=db)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_log_integrity_raises_without_tenant_context(service):
    db = AsyncMock()
    with patch("src.core.security.security_audit_service.get_tenant_id", return_value=None):
        with pytest.raises(RuntimeError, match="Tenant context required"):
            await service.verify_log_integrity(db=db)


@pytest.mark.unit
def test_bypass_contextvars_not_in_public_api():
    """Private ContextVars must not be in __all__ -- use TenantFilterBypass instead."""
    import src.core.database.tenant_query_filter as m

    assert "_bypass_tenant_filter" not in m.__all__
    assert "_force_real_filtering" not in m.__all__
    assert "TenantFilterBypass" in m.__all__
