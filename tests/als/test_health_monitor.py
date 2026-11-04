"""Tests for AgentHealthMonitorAgent health monitoring infrastructure."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timedelta, timezone

import pytest

from src.core.als.health_monitor import (
    ALERT_COOLDOWN_SECONDS,
    CONSECUTIVE_FAILURE_DISABLE,
    AgentHealthMonitorAgent,
    HealthAlert,
    HealthMetrics,
    HealthMonitorService,
    HealthRecord,
    HealthStatus,
)


@pytest.mark.als
class TestHealthStatus:
    def test_all_statuses_exist(self):
        assert {s.value for s in HealthStatus} == {
            "healthy",
            "warning",
            "critical",
            "disabled",
        }

    def test_ordering(self):
        # healthy < warning < critical < disabled
        assert HealthStatus.HEALTHY.value < HealthStatus.WARNING.value


@pytest.mark.als
class TestHealthRecord:
    def test_has_required_fields(self):
        field_names = {f.name for f in fields(HealthRecord)}
        assert field_names >= {
            "agent_id",
            "tenant_id",
            "success",
            "latency_ms",
            "timestamp",
            "error_type",
        }

    def test_defaults(self):
        record = HealthRecord(
            agent_id="agent-1",
            tenant_id=1,
            success=True,
            latency_ms=42.0,
        )
        assert record.error_type is None
        assert isinstance(record.timestamp, datetime)


@pytest.mark.als
class TestHealthMetrics:
    def test_has_required_fields(self):
        field_names = {f.name for f in fields(HealthMetrics)}
        assert field_names >= {
            "agent_id",
            "total_tasks",
            "success_count",
            "error_count",
            "avg_latency_ms",
            "error_rate",
            "success_rate",
            "status",
            "consecutive_failures",
        }

    def test_computed_rates(self):
        metrics = HealthMetrics(
            agent_id="agent-1",
            total_tasks=10,
            success_count=8,
            error_count=2,
            avg_latency_ms=100.0,
            error_rate=0.2,
            success_rate=0.8,
            status=HealthStatus.WARNING,
            consecutive_failures=0,
        )
        assert metrics.error_rate == pytest.approx(0.2)
        assert metrics.success_rate == pytest.approx(0.8)


@pytest.mark.als
class TestHealthAlert:
    def test_has_required_fields(self):
        field_names = {f.name for f in fields(HealthAlert)}
        assert field_names >= {
            "agent_id",
            "tenant_id",
            "alert_type",
            "severity",
            "message",
            "metrics",
            "timestamp",
        }

    def test_defaults(self):
        metrics = HealthMetrics(
            agent_id="agent-1",
            total_tasks=10,
            success_count=5,
            error_count=5,
            avg_latency_ms=6000.0,
            error_rate=0.5,
            success_rate=0.5,
            status=HealthStatus.CRITICAL,
            consecutive_failures=3,
        )
        alert = HealthAlert(
            agent_id="agent-1",
            tenant_id=1,
            alert_type="high_error_rate",
            severity="critical",
            message="Error rate 50% exceeds threshold",
            metrics=metrics,
        )
        assert isinstance(alert.timestamp, datetime)


@pytest.mark.als
class TestHealthMonitorServiceRecording:
    def test_record_single_success(self):
        service = HealthMonitorService()
        record = HealthRecord(agent_id="agent-1", tenant_id=1, success=True, latency_ms=50.0)
        service.record(record)
        metrics = service.get_metrics("agent-1")
        assert metrics.total_tasks == 1
        assert metrics.success_count == 1
        assert metrics.error_count == 0
        assert metrics.error_rate == pytest.approx(0.0)
        assert metrics.success_rate == pytest.approx(1.0)

    def test_record_single_failure(self):
        service = HealthMonitorService()
        record = HealthRecord(
            agent_id="agent-1",
            tenant_id=1,
            success=False,
            latency_ms=50.0,
            error_type="TimeoutError",
        )
        service.record(record)
        metrics = service.get_metrics("agent-1")
        assert metrics.total_tasks == 1
        assert metrics.error_count == 1
        assert metrics.error_rate == pytest.approx(1.0)

    def test_rolling_window_caps_at_50(self):
        service = HealthMonitorService()
        for i in range(60):
            service.record(
                HealthRecord(agent_id="agent-1", tenant_id=1, success=True, latency_ms=10.0)
            )
        metrics = service.get_metrics("agent-1")
        assert metrics.total_tasks == 50  # capped at ROLLING_WINDOW_SIZE

    def test_avg_latency_computation(self):
        service = HealthMonitorService()
        for lat in [100.0, 200.0, 300.0]:
            service.record(
                HealthRecord(agent_id="agent-1", tenant_id=1, success=True, latency_ms=lat)
            )
        metrics = service.get_metrics("agent-1")
        assert metrics.avg_latency_ms == pytest.approx(200.0)

    def test_unknown_agent_returns_none(self):
        service = HealthMonitorService()
        metrics = service.get_metrics("nonexistent")
        assert metrics is None

    def test_multiple_agents_isolated(self):
        service = HealthMonitorService()
        service.record(HealthRecord(agent_id="agent-1", tenant_id=1, success=True, latency_ms=10.0))
        service.record(
            HealthRecord(agent_id="agent-2", tenant_id=1, success=False, latency_ms=20.0)
        )
        m1 = service.get_metrics("agent-1")
        m2 = service.get_metrics("agent-2")
        assert m1.success_count == 1
        assert m2.error_count == 1

    def test_consecutive_failures_tracked(self):
        service = HealthMonitorService()
        # 2 failures, then 1 success resets counter
        service.record(
            HealthRecord(agent_id="agent-1", tenant_id=1, success=False, latency_ms=10.0)
        )
        service.record(
            HealthRecord(agent_id="agent-1", tenant_id=1, success=False, latency_ms=10.0)
        )
        assert service.get_metrics("agent-1").consecutive_failures == 2

    def test_consecutive_failures_reset_on_success(self):
        service = HealthMonitorService()
        service.record(
            HealthRecord(agent_id="agent-1", tenant_id=1, success=False, latency_ms=10.0)
        )
        service.record(
            HealthRecord(agent_id="agent-1", tenant_id=1, success=False, latency_ms=10.0)
        )
        assert service.get_metrics("agent-1").consecutive_failures == 2
        service.record(HealthRecord(agent_id="agent-1", tenant_id=1, success=True, latency_ms=10.0))
        assert service.get_metrics("agent-1").consecutive_failures == 0


@pytest.mark.als
class TestHealthStatusComputation:
    def test_healthy_agent(self):
        service = HealthMonitorService()
        for _ in range(10):
            service.record(
                HealthRecord(agent_id="agent-1", tenant_id=1, success=True, latency_ms=100.0)
            )
        metrics = service.get_metrics("agent-1")
        assert metrics.status == HealthStatus.HEALTHY

    def test_warning_on_high_error_rate(self):
        service = HealthMonitorService()
        # 8 successes + 2 failures = 20% error rate (boundary)
        for _ in range(8):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=True, latency_ms=10.0))
        for _ in range(2):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        metrics = service.get_metrics("a")
        assert metrics.status == HealthStatus.WARNING

    def test_critical_on_extreme_error_rate(self):
        service = HealthMonitorService()
        # 5 successes + 5 failures = 50% error rate
        for _ in range(5):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=True, latency_ms=10.0))
        for _ in range(5):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        metrics = service.get_metrics("a")
        assert metrics.status == HealthStatus.CRITICAL

    def test_warning_on_high_latency(self):
        service = HealthMonitorService()
        service.record(HealthRecord(agent_id="a", tenant_id=1, success=True, latency_ms=6000.0))
        metrics = service.get_metrics("a")
        assert metrics.status == HealthStatus.WARNING

    def test_warning_on_low_success_rate(self):
        service = HealthMonitorService()
        # 7 successes + 3 failures = 70% success rate (< 80%)
        for _ in range(7):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=True, latency_ms=10.0))
        for _ in range(3):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        metrics = service.get_metrics("a")
        assert metrics.status == HealthStatus.WARNING


@pytest.mark.als
class TestAlertGeneration:
    def test_no_alert_for_healthy_agent(self):
        service = HealthMonitorService()
        for _ in range(10):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=True, latency_ms=10.0))
        alerts = service.check_alerts("a", tenant_id=1)
        assert alerts == []

    def test_alert_on_high_error_rate(self):
        service = HealthMonitorService()
        for _ in range(8):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=True, latency_ms=10.0))
        for _ in range(3):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        alerts = service.check_alerts("a", tenant_id=1)
        assert len(alerts) >= 1
        assert any(a.alert_type == "high_error_rate" for a in alerts)

    def test_alert_on_high_latency(self):
        service = HealthMonitorService()
        service.record(HealthRecord(agent_id="a", tenant_id=1, success=True, latency_ms=6000.0))
        alerts = service.check_alerts("a", tenant_id=1)
        assert any(a.alert_type == "high_latency" for a in alerts)

    def test_alert_cooldown_suppresses_duplicate(self):
        service = HealthMonitorService()
        for _ in range(5):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        alerts1 = service.check_alerts("a", tenant_id=1)
        assert len(alerts1) >= 1

        # Immediate second check -- should be suppressed
        alerts2 = service.check_alerts("a", tenant_id=1)
        assert alerts2 == []

    def test_alert_fires_again_after_cooldown(self):
        service = HealthMonitorService()
        for _ in range(5):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        alerts1 = service.check_alerts("a", tenant_id=1)
        assert len(alerts1) >= 1

        # Fast-forward past cooldown
        past = datetime.now(timezone.utc) - timedelta(seconds=ALERT_COOLDOWN_SECONDS + 1)
        service._last_alert_time["a"] = past

        alerts2 = service.check_alerts("a", tenant_id=1)
        assert len(alerts2) >= 1


@pytest.mark.als
class TestAgentDisabling:
    def test_agent_disabled_after_consecutive_failures(self):
        service = HealthMonitorService()
        for _ in range(CONSECUTIVE_FAILURE_DISABLE):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        alerts = service.check_alerts("a", tenant_id=1)
        assert service.is_disabled("a")
        assert any(a.alert_type == "agent_disabled" for a in alerts)

    def test_disabled_agent_not_re_disabled(self):
        service = HealthMonitorService()
        for _ in range(CONSECUTIVE_FAILURE_DISABLE):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        service.check_alerts("a", tenant_id=1)
        assert service.is_disabled("a")

        # Recording more failures on disabled agent does not crash
        service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        assert service.is_disabled("a")

    def test_re_enable_agent(self):
        service = HealthMonitorService()
        for _ in range(CONSECUTIVE_FAILURE_DISABLE):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        service.check_alerts("a", tenant_id=1)
        assert service.is_disabled("a")

        service.enable_agent("a")
        assert not service.is_disabled("a")

    def test_enable_unknown_agent_is_noop(self):
        service = HealthMonitorService()
        service.enable_agent("nonexistent")  # should not raise


@pytest.mark.als
class TestHealthReport:
    def test_empty_report(self):
        service = HealthMonitorService()
        report = service.get_health_report()
        assert report == []

    def test_report_contains_all_agents(self):
        service = HealthMonitorService()
        service.record(HealthRecord(agent_id="a", tenant_id=1, success=True, latency_ms=10.0))
        service.record(HealthRecord(agent_id="b", tenant_id=2, success=False, latency_ms=20.0))
        report = service.get_health_report()
        ids = {m.agent_id for m in report}
        assert ids == {"a", "b"}

    def test_report_includes_disabled_status(self):
        service = HealthMonitorService()
        for _ in range(CONSECUTIVE_FAILURE_DISABLE):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        service.check_alerts("a", tenant_id=1)
        assert service.is_disabled("a")

        report = service.get_health_report()
        agent_a = [m for m in report if m.agent_id == "a"][0]
        assert agent_a.status == HealthStatus.DISABLED


@pytest.mark.als
class TestAgentHealthMonitorAgent:
    def test_record_and_retrieve_metrics(self):
        agent = AgentHealthMonitorAgent(tenant_id=1)
        agent.record_task_result(agent_id="worker-1", success=True, latency_ms=50.0)
        metrics = agent.get_agent_health("worker-1")
        assert metrics is not None
        assert metrics.total_tasks == 1

    def test_check_alerts_delegates_to_service(self):
        agent = AgentHealthMonitorAgent(tenant_id=1)
        for _ in range(5):
            agent.record_task_result(agent_id="worker-1", success=False, latency_ms=10.0)
        alerts = agent.check_agent_alerts("worker-1")
        assert len(alerts) >= 1

    def test_is_agent_available_returns_false_when_disabled(self):
        agent = AgentHealthMonitorAgent(tenant_id=1)
        for _ in range(CONSECUTIVE_FAILURE_DISABLE):
            agent.record_task_result(agent_id="worker-1", success=False, latency_ms=10.0)
        agent.check_agent_alerts("worker-1")
        assert not agent.is_agent_available("worker-1")

    def test_is_agent_available_returns_true_for_healthy(self):
        agent = AgentHealthMonitorAgent(tenant_id=1)
        agent.record_task_result(agent_id="worker-1", success=True, latency_ms=10.0)
        assert agent.is_agent_available("worker-1")

    def test_get_health_report(self):
        agent = AgentHealthMonitorAgent(tenant_id=1)
        agent.record_task_result(agent_id="w1", success=True, latency_ms=10.0)
        agent.record_task_result(agent_id="w2", success=False, latency_ms=20.0)
        report = agent.get_health_report()
        assert set(report.keys()) == {"w1", "w2"}

    def test_enable_agent_delegation(self):
        agent = AgentHealthMonitorAgent(tenant_id=1)
        for _ in range(CONSECUTIVE_FAILURE_DISABLE):
            agent.record_task_result(agent_id="w1", success=False, latency_ms=10.0)
        agent.check_agent_alerts("w1")
        assert not agent.is_agent_available("w1")
        agent.enable_agent("w1")
        assert agent.is_agent_available("w1")


@pytest.mark.als
class TestEdgeCases:
    """Task 7 -- edge cases and unhappy paths."""

    def test_record_with_zero_latency(self):
        service = HealthMonitorService()
        service.record(HealthRecord(agent_id="a", tenant_id=1, success=True, latency_ms=0.0))
        metrics = service.get_metrics("a")
        assert metrics is not None
        assert metrics.avg_latency_ms == pytest.approx(0.0)

    def test_all_failures_gives_100_percent_error_rate(self):
        service = HealthMonitorService()
        for _ in range(10):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        metrics = service.get_metrics("a")
        assert metrics.error_rate == pytest.approx(1.0)
        assert metrics.success_rate == pytest.approx(0.0)

    def test_window_eviction_updates_metrics(self):
        service = HealthMonitorService(window_size=5)
        # Fill with 5 failures
        for _ in range(5):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=False, latency_ms=10.0))
        assert service.get_metrics("a").error_rate == pytest.approx(1.0)

        # Add 5 successes -- failures get evicted
        for _ in range(5):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=True, latency_ms=10.0))
        assert service.get_metrics("a").error_rate == pytest.approx(0.0)

    def test_check_alerts_for_unknown_agent(self):
        service = HealthMonitorService()
        alerts = service.check_alerts("nonexistent", tenant_id=1)
        assert alerts == []

    def test_is_disabled_for_unknown_agent(self):
        service = HealthMonitorService()
        assert not service.is_disabled("nonexistent")

    def test_custom_window_size(self):
        service = HealthMonitorService(window_size=3)
        for _ in range(5):
            service.record(HealthRecord(agent_id="a", tenant_id=1, success=True, latency_ms=10.0))
        metrics = service.get_metrics("a")
        assert metrics.total_tasks == 3

    def test_agent_monitor_with_different_tenants(self):
        """Health monitor instance is scoped to a single tenant."""
        agent = AgentHealthMonitorAgent(tenant_id=1)
        agent.record_task_result(agent_id="w1", success=True, latency_ms=10.0)
        metrics = agent.get_agent_health("w1")
        assert metrics is not None
