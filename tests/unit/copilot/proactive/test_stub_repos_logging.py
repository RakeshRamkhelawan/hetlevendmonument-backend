"""
Unit tests for Proactive Copilot stub repositories structured logging.

Verifies that all 7 stub repositories emit structured debug logs on invocation,
ensuring observability and preventing silent failure in the scheduler pipeline.
"""

from datetime import datetime, timezone
import logging
from unittest.mock import MagicMock

import pytest

from src.core.copilot.proactive.stub_repos import (
    StubAuditRepo,
    StubConsentRepo,
    StubDPIARepo,
    StubPrometheusClient,
    StubRoleRepo,
    StubWorkflowPIIScanner,
    StubWorkflowRepo,
)


@pytest.fixture
def mock_session_factory() -> MagicMock:
    return MagicMock()


@pytest.mark.asyncio
async def test_stub_consent_repo_logs_invocation(
    mock_session_factory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    repo = StubConsentRepo(mock_session_factory)
    result = await repo.list_users_with_expiring_consent(tenant_id=42, days_before_expiry=7)
    assert result == []
    assert any(
        "StubConsentRepo.list_users_with_expiring_consent" in record.message
        for record in caplog.records
    )
    assert any("tenant_id=42" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_stub_audit_repo_logs_invocation(
    mock_session_factory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    repo = StubAuditRepo(mock_session_factory)
    result = await repo.count_permission_denied_per_user(tenant_id=42, hours=24)
    assert result == []
    assert any(
        "StubAuditRepo.count_permission_denied_per_user" in record.message
        for record in caplog.records
    )
    assert any("tenant_id=42" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_stub_role_repo_logs_invocation(
    mock_session_factory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    repo = StubRoleRepo(mock_session_factory)
    now = datetime.now(timezone.utc)
    result = await repo.was_any_role_created_after(tenant_id=42, after=now)
    assert result is False
    assert any(
        "StubRoleRepo.was_any_role_created_after" in record.message for record in caplog.records
    )
    assert any("tenant_id=42" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_stub_workflow_repo_logs_invocation(
    mock_session_factory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    repo = StubWorkflowRepo(mock_session_factory)
    result = await repo.list_active(tenant_id=42)
    assert result == []
    assert any("StubWorkflowRepo.list_active" in record.message for record in caplog.records)
    assert any("tenant_id=42" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_stub_dpia_repo_logs_invocation(
    mock_session_factory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    repo = StubDPIARepo(mock_session_factory)
    result = await repo.exists_for_workflow(tenant_id=42, workflow_id="wf-100")
    assert result is False
    assert any("StubDPIARepo.exists_for_workflow" in record.message for record in caplog.records)
    assert any("tenant_id=42" in record.message for record in caplog.records)


def test_stub_workflow_pii_scanner_logs_invocation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    scanner = StubWorkflowPIIScanner()
    result = scanner.scan({"step": "test"})
    assert result == []
    assert any("StubWorkflowPIIScanner.scan" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_stub_prometheus_client_logs_invocation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = StubPrometheusClient()
    assert await client.list_workflows(tenant_id=42) == []
    assert await client.execution_count("wf-1", 42, "1h") == 0
    assert await client.get_histogram_p95("lat", {}, "1h") == 0.0
    assert await client.get_counter_sum("cnt", {}, "1h") == 0.0
    assert await client.get_counter_average("avg", {}, "1h", "1m") == 0.0

    assert any("StubPrometheusClient.list_workflows" in record.message for record in caplog.records)
    assert any(
        "StubPrometheusClient.execution_count" in record.message for record in caplog.records
    )
