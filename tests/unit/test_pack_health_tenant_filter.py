"""Unit tests for pack health job tenant isolation (B-014).

Verifies that pack health queries filter by tenant_id.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_pack_health_filters_by_tenant_id():
    """calculate_pack_health must accept tenant_id and filter DomainPack query."""
    from src.core.jobs.pack_health_job import calculate_pack_health

    mock_session = AsyncMock()
    mock_pack = MagicMock()
    mock_pack.tenant_id = 42
    mock_pack.last_used_at = datetime.now(timezone.utc) - timedelta(days=30)
    mock_pack.usage_count = 10
    mock_pack.error_count = 0
    mock_pack.health_status = "healthy"
    mock_pack.last_health_check = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_pack]
    mock_session.execute.return_value = mock_result

    await calculate_pack_health(mock_session, tenant_id=42)

    # The executed query should contain a tenant_id filter
    call_args = mock_session.execute.call_args
    query_obj = call_args[0][0]
    query_str = str(query_obj)

    assert "tenant_id" in query_str, (
        "calculate_pack_health query does not filter by tenant_id"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_aggregate_pack_usage_filters_by_tenant_id():
    """aggregate_pack_usage must accept tenant_id and filter audit log query."""
    from src.core.jobs.pack_health_job import aggregate_pack_usage

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.execute.return_value = mock_result

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    await aggregate_pack_usage(mock_session, since=since, tenant_id=42)

    call_args = mock_session.execute.call_args
    query_obj = call_args[0][0]
    query_str = str(query_obj)

    assert "tenant_id" in query_str, (
        "aggregate_pack_usage query does not filter by tenant_id"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pack_usage_counts_filters_by_tenant_id():
    """update_pack_usage_counts must accept tenant_id and filter DomainPack query."""
    from src.core.jobs.pack_health_job import update_pack_usage_counts

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.execute.return_value = mock_result

    await update_pack_usage_counts(mock_session, tenant_id=42)

    # First call is aggregate_pack_usage, second is the DomainPack lookup
    assert mock_session.execute.call_count >= 1

    # Check that at least one query contains tenant_id filter
    has_tenant_filter = False
    for call in mock_session.execute.call_args_list:
        query_obj = call[0][0]
        if "tenant_id" in str(query_obj):
            has_tenant_filter = True
            break

    assert has_tenant_filter, (
        "update_pack_usage_counts query does not filter by tenant_id"
    )
