"""Unit tests for twin profile aggregation metrics (B-012).

Verifies that per-tenant metrics are emitted, not aggregated under tenant_id=0.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_aggregate_all_profiles_emits_per_tenant_metrics():
    """Metrics must be recorded per-tenant, not hardcoded to tenant_id=0."""
    from src.core.jobs.twin_profile_aggregation_job import aggregate_all_profiles

    mock_session = AsyncMock()

    # De taak vraagt sinds 2026-09-16 EERST de klantenlijst op (ADR-036 OP-153) en loopt
    # daarna per klant. Reden: `user_behavior_observations` heeft een afschermingsregel
    # en `tenants` niet, dus de klantenlijst is de enige lezing die klant-overstijgend
    # mag zijn. Gemeten op de ketendatabase als niet-eigenaar zonder klantcontext:
    # observaties nul rijen, tenants twee rijen.
    mock_session.execute.return_value.all = MagicMock(return_value=[(7,), (9,)])

    # Per klant een gebruiker; de taak vraagt nu om `human_user_id`, niet om paren.
    def mock_fetch_batch(db, tenant_id, limit, offset):
        if offset == 0:
            return {7: ["user_a"], 9: ["user_b"]}[tenant_id]
        return []

    with patch(
        "src.core.jobs.twin_profile_aggregation_job._fetch_user_batch",
        side_effect=mock_fetch_batch,
    ):
        with patch(
            "src.core.jobs.twin_profile_aggregation_job.get_db_session"
        ) as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.core.jobs.twin_profile_aggregation_job.ProfileAggregator"
            ) as mock_agg_cls:
                mock_agg = MagicMock()
                mock_agg.aggregate = AsyncMock(return_value=MagicMock())
                mock_agg_cls.return_value = mock_agg

                with patch(
                    "src.core.jobs.twin_profile_aggregation_job.record_twin_aggregation_users_processed"
                ) as mock_record:
                    result = await aggregate_all_profiles(batch_size=100)

    # Should have called record_twin_aggregation_users_processed for EACH tenant
    assert mock_record.call_count >= 2, (
        f"Expected per-tenant metrics (>=2 calls), got {mock_record.call_count}"
    )

    # Collect all tenant_ids that were passed to the metric function
    call_tenant_ids = {call.args[0] for call in mock_record.call_args_list}

    assert 7 in call_tenant_ids, "Metric for tenant 7 not emitted"
    assert 9 in call_tenant_ids, "Metric for tenant 9 not emitted"
    assert 0 not in call_tenant_ids, (
        "Hardcoded tenant_id=0 still present in metric calls"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_aggregate_all_profiles_no_hardcoded_tenant_zero():
    """Source code must not contain tenant_id=0 in aggregate_all_profiles."""
    import inspect
    from src.core.jobs.twin_profile_aggregation_job import aggregate_all_profiles

    source = inspect.getsource(aggregate_all_profiles)
    assert "tenant_id=0" not in source, (
        "aggregate_all_profiles still hardcodes tenant_id=0"
    )
