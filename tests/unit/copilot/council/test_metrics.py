"""Unit tests for Agent Council Prometheus metrics.

Cardinality-discipline tests ensure we do not accidentally explode
Prometheus with high-cardinality labels (tenant_id on histograms,
user_id anywhere).
"""

from __future__ import annotations

import time

import pytest

from src.core.copilot.council.metrics import (
    AUDIT_WRITES_TOTAL,
    COUNCIL_CACHE_HIT_TOTAL,
    COUNCIL_CACHE_MISS_TOTAL,
    COUNCIL_DELIBERATION_SECONDS,
    COUNCIL_TURNS_TOTAL,
    COUNCIL_VERDICT_TOTAL,
    HASH_CHAIN_BREAKS_TOTAL,
    HITL_PENDING,
    NOTIFICATIONS_DEFERRED_TOTAL,
    NOTIFICATIONS_DISPATCHED_TOTAL,
)


@pytest.mark.unit
def test_council_turns_counter_increments() -> None:
    before = (
        COUNCIL_TURNS_TOTAL.labels(tenant_id="1", verdict="APPROVED")
        ._value.get()
    )
    COUNCIL_TURNS_TOTAL.labels(tenant_id="1", verdict="APPROVED").inc()
    after = (
        COUNCIL_TURNS_TOTAL.labels(tenant_id="1", verdict="APPROVED")
        ._value.get()
    )
    assert after - before == 1


@pytest.mark.unit
def test_deliberation_histogram_records_latency() -> None:
    with COUNCIL_DELIBERATION_SECONDS.labels(officer="test").time():
        time.sleep(0.05)
    # Verify that _sum > 0
    samples = list(COUNCIL_DELIBERATION_SECONDS.collect())
    found = False
    for s in samples:
        for v in s.samples:
            if (
                v.name == "copilot_council_deliberation_seconds_sum"
                and v.labels.get("officer") == "test"
                and v.value > 0
            ):
                found = True
                break
    assert found, "Histogram did not record positive latency"


@pytest.mark.unit
def test_audit_write_success_increments_success() -> None:
    before = AUDIT_WRITES_TOTAL.labels(status="success")._value.get()
    AUDIT_WRITES_TOTAL.labels(status="success").inc()
    after = AUDIT_WRITES_TOTAL.labels(status="success")._value.get()
    assert after - before == 1


@pytest.mark.unit
def test_audit_write_failure_increments_failed() -> None:
    before = AUDIT_WRITES_TOTAL.labels(status="failed")._value.get()
    AUDIT_WRITES_TOTAL.labels(status="failed").inc()
    after = AUDIT_WRITES_TOTAL.labels(status="failed")._value.get()
    assert after - before == 1


@pytest.mark.unit
def test_hash_chain_break_counter_increments() -> None:
    before = HASH_CHAIN_BREAKS_TOTAL.labels(tenant_id="42")._value.get()
    HASH_CHAIN_BREAKS_TOTAL.labels(tenant_id="42").inc()
    after = HASH_CHAIN_BREAKS_TOTAL.labels(tenant_id="42")._value.get()
    assert after - before == 1


@pytest.mark.unit
def test_metrics_module_exposes_expected_names() -> None:
    """Lockdown test -- voorkomt accidentele rename."""
    expected = {
        "COUNCIL_TURNS_TOTAL",
        "COUNCIL_DELIBERATION_SECONDS",
        "COUNCIL_VERDICT_TOTAL",
        "HITL_PENDING",
        "AUDIT_WRITES_TOTAL",
        "HASH_CHAIN_BREAKS_TOTAL",
        "NOTIFICATIONS_DISPATCHED_TOTAL",
        "NOTIFICATIONS_DEFERRED_TOTAL",
        "COUNCIL_CACHE_HIT_TOTAL",
        "COUNCIL_CACHE_MISS_TOTAL",
    }
    from src.core.copilot.council import metrics

    assert expected.issubset(set(metrics.__all__))


@pytest.mark.unit
def test_cardinality_discipline_no_tenant_id_on_histogram() -> None:
    """Verifieer dat tenant_id GEEN label is op DELIBERATION_SECONDS."""
    assert "tenant_id" not in COUNCIL_DELIBERATION_SECONDS._labelnames


@pytest.mark.unit
def test_no_user_id_label_on_any_metric() -> None:
    """user_id is NOOIT een label (cardinality-bomb voor 100k+ users)."""
    from src.core.copilot.council import metrics as m

    for name in m.__all__:
        col = getattr(m, name)
        labels = getattr(col, "_labelnames", ())
        assert "user_id" not in labels, f"{name} has user_id label -- forbidden"


@pytest.mark.unit
def test_hash_chain_breaks_has_tenant_id_label() -> None:
    """tenant_id label IS toegevoegd voor incident response."""
    assert "tenant_id" in HASH_CHAIN_BREAKS_TOTAL._labelnames


@pytest.mark.unit
def test_cache_hit_counter_increments() -> None:
    before = COUNCIL_CACHE_HIT_TOTAL.labels(officer="ComplianceOfficer")._value.get()
    COUNCIL_CACHE_HIT_TOTAL.labels(officer="ComplianceOfficer").inc()
    after = COUNCIL_CACHE_HIT_TOTAL.labels(officer="ComplianceOfficer")._value.get()
    assert after - before == 1


@pytest.mark.unit
def test_cache_miss_counter_increments() -> None:
    before = COUNCIL_CACHE_MISS_TOTAL.labels(officer="PrivacyOfficer")._value.get()
    COUNCIL_CACHE_MISS_TOTAL.labels(officer="PrivacyOfficer").inc()
    after = COUNCIL_CACHE_MISS_TOTAL.labels(officer="PrivacyOfficer")._value.get()
    assert after - before == 1


@pytest.mark.unit
def test_hitl_pending_gauge_can_set() -> None:
    HITL_PENDING.labels(tenant_id="1").set(5)
    # No assertion on global state; just verify it does not raise


@pytest.mark.unit
def test_notifications_counters_increments() -> None:
    before_d = (
        NOTIFICATIONS_DISPATCHED_TOTAL.labels(tenant_id="1", severity="high")
        ._value.get()
    )
    NOTIFICATIONS_DISPATCHED_TOTAL.labels(tenant_id="1", severity="high").inc()
    after_d = (
        NOTIFICATIONS_DISPATCHED_TOTAL.labels(tenant_id="1", severity="high")
        ._value.get()
    )
    assert after_d - before_d == 1

    before_df = (
        NOTIFICATIONS_DEFERRED_TOTAL.labels(tenant_id="1", reason="budget")
        ._value.get()
    )
    NOTIFICATIONS_DEFERRED_TOTAL.labels(tenant_id="1", reason="budget").inc()
    after_df = (
        NOTIFICATIONS_DEFERRED_TOTAL.labels(tenant_id="1", reason="budget")
        ._value.get()
    )
    assert after_df - before_df == 1
