"""Unit tests for audit report_jobs tenant context cleanup.

Regression test for AUDIT-003: if audit report generation fails after the tenant
ContextVar is set, set_tenant_id(None) must still run so a pooled Dramatiq thread
does not keep the previous tenant_id.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.copilot.audit.report_jobs import _generate_audit_report_async


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cleanup_runs_when_report_generation_fails() -> None:
    """When report generation raises after tenant is set, tenant ContextVar must be cleared."""
    job_id = uuid4()
    tenant_id = 44
    from_date = datetime.now(timezone.utc)
    to_date = datetime.now(timezone.utc)
    cleanup_calls: list[object] = []

    def fake_set_tenant_id(value: object) -> None:
        cleanup_calls.append(value)

    class FailingGenerator:
        """Stand-in AuditReportGenerator whose __init__ always raises."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("generator init failed")

    fake_db = AsyncMock()
    fake_session_cm = AsyncMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_db)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "src.core.copilot.audit.report_jobs.set_tenant_id",
            side_effect=fake_set_tenant_id,
        ),
        patch(
            "src.core.copilot.audit.report_jobs.AuditReportGenerator",
            FailingGenerator,
        ),
        patch(
            "src.core.copilot.audit.report_jobs.db_manager.get_session",
            return_value=fake_session_cm,
        ),
    ):
        with pytest.raises(RuntimeError, match="generator init failed"):
            await _generate_audit_report_async(
                job_id, tenant_id, 1, from_date, to_date, "pdf"
            )

    assert cleanup_calls == [tenant_id, None]
