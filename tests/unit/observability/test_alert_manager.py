"""
Tests for Alert Manager

Covers:
- Alert rule registration
- Alert evaluation
- Notification handling
- Alert lifecycle (firing, resolving, suppressing)
- Predefined rules
"""

import pytest

from src.core.observability.alert_manager import (
    Alert,
    AlertManager,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    NotificationChannel,
    PredefinedRules,
)


class TestAlert:
    """Test Alert dataclass."""

    def test_alert_creation(self):
        """Should create alert with default status."""
        alert = Alert(
            id="alert-1",
            name="test_alert",
            severity=AlertSeverity.ERROR,
            message="Test message",
        )

        assert alert.id == "alert-1"
        assert alert.name == "test_alert"
        assert alert.severity == AlertSeverity.ERROR
        assert alert.message == "Test message"
        assert alert.status == AlertStatus.PENDING
        assert alert.tenant_id is None

    def test_alert_with_tenant(self):
        """Should create alert with tenant ID."""
        alert = Alert(
            id="alert-1",
            name="test_alert",
            severity=AlertSeverity.WARNING,
            message="Test",
            tenant_id=123,
        )

        assert alert.tenant_id == 123


class TestAlertManager:
    """Test AlertManager."""

    @pytest.fixture
    def manager(self):
        """Create fresh alert manager."""
        return AlertManager()

    def test_register_rule(self, manager):
        """Should register alert rule."""
        rule = AlertRule(
            name="test_rule",
            condition=lambda m: True,
            severity=AlertSeverity.ERROR,
            message_template="Error occurred",
            channels=[NotificationChannel.WEBHOOK],
        )

        manager.register_rule(rule)

        assert "test_rule" in manager._rules

    def test_register_handler(self, manager):
        """Should register notification handler."""
        handler_calls = []

        def handler(alert):
            handler_calls.append(alert)

        manager.register_handler(NotificationChannel.EMAIL, handler)

        assert NotificationChannel.EMAIL in manager._handlers

    def test_evaluate_rules_firing(self, manager):
        """Should evaluate rules and return firing alerts."""
        rule = AlertRule(
            name="always_fire",
            condition=lambda m: True,
            severity=AlertSeverity.ERROR,
            message_template="Always fires",
            channels=[],
        )

        manager.register_rule(rule)
        alerts = manager.evaluate_rules({})

        assert len(alerts) == 1
        assert alerts[0].name == "always_fire"
        assert alerts[0].status == AlertStatus.FIRING

    def test_evaluate_rules_not_firing(self, manager):
        """Should not return alerts for non-firing rules."""
        rule = AlertRule(
            name="never_fire",
            condition=lambda m: False,
            severity=AlertSeverity.ERROR,
            message_template="Never fires",
            channels=[],
        )

        manager.register_rule(rule)
        alerts = manager.evaluate_rules({})

        assert len(alerts) == 0

    def test_evaluate_rules_cooldown(self, manager):
        """Should respect cooldown period."""
        rule = AlertRule(
            name="cooldown_test",
            condition=lambda m: True,
            severity=AlertSeverity.ERROR,
            message_template="Test",
            channels=[],
            cooldown_seconds=60,
        )

        manager.register_rule(rule)

        # First evaluation should fire
        alerts1 = manager.evaluate_rules({})
        assert len(alerts1) == 1

        # Second evaluation should not fire (cooldown)
        alerts2 = manager.evaluate_rules({})
        assert len(alerts2) == 0

    def test_notification_sent(self, manager):
        """Should send notification when alert fires."""
        notifications = []

        def handler(alert):
            notifications.append(alert)

        manager.register_handler(NotificationChannel.WEBHOOK, handler)

        rule = AlertRule(
            name="notify_test",
            condition=lambda m: True,
            severity=AlertSeverity.ERROR,
            message_template="Test notification",
            channels=[NotificationChannel.WEBHOOK],
        )

        manager.register_rule(rule)
        manager.evaluate_rules({})

        assert len(notifications) == 1
        assert notifications[0].message == "Test notification"

    def test_resolve_alert(self, manager):
        """Should resolve active alert."""
        rule = AlertRule(
            name="resolve_test",
            condition=lambda m: True,
            severity=AlertSeverity.ERROR,
            message_template="Test",
            channels=[],
        )

        manager.register_rule(rule)
        alerts = manager.evaluate_rules({})
        alert_id = alerts[0].id

        result = manager.resolve_alert(alert_id)

        assert result is True
        assert manager._alerts[alert_id].status == AlertStatus.RESOLVED

    def test_resolve_nonexistent_alert(self, manager):
        """Should return False for nonexistent alert."""
        result = manager.resolve_alert("nonexistent")

        assert result is False

    def test_suppress_alert(self, manager):
        """Should suppress alert."""
        rule = AlertRule(
            name="suppress_test",
            condition=lambda m: True,
            severity=AlertSeverity.ERROR,
            message_template="Test",
            channels=[],
        )

        manager.register_rule(rule)
        alerts = manager.evaluate_rules({})
        alert_id = alerts[0].id

        result = manager.suppress_alert(alert_id, duration_seconds=300)

        assert result is True
        assert manager._alerts[alert_id].status == AlertStatus.SUPPRESSED

    def test_get_active_alerts(self, manager):
        """Should get all active (firing) alerts."""
        rule1 = AlertRule(
            name="alert1",
            condition=lambda m: True,
            severity=AlertSeverity.ERROR,
            message_template="Alert 1",
            channels=[],
        )

        rule2 = AlertRule(
            name="alert2",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message_template="Alert 2",
            channels=[],
            cooldown_seconds=0,
        )

        manager.register_rule(rule1)
        manager.register_rule(rule2)

        manager.evaluate_rules({})

        active = manager.get_active_alerts()

        assert len(active) == 2

    def test_get_active_alerts_by_severity(self, manager):
        """Should filter active alerts by severity."""
        rule1 = AlertRule(
            name="error_alert",
            condition=lambda m: True,
            severity=AlertSeverity.ERROR,
            message_template="Error",
            channels=[],
        )

        rule2 = AlertRule(
            name="warning_alert",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message_template="Warning",
            channels=[],
            cooldown_seconds=0,
        )

        manager.register_rule(rule1)
        manager.register_rule(rule2)

        manager.evaluate_rules({})

        error_alerts = manager.get_active_alerts(severity=AlertSeverity.ERROR)

        assert len(error_alerts) == 1
        assert error_alerts[0].severity == AlertSeverity.ERROR

    def test_get_active_alerts_by_tenant(self, manager):
        """Should filter active alerts by tenant."""

        def condition_with_tenant(metrics):
            return metrics.get("value", 0) > 0

        rule = AlertRule(
            name="tenant_alert",
            condition=condition_with_tenant,
            severity=AlertSeverity.ERROR,
            message_template="Tenant {tenant_id}",
            channels=[],
        )

        manager.register_rule(rule)
        manager.evaluate_rules({"value": 1, "tenant_id": 123})
        manager.evaluate_rules({"value": 1, "tenant_id": 456})

        tenant_alerts = manager.get_active_alerts(tenant_id=123)

        assert len(tenant_alerts) == 1
        assert tenant_alerts[0].tenant_id == 123


class TestPredefinedRules:
    """Test predefined alert rules."""

    def test_high_error_rate_rule(self):
        """High error rate rule should fire when threshold exceeded."""
        rule = PredefinedRules.high_error_rate(threshold=0.05)

        # Below threshold
        assert rule.condition({"error_rate": 0.03}) is False

        # Above threshold
        assert rule.condition({"error_rate": 0.10}) is True

        # At threshold
        assert rule.condition({"error_rate": 0.05}) is False

    def test_high_latency_rule(self):
        """High latency rule should fire when threshold exceeded."""
        rule = PredefinedRules.high_latency(threshold_ms=1000)

        # Below threshold
        assert rule.condition({"p99_latency_ms": 500}) is False

        # Above threshold
        assert rule.condition({"p99_latency_ms": 1500}) is True

    def test_quota_exceeded_rule(self):
        """Quota exceeded rule should fire when quota >= 100%."""
        rule = PredefinedRules.quota_exceeded()

        # Below 100%
        assert rule.condition({"quota_used_percent": 95}) is False

        # At 100%
        assert rule.condition({"quota_used_percent": 100}) is True

        # Above 100%
        assert rule.condition({"quota_used_percent": 105}) is True

    def test_budget_threshold_rule(self):
        """Budget threshold rule should fire when threshold reached."""
        rule = PredefinedRules.budget_threshold(threshold_percent=80)

        # Below threshold
        assert rule.condition({"budget_used_percent": 75}) is False

        # At threshold
        assert rule.condition({"budget_used_percent": 80}) is True

        # Above threshold
        assert rule.condition({"budget_used_percent": 90}) is True

    def test_rule_severity_levels(self):
        """Predefined rules should have correct severity."""
        high_error = PredefinedRules.high_error_rate()
        high_latency = PredefinedRules.high_latency()
        quota_exceeded = PredefinedRules.quota_exceeded()
        budget_threshold = PredefinedRules.budget_threshold()

        assert high_error.severity == AlertSeverity.ERROR
        assert high_latency.severity == AlertSeverity.WARNING
        assert quota_exceeded.severity == AlertSeverity.ERROR
        assert budget_threshold.severity == AlertSeverity.WARNING
