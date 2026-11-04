"""GOV-002/GOV-003 -- AuditService consolidation naar hash-chain-pad
(Sprint Dag 1 Groep 2, AUDIT-ARCH-2026-07-02).

Covers the two non-canonical AuditService paths:
- governance/services/audit_service.py (21 call-sites, has a DB session) -- now
  populates the hash chain in-place via HashChainVerifier.
- audit/audit_service.py (5 hot-path call-sites, no DB session) -- now enqueues a
  hash-chained write via write_audit_log_task (Dramatiq, ADR-006) when a tenant_id
  is resolvable.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.governance.services.audit_service import AuditService as ServicesAuditService


@pytest.fixture
def mock_db_session_with_chain():
    mock_session = AsyncMock()
    mock_session.add = Mock()
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.rollback = AsyncMock()
    nested_cm = MagicMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=False)
    mock_session.begin_nested = MagicMock(return_value=nested_cm)
    prev_hash_result = MagicMock()
    prev_hash_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_session.execute = AsyncMock(return_value=prev_hash_result)
    return mock_session


@pytest.mark.asyncio
async def test_log_event_populates_hash_chain_when_tenant_id_given(mock_db_session_with_chain):
    """GOV-003: with a tenant_id, log_event() must populate audit_hash/previous_hash
    via the canonical HashChainVerifier -- previously this path never set them."""
    result = await ServicesAuditService.log_event(
        db=mock_db_session_with_chain,
        event_type="LOGIN_SUCCESS",
        severity="low",
        source_ip="127.0.0.1",
        endpoint="/api/test",
        description="chain test",
        tenant_id=42,
    )

    assert result is True
    added_entry = mock_db_session_with_chain.add.call_args[0][0]
    assert added_entry.audit_hash is not None
    assert added_entry.audit_hash != ""
    # ADR-019: flush() semantics preserved -- caller owns the commit boundary.
    mock_db_session_with_chain.commit.assert_not_called()
    mock_db_session_with_chain.flush.assert_called_once()


@pytest.mark.asyncio
async def test_log_event_without_tenant_id_stays_ungated_but_unchained(
    mock_db_session_with_chain,
):
    """No tenant_id -- hash chain cannot be scoped per-tenant, so the entry is written
    without a hash (degraded mode), consistent with governance/audit.py's own contract.
    This must NOT regress the existing no-tenant-id call-sites (most of the 21)."""
    result = await ServicesAuditService.log_event(
        db=mock_db_session_with_chain,
        event_type="SYSTEM_EVENT",
        severity="low",
        source_ip="127.0.0.1",
        endpoint="/api/test",
        description="no tenant",
    )

    assert result is True
    added_entry = mock_db_session_with_chain.add.call_args[0][0]
    assert added_entry.audit_hash is None


@pytest.mark.asyncio
async def test_log_security_event_enqueues_hash_chained_write_when_tenant_resolvable():
    """GOV-002: audit/audit_service.py::log_security_event() must enqueue a real
    hash-chained AuditLog write when a tenant_id is resolvable, not just log to the
    Python logger with no persisted record."""
    from src.core.audit.audit_service import AuditService as LoggerAuditService

    service = LoggerAuditService()
    with (
        patch("src.core.audit.audit_service.get_tenant_id", return_value=7),
        patch("src.core.audit.audit_service.write_audit_log_task") as mock_task,
    ):
        result = await service.log_security_event(event_type="token_revoked", user_id=123)

    assert result is True
    mock_task.send.assert_called_once()
    _, kwargs = mock_task.send.call_args
    assert kwargs["tenant_id"] == 7
    assert kwargs["action"] == "token_revoked"


@pytest.mark.asyncio
async def test_log_security_event_skips_db_write_without_tenant_id():
    """No tenant_id resolvable (system-wide event) -> stays logger-only, matching
    governance/audit.py::AuditService.log_action()'s own tenant-required contract."""
    from src.core.audit.audit_service import AuditService as LoggerAuditService

    service = LoggerAuditService()
    with (
        patch("src.core.audit.audit_service.get_tenant_id", return_value=None),
        patch("src.core.audit.audit_service.write_audit_log_task") as mock_task,
    ):
        result = await service.log_security_event(event_type="system_startup")

    assert result is True
    mock_task.send.assert_not_called()


@pytest.mark.asyncio
async def test_log_security_event_counts_a_failed_enqueue() -> None:
    """ADR-036 OP-06: een mislukte Dramatiq-enqueue was voorheen alleen een ERROR-logregel --
    geen enkel signaal waarop een operator kan alarmeren dat de ADR-019-keten een rij mist.
    Deze test bewijst dat de mislukking nu ook een Prometheus-counter verhoogt.
    """
    from src.core.audit.audit_service import AUDIT_HASH_CHAIN_ENQUEUE_FAILURES_TOTAL
    from src.core.audit.audit_service import AuditService as LoggerAuditService

    before = AUDIT_HASH_CHAIN_ENQUEUE_FAILURES_TOTAL.labels(event_type="token_revoked")._value.get()

    service = LoggerAuditService()
    with (
        patch("src.core.audit.audit_service.get_tenant_id", return_value=7),
        patch("src.core.audit.audit_service.write_audit_log_task") as mock_task,
    ):
        mock_task.send.side_effect = RuntimeError("broker unreachable")
        result = await service.log_security_event(event_type="token_revoked", user_id=123)

    # Fail-open blijft bewust behouden -- geen enkele aanroeper leest de returnwaarde
    # (`git grep -n "= await log_security_event"` geeft nul treffers), en de structured-log-
    # schrijf IS gelukt. Deze test bewaakt de OBSERVEERBAARHEID, niet een gedragswijziging.
    assert result is True

    after = AUDIT_HASH_CHAIN_ENQUEUE_FAILURES_TOTAL.labels(event_type="token_revoked")._value.get()
    assert after == before + 1, (
        "Een mislukte hash-chain-enqueue verhoogt AUDIT_HASH_CHAIN_ENQUEUE_FAILURES_TOTAL niet -- "
        "de mislukking blijft dan onzichtbaar voor monitoring, ook al is hij wel geLOGD."
    )
