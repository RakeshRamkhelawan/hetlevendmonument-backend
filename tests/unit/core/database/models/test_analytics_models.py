"""Unit tests for src.core.database.models.analytics."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from src.core.database.models.analytics import (
    PackUsageAggregate,
    CompanyAnalyticsOptOut,
    BenchmarkingQueryLog,
    __all__ as analytics_all,
)


def test_analytics_models_exports():
    """Validates all intended models are exported."""
    assert "PackUsageAggregate" in analytics_all
    assert "CompanyAnalyticsOptOut" in analytics_all
    assert "BenchmarkingQueryLog" in analytics_all


def test_pack_usage_aggregate_attributes():
    """Tests PackUsageAggregate fields, defaults, and representation."""
    now = datetime.now(timezone.utc)
    item_id = uuid4()
    item = PackUsageAggregate(
        id=item_id,
        date=now,
        sector="Technology",
        company_type="mkb",
        employee_bucket="10-49",
        pack_id="pack-hr-core",
        pack_name="HR Automation Pack",
        total_companies=10,
        active_companies=5,
        total_activations=25,
        daily_activations=2,
        adoption_rate_pct=50.0,
        avg_usage_per_company=3.5,
        k_anonymity_met=True,
    )

    assert item.id == item_id
    assert item.sector == "Technology"
    assert item.company_type == "mkb"
    assert item.employee_bucket == "10-49"
    assert item.pack_id == "pack-hr-core"
    assert item.adoption_rate_pct == 50.0
    assert item.k_anonymity_met is True

    repr_str = repr(item)
    assert "PackUsageAggregate" in repr_str
    assert "Technology" in repr_str
    assert "pack-hr-core" in repr_str
    assert "50.0%" in repr_str


def test_company_analytics_opt_out_attributes():
    """Tests CompanyAnalyticsOptOut fields and representation."""
    company_id = uuid4()
    opt_out = CompanyAnalyticsOptOut(
        company_id=company_id,
        reason="GDPR objection",
        company_hash="abc123hash",
    )

    assert opt_out.company_id == company_id
    assert opt_out.reason == "GDPR objection"
    assert opt_out.company_hash == "abc123hash"

    repr_str = repr(opt_out)
    assert "CompanyAnalyticsOptOut" in repr_str
    assert "abc123hash" in repr_str


def test_benchmarking_query_log_attributes():
    """Tests BenchmarkingQueryLog fields."""
    log_id = uuid4()
    company_id = uuid4()
    now = datetime.now(timezone.utc)

    log_entry = BenchmarkingQueryLog(
        id=log_id,
        user_id=42,
        company_id=company_id,
        query_type="sector_benchmarks",
        query_params='{"sector": "Finance"}',
        queried_at=now,
    )

    assert log_entry.id == log_id
    assert log_entry.user_id == 42
    assert log_entry.company_id == company_id
    assert log_entry.query_type == "sector_benchmarks"
    assert log_entry.query_params == '{"sector": "Finance"}'
    assert log_entry.queried_at == now
