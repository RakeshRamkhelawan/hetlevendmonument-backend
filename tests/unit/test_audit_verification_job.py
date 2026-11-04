"""
Unit tests for AuditTrailVerificationJob.

Sprint 7, Task 3.3 - TDD implementation of audit trail verification job.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_audit_trail_verification_job_class_exists():
    """Job class should exist with required methods."""
    from src.core.jobs.audit_verification import AuditTrailVerificationJob

    assert hasattr(AuditTrailVerificationJob, "run")
    assert hasattr(AuditTrailVerificationJob, "verify_tenant")
    assert hasattr(AuditTrailVerificationJob, "store_result")


@pytest.mark.asyncio
async def test_job_result_dataclass_exists():
    """JobResult dataclass should exist with all required fields."""
    from src.core.jobs.audit_verification import JobResult

    result = JobResult(
        total_tenants=2,
        verified_tenants=2,
        failed_tenants=0,
        total_entries_checked=100,
        total_broken_chains=0,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_ms=150.5,
    )

    assert result.total_tenants == 2
    assert result.verified_tenants == 2
    assert result.failed_tenants == 0
    assert result.total_entries_checked == 100
    assert result.total_broken_chains == 0
    assert isinstance(result.duration_ms, float)


@pytest.mark.asyncio
async def test_tenant_verification_result_dataclass_exists():
    """TenantVerificationResult dataclass should exist with all required fields."""
    from src.core.jobs.audit_verification import TenantVerificationResult

    result = TenantVerificationResult(
        tenant_id=1,
        is_valid=True,
        total_entries=50,
        verified_entries=50,
        broken_at_entry_id=None,
        checked_at=datetime.now(timezone.utc),
        verification_time_ms=75.2,
    )

    assert result.tenant_id == 1
    assert result.is_valid is True
    assert result.total_entries == 50
    assert result.verified_entries == 50
    assert result.broken_at_entry_id is None
    assert isinstance(result.verification_time_ms, float)


@pytest.mark.asyncio
async def test_job_initialization_requires_db_session():
    """Job should require db_session in constructor."""
    from src.core.jobs.audit_verification import AuditTrailVerificationJob

    mock_session = AsyncMock()
    job = AuditTrailVerificationJob(db_session=mock_session)

    assert job.db_session is mock_session


@pytest.mark.asyncio
async def test_run_returns_correct_job_result_structure():
    """run() should return JobResult with correct structure."""
    from src.core.jobs.audit_verification import AuditTrailVerificationJob, JobResult

    mock_session = AsyncMock()
    job = AuditTrailVerificationJob(db_session=mock_session)

    # Mock tenant query to return empty list
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    result = await job.run()

    assert isinstance(result, JobResult)
    assert result.total_tenants == 0
    assert result.verified_tenants == 0
    assert result.failed_tenants == 0


@pytest.mark.asyncio
async def test_run_iterates_over_all_active_tenants():
    """run() should iterate over all active tenants."""
    from src.core.jobs.audit_verification import AuditTrailVerificationJob
    from src.core.models.rbac_models import Tenant

    mock_session = AsyncMock()
    job = AuditTrailVerificationJob(db_session=mock_session)

    # Create mock tenants
    tenant1 = MagicMock(spec=Tenant)
    tenant1.id = 1
    tenant1.is_active = True

    tenant2 = MagicMock(spec=Tenant)
    tenant2.id = 2
    tenant2.is_active = True

    # Mock tenant query
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [tenant1, tenant2]
    mock_session.execute.return_value = mock_result

    # Mock verify_tenant and store_result
    job.verify_tenant = AsyncMock(
        return_value=MagicMock(
            tenant_id=1,
            is_valid=True,
            total_entries=10,
            verified_entries=10,
            broken_at_entry_id=None,
            checked_at=datetime.now(timezone.utc),
            verification_time_ms=50.0,
        )
    )
    job.store_result = AsyncMock()

    result = await job.run()

    assert result.total_tenants == 2
    assert job.verify_tenant.call_count == 2
    assert job.store_result.call_count == 2


@pytest.mark.asyncio
async def test_failed_tenant_verification_does_not_stop_job():
    """Failed tenant verification should not stop job from processing other tenants."""
    from src.core.jobs.audit_verification import AuditTrailVerificationJob
    from src.core.models.rbac_models import Tenant

    mock_session = AsyncMock()
    job = AuditTrailVerificationJob(db_session=mock_session)

    # Create mock tenants
    tenant1 = MagicMock(spec=Tenant)
    tenant1.id = 1
    tenant1.is_active = True

    tenant2 = MagicMock(spec=Tenant)
    tenant2.id = 2
    tenant2.is_active = True

    tenant3 = MagicMock(spec=Tenant)
    tenant3.id = 3
    tenant3.is_active = True

    # Mock tenant query
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [tenant1, tenant2, tenant3]
    mock_session.execute.return_value = mock_result

    # Mock verify_tenant with one failure
    async def mock_verify(tenant_id: int):
        if tenant_id == 2:
            raise Exception("Verification failed")
        return MagicMock(
            tenant_id=tenant_id,
            is_valid=True,
            total_entries=10,
            verified_entries=10,
            broken_at_entry_id=None,
            checked_at=datetime.now(timezone.utc),
            verification_time_ms=50.0,
        )

    job.verify_tenant = AsyncMock(side_effect=mock_verify)
    job.store_result = AsyncMock()

    result = await job.run()

    assert result.total_tenants == 3
    assert result.verified_tenants == 2
    assert result.failed_tenants == 1
    assert job.verify_tenant.call_count == 3


@pytest.mark.asyncio
async def test_verify_tenant_uses_hash_chain_verifier():
    """verify_tenant() should use HashChainVerifier to verify chain."""
    from src.core.governance.hash_chain import ChainVerificationResult
    from src.core.jobs.audit_verification import AuditTrailVerificationJob, TenantVerificationResult

    mock_session = AsyncMock()
    # `verify_tenant` doet sinds ADR-036 OP-120 twee eigen queries: het anker ophalen (voor het
    # knippunt) en de laagste gesleutelde `id`. Een kale AsyncMock geeft daar een coroutine terug
    # waar de code een Result verwacht; vandaar een expliciet resultaat met SYNCHRONE
    # `scalar_one_or_none`, net als een echte `Result`.
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    job = AuditTrailVerificationJob(db_session=mock_session)

    # Mock HashChainVerifier
    mock_chain_result = ChainVerificationResult(
        is_valid=True,
        total_entries=100,
        verified_entries=100,
        broken_at_entry_id=None,
        broken_at_index=None,
        expected_hash=None,
        actual_hash=None,
        verification_time_ms=120.5,
        tenant_id=1,
        checked_at=datetime.now(timezone.utc),
    )

    with patch("src.core.jobs.audit_verification.HashChainVerifier") as mock_verifier_cls:
        mock_verifier = MagicMock()
        mock_verifier.verify_chain = AsyncMock(return_value=mock_chain_result)
        mock_verifier_cls.return_value = mock_verifier

        result = await job.verify_tenant(tenant_id=1)

        mock_verifier_cls.assert_called_once_with(mock_session)
        # Het knippunt gaat mee (ADR-036 OP-120); zonder anker is dat None.
        mock_verifier.verify_chain.assert_called_once_with(1, chain_epoch_id=None)

        assert isinstance(result, TenantVerificationResult)
        assert result.tenant_id == 1
        assert result.is_valid is True
        assert result.total_entries == 100
        assert result.verified_entries == 100


@pytest.mark.asyncio
async def test_verify_tenant_handles_broken_chain():
    """verify_tenant() should handle broken chain correctly."""
    from src.core.governance.hash_chain import ChainVerificationResult
    from src.core.jobs.audit_verification import AuditTrailVerificationJob, TenantVerificationResult

    mock_session = AsyncMock()
    # `verify_tenant` doet sinds ADR-036 OP-120 twee eigen queries: het anker ophalen (voor het
    # knippunt) en de laagste gesleutelde `id`. Een kale AsyncMock geeft daar een coroutine terug
    # waar de code een Result verwacht; vandaar een expliciet resultaat met SYNCHRONE
    # `scalar_one_or_none`, net als een echte `Result`.
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    job = AuditTrailVerificationJob(db_session=mock_session)

    # Mock HashChainVerifier with broken chain
    mock_chain_result = ChainVerificationResult(
        is_valid=False,
        total_entries=100,
        verified_entries=42,
        broken_at_entry_id=123,
        broken_at_index=42,
        expected_hash="expected_hash",
        actual_hash="actual_hash",
        verification_time_ms=85.3,
        tenant_id=1,
        checked_at=datetime.now(timezone.utc),
    )

    with patch("src.core.jobs.audit_verification.HashChainVerifier") as mock_verifier_cls:
        mock_verifier = MagicMock()
        mock_verifier.verify_chain = AsyncMock(return_value=mock_chain_result)
        mock_verifier_cls.return_value = mock_verifier

        result = await job.verify_tenant(tenant_id=1)

        assert isinstance(result, TenantVerificationResult)
        assert result.is_valid is False
        assert result.verified_entries == 42
        assert result.broken_at_entry_id == 123


@pytest.mark.asyncio
async def test_store_result_returns_the_deviations_it_found() -> None:
    """Het contract van `store_result`: een lijst afwijkingen, leeg als er niets verloren is.

    **Hier stonden twee HOLLE tests**, verwijderd op 2026-08-10 (ADR-036 OP-119):

        mock_tenant = MagicMock()
        mock_tenant.last_verified_at = None
        ...
        assert mock_tenant.last_verified_at is not None

    Een `MagicMock` accepteert elk attribuut, dus die assertie slaagde ongeacht wat de code deed.
    En de code deed niets: `store_result` zette `tenant.last_verified_at`, en die kolom bestaat
    niet -- niet op het model en niet in enige migratie. SQLAlchemy kende hem dus niet, vlagde
    niets en schreef niets weg. Twee groene tests over een methode die een SELECT en een commit
    deed en verder niets.

    Het gedrag wordt nu getoetst tegen een ECHTE sessie in
    `tests/unit/governance/test_audit_chain_anchor_detects_loss.py`. Alleen daar is het verschil
    tussen "opgeslagen" en "een attribuut op een mock gezet" zichtbaar.
    """
    from src.core.jobs.audit_verification import (
        AuditTrailVerificationJob,
        TenantVerificationResult,
    )

    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    job = AuditTrailVerificationJob(db_session=mock_session)

    afwijkingen = await job.store_result(
        TenantVerificationResult(
            tenant_id=1,
            is_valid=True,
            total_entries=50,
            verified_entries=50,
            broken_at_entry_id=None,
            checked_at=datetime.now(timezone.utc),
            verification_time_ms=75.2,
        )
    )

    assert afwijkingen == [], "Een eerste meting zonder bestaand anker mag niet alarmeren."
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_tenant_list_handled():
    """Job should handle empty tenant list gracefully."""
    from src.core.jobs.audit_verification import AuditTrailVerificationJob, JobResult

    mock_session = AsyncMock()
    job = AuditTrailVerificationJob(db_session=mock_session)

    # Mock tenant query to return empty list
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    result = await job.run()

    assert isinstance(result, JobResult)
    assert result.total_tenants == 0
    assert result.verified_tenants == 0
    assert result.failed_tenants == 0
    assert result.total_entries_checked == 0
    assert result.total_broken_chains == 0
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_duration_calculation():
    """Job should calculate duration correctly."""
    from src.core.jobs.audit_verification import AuditTrailVerificationJob, JobResult

    mock_session = AsyncMock()
    job = AuditTrailVerificationJob(db_session=mock_session)

    # Mock tenant query
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    start_time = datetime.now(timezone.utc)
    result = await job.run()
    end_time = datetime.now(timezone.utc)

    assert isinstance(result, JobResult)
    assert result.started_at >= start_time
    assert result.completed_at <= end_time
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_aggregate_counts_accurate():
    """Job should aggregate counts accurately across all tenants."""
    from src.core.jobs.audit_verification import (
        AuditTrailVerificationJob,
        TenantVerificationResult,
    )
    from src.core.models.rbac_models import Tenant

    mock_session = AsyncMock()
    job = AuditTrailVerificationJob(db_session=mock_session)

    # Create mock tenants
    tenant1 = MagicMock(spec=Tenant)
    tenant1.id = 1
    tenant1.is_active = True

    tenant2 = MagicMock(spec=Tenant)
    tenant2.id = 2
    tenant2.is_active = True

    tenant3 = MagicMock(spec=Tenant)
    tenant3.id = 3
    tenant3.is_active = True

    # Mock tenant query
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [tenant1, tenant2, tenant3]
    mock_session.execute.return_value = mock_result

    # Create results with different values
    async def mock_verify(tenant_id: int):
        results = {
            1: TenantVerificationResult(
                tenant_id=1,
                is_valid=True,
                total_entries=100,
                verified_entries=100,
                broken_at_entry_id=None,
                checked_at=datetime.now(timezone.utc),
                verification_time_ms=50.0,
            ),
            2: TenantVerificationResult(
                tenant_id=2,
                is_valid=False,
                total_entries=50,
                verified_entries=30,
                broken_at_entry_id=45,
                checked_at=datetime.now(timezone.utc),
                verification_time_ms=40.0,
            ),
            3: TenantVerificationResult(
                tenant_id=3,
                is_valid=True,
                total_entries=75,
                verified_entries=75,
                broken_at_entry_id=None,
                checked_at=datetime.now(timezone.utc),
                verification_time_ms=35.0,
            ),
        }
        return results[tenant_id]

    job.verify_tenant = AsyncMock(side_effect=mock_verify)
    job.store_result = AsyncMock()

    result = await job.run()

    assert result.total_tenants == 3
    assert result.verified_tenants == 2  # Tenants 1 and 3
    assert result.failed_tenants == 1  # Tenant 2
    assert result.total_entries_checked == 225  # 100 + 50 + 75
    assert result.total_broken_chains == 1  # Only tenant 2
