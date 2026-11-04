"""GOV-004 -- SecurityAuditService must use the canonical HashChainVerifier and write
to the real audit_hash/previous_hash columns, not an in-memory _last_hash +
JSON event_metadata scheme (Sprint Dag 1 Groep 2, AUDIT-ARCH-2026-07-02)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.hash_chain import HashChainVerifier
from src.core.governance.models import AuditLog
from src.core.security.security_audit_service import SecurityAuditService
from src.core.security.types import SecurityEventType, ThreatLevel


@pytest.fixture
def mock_db():
    mock = AsyncMock(spec=AsyncSession)
    mock.add = MagicMock()
    mock.commit = AsyncMock()
    mock.rollback = AsyncMock()
    prev_hash_result = MagicMock()
    prev_hash_result.scalar_one_or_none = MagicMock(return_value=None)
    mock.execute = AsyncMock(return_value=prev_hash_result)
    return mock


@pytest.fixture
def audit_service():
    return SecurityAuditService()


@pytest.mark.asyncio
async def test_log_event_sets_audit_hash_column_via_hash_chain_verifier(audit_service, mock_db):
    with patch("src.core.security.security_audit_service.get_tenant_id", return_value=1):
        event_id = await audit_service.log_event(
            db=mock_db,
            event_type=SecurityEventType.LOGIN_SUCCESS,
            severity=ThreatLevel.LOW,
            source_ip="192.168.1.100",
            endpoint="/api/v1/auth/login",
            description="hash chain test",
            user_id=123,
            tenant_id=1,
        )

    assert event_id is not None
    added_entry = mock_db.add.call_args[0][0]
    assert added_entry.audit_hash is not None
    assert added_entry.audit_hash != ""


@pytest.mark.asyncio
async def test_log_event_no_longer_stores_hash_in_json_metadata(audit_service, mock_db):
    with patch("src.core.security.security_audit_service.get_tenant_id", return_value=1):
        await audit_service.log_event(
            db=mock_db,
            event_type=SecurityEventType.LOGIN_SUCCESS,
            severity=ThreatLevel.LOW,
            source_ip="192.168.1.100",
            endpoint="/api/v1/auth/login",
            description="hash chain test",
            tenant_id=1,
        )

    added_entry = mock_db.add.call_args[0][0]
    assert "log_hash" not in (added_entry.event_metadata or {})
    assert "previous_hash" not in (added_entry.event_metadata or {})


@pytest.mark.asyncio
async def test_log_event_stores_tenant_id_as_int_not_str(audit_service, mock_db):
    """Pre-existing bug fixed alongside GOV-004: AuditLog.tenant_id is Mapped[int | None]
    but log_event() was storing str(tenant_id)."""
    with patch("src.core.security.security_audit_service.get_tenant_id", return_value=1):
        await audit_service.log_event(
            db=mock_db,
            event_type=SecurityEventType.LOGIN_SUCCESS,
            severity=ThreatLevel.LOW,
            source_ip="192.168.1.100",
            endpoint="/api/v1/auth/login",
            description="tenant id type test",
            tenant_id=1,
        )

    added_entry = mock_db.add.call_args[0][0]
    assert added_entry.tenant_id == 1
    assert isinstance(added_entry.tenant_id, int)


@pytest.mark.asyncio
async def test_log_event_skips_write_without_resolvable_tenant_id(audit_service, mock_db):
    with patch("src.core.security.security_audit_service.get_tenant_id", return_value=None):
        event_id = await audit_service.log_event(
            db=mock_db,
            event_type=SecurityEventType.LOGIN_SUCCESS,
            severity=ThreatLevel.LOW,
            source_ip="192.168.1.100",
            endpoint="/api/v1/auth/login",
            description="no tenant",
        )

    assert event_id is None
    mock_db.add.assert_not_called()


def _make_chained_log(id_: int, tenant_id: int, action: str, resource: str, previous_hash):
    from datetime import datetime, timezone

    log = AuditLog(
        tenant_id=tenant_id,
        action=action,
        resource=resource,
        event_type=action,
        timestamp=datetime.now(timezone.utc),
    )
    log.id = id_
    log.previous_hash = previous_hash
    verifier = HashChainVerifier(db_session=MagicMock())
    log.audit_hash = verifier._compute_hash(log, previous_hash)
    return log


@pytest.mark.asyncio
async def test_verify_log_integrity_reads_real_audit_hash_columns(audit_service):
    """Regression guard: after GOV-004, verify_log_integrity() must recompute against
    the real audit_hash/previous_hash columns -- not the retired JSON event_metadata
    scheme (which no longer gets populated and would make this silently always pass)."""
    log1 = _make_chained_log(1, tenant_id=1, action="LOGIN", resource="user:1", previous_hash=None)
    log2 = _make_chained_log(
        2, tenant_id=1, action="LOGOUT", resource="user:1", previous_hash=log1.audit_hash
    )

    db = AsyncMock(spec=AsyncSession)
    scalars_result = MagicMock()
    # Sinds ADR-036 OP-122 haalt deze verifier het venster met `ORDER BY timestamp DESC` op --
    # de database levert dus NIEUWSTE-EERST -- en doet daarna een tweede query voor de
    # basislijn. De mock modelleert beide; zonder de tweede krijgt de basislijn een MagicMock in
    # plaats van een hash, en meldt de eerste rij een breuk die er niet is.
    scalars_result.all = MagicMock(return_value=[log2, log1])
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)
    basislijn = MagicMock()
    basislijn.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(side_effect=[execute_result, basislijn])

    with patch("src.core.security.security_audit_service.get_tenant_id", return_value=1):
        result = await audit_service.verify_log_integrity(db=db, tenant_id=1)

    assert result["verified"] is True
    assert result["entries_checked"] == 2
    assert result["tampered_entries"] == []


@pytest.mark.asyncio
async def test_verify_log_integrity_detects_tampered_audit_hash_column():
    """A mutated audit_hash column (tampering) must be detected -- this is the exact
    tamper-detection regression a security reviewer flagged: verify_log_integrity()
    previously kept reading the retired JSON metadata fields and would report
    verified=True regardless of real column tampering."""
    service = SecurityAuditService()
    log1 = _make_chained_log(1, tenant_id=1, action="LOGIN", resource="user:1", previous_hash=None)
    log2 = _make_chained_log(
        2, tenant_id=1, action="LOGOUT", resource="user:1", previous_hash=log1.audit_hash
    )
    log2.audit_hash = "tampered" * 8  # simulate a modified hash column

    db = AsyncMock(spec=AsyncSession)
    scalars_result = MagicMock()
    # Sinds ADR-036 OP-122 haalt deze verifier het venster met `ORDER BY timestamp DESC` op --
    # de database levert dus NIEUWSTE-EERST -- en doet daarna een tweede query voor de
    # basislijn. De mock modelleert beide; zonder de tweede krijgt de basislijn een MagicMock in
    # plaats van een hash, en meldt de eerste rij een breuk die er niet is.
    scalars_result.all = MagicMock(return_value=[log2, log1])
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)
    basislijn = MagicMock()
    basislijn.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(side_effect=[execute_result, basislijn])

    with patch("src.core.security.security_audit_service.get_tenant_id", return_value=1):
        result = await service.verify_log_integrity(db=db, tenant_id=1)

    assert result["verified"] is False
    assert any(entry["issue"] == "hash_mismatch" for entry in result["tampered_entries"])
