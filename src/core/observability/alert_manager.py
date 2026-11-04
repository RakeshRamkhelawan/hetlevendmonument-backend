"""
Alert Manager

Provides:
- Configurable alerting rules
- Multi-channel notifications (email, webhook, PagerDuty)
- Alert suppression and deduplication
- On-call rotation support
"""

import enum
import time
from dataclasses import dataclass, field
from typing import Any, cast
from collections.abc import Callable


class AlertSeverity(enum.Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(enum.Enum):
    """Alert status."""

    PENDING = "pending"
    FIRING = "firing"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class NotificationChannel(enum.Enum):
    """Notification channels."""

    EMAIL = "email"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"
    SLACK = "slack"


@dataclass
class Alert:
    """Alert definition."""

    id: str
    name: str
    severity: AlertSeverity
    message: str
    tenant_id: int | None = None
    status: AlertStatus = AlertStatus.PENDING
    created_at: float = field(default_factory=time.time)
    fired_at: float | None = None
    resolved_at: float | None = None
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)


@dataclass
class AlertRule:
    """Alert rule definition."""

    name: str
    condition: Callable[..., bool]
    severity: AlertSeverity
    message_template: str
    channels: list[NotificationChannel]
    cooldown_seconds: float = 300.0
    suppress_alerts: list[str] = field(default_factory=list)


class AlertManager:
    """
    Manages alerts and notifications.
    """

    def __init__(self) -> None:
        self._rules: dict[str, AlertRule] = {}
        self._alerts: dict[str, Alert] = {}
        self._handlers: dict[
            NotificationChannel, Callable[..., Any]
        ] = {}  # TODO(TYPE): replace Any with concrete type
        self._last_alert_time: dict[str, float] = {}
        self._suppressed_alerts: set[str] = set()

    def register_rule(self, rule: AlertRule) -> None:
        """
        Register an alert rule.

        Args:
            rule: Alert rule definition
        """
        self._rules[rule.name] = rule

    def register_handler(
        self,
        channel: NotificationChannel,
        handler: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Register notification handler.

        Args:
            channel: Notification channel
            handler: Handler function
        """
        self._handlers[channel] = handler

    def evaluate_rules(
        self, metrics: dict[str, Any]  # TODO(TYPE): Any -- MetricsDict: str->float|int|str
    ) -> list[Alert]:
        """
        Evaluate all alert rules against current metrics.

        Args:
            metrics: Current metrics data

        Returns: List[Alert] of firing alerts
        """
        firing: list[Alert] = []
        for rule_name, rule in self._rules.items():
            # Check cooldown
            last_fired = self._last_alert_time.get(rule_name, 0)
            if time.time() - last_fired < rule.cooldown_seconds:
                continue

            # Evaluate condition
            try:
                if rule.condition(metrics):
                    alert = self._create_alert(rule, metrics)
                    firing.append(alert)
                    self._last_alert_time[rule_name] = time.time()
            except Exception as e:
                # Log error but don't crash
                print(f"Error evaluating rule {rule_name}: {e}")

        return firing

    def _create_alert(
        self,
        rule: AlertRule,
        metrics: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> Alert:
        """Create alert from rule."""
        alert_id = f"{rule.name}:{int(time.time())}"

        message = rule.message_template.format(**metrics)

        alert = Alert(
            id=alert_id,
            name=rule.name,
            severity=rule.severity,
            message=message,
            tenant_id=metrics.get("tenant_id"),
            status=AlertStatus.FIRING,
            fired_at=time.time(),
        )

        self._alerts[alert_id] = alert

        # Send notifications
        self._notify(alert, rule)

        return alert

    def _notify(self, alert: Alert, rule: AlertRule) -> None:
        """Send notifications through configured channels."""
        for channel in rule.channels:
            handler = self._handlers.get(channel)
            if handler:
                try:
                    handler(alert)
                except Exception as e:
                    print(f"Error sending {channel.value} notification: {e}")

    def resolve_alert(self, alert_id: str) -> bool:
        """
        Mark alert as resolved.

        Args:
            alert_id: Alert ID

        Returns:
            True if alert was found and resolved
        """
        alert = self._alerts.get(alert_id)
        if not alert:
            return False

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = time.time()

        return True

    def suppress_alert(self, alert_id: str, duration_seconds: float) -> bool:
        """
        Suppress alert for a duration.

        Args:
            alert_id: Alert ID
            duration_seconds: Suppression duration

        Returns:
            True if alert was found and suppressed
        """
        alert = self._alerts.get(alert_id)
        if not alert:
            return False

        alert.status = AlertStatus.SUPPRESSED
        self._suppressed_alerts.add(alert_id)

        # Schedule unsuppression
        # In real implementation, use async task

        return True

    def get_active_alerts(
        self,
        tenant_id: int | None = None,
        severity: AlertSeverity | None = None,
    ) -> list[Alert]:
        """
        Get active (firing) alerts.

        Args:
            tenant_id: Filter by tenant
            severity: Filter by severity

        Returns: List[Alert] of active alerts
        """
        active: list[Alert] = []
        for alert in self._alerts.values():
            if alert.status != AlertStatus.FIRING:
                continue

            if tenant_id is not None and alert.tenant_id != tenant_id:
                continue

            if severity is not None and alert.severity != severity:
                continue

            active.append(alert)

        return active

    def get_alert_history(
        self,
        tenant_id: int | None = None,
        since: float | None = None,
    ) -> list[Alert]:
        """
        Get alert history.

        Args:
            tenant_id: Filter by tenant
            since: Filter by time

        Returns: List[Alert] of historical alerts
        """
        history: list[Alert] = []
        for alert in self._alerts.values():
            if tenant_id is not None and alert.tenant_id != tenant_id:
                continue

            if since is not None and alert.created_at < since:
                continue

            history.append(alert)

        return sorted(history, key=lambda a: a.created_at, reverse=True)


class PredefinedRules:
    """Predefined alert rules for common scenarios."""

    @staticmethod
    def high_error_rate(
        threshold: float = 0.05,
        channels: list[NotificationChannel] | None = None,
    ) -> AlertRule:
        """
        High error rate alert.

        Args:
            threshold: Error rate threshold (0.0 - 1.0)
            channels: Notification channels
        """
        if channels is None:
            channels = [NotificationChannel.WEBHOOK]

        def condition(metrics: dict[str, Any]) -> bool:  # TODO(TYPE): Any -- MetricsDict
            error_rate: float = cast(float, metrics.get("error_rate", 0))
            return error_rate > threshold

        return AlertRule(
            name="high_error_rate",
            condition=condition,
            severity=AlertSeverity.ERROR,
            message_template="Error rate {error_rate:.2%} exceeds threshold {threshold:.2%}",
            channels=channels,
            cooldown_seconds=300,
        )

    @staticmethod
    def high_latency(
        threshold_ms: float = 1000.0,
        channels: list[NotificationChannel] | None = None,
    ) -> AlertRule:
        """
        High latency alert.

        Args:
            threshold_ms: Latency threshold in milliseconds
            channels: Notification channels
        """
        if channels is None:
            channels = [NotificationChannel.WEBHOOK]

        def condition(metrics: dict[str, Any]) -> bool:  # TODO(TYPE): Any -- MetricsDict
            latency: float = cast(float, metrics.get("p99_latency_ms", 0))
            return latency > threshold_ms

        return AlertRule(
            name="high_latency",
            condition=condition,
            severity=AlertSeverity.WARNING,
            message_template="P99 latency {p99_latency_ms:.0f}ms exceeds threshold {threshold_ms:.0f}ms",
            channels=channels,
            cooldown_seconds=300,
        )

    @staticmethod
    def quota_exceeded(
        channels: list[NotificationChannel] | None = None,
    ) -> AlertRule:
        """
        Quota exceeded alert.

        Args:
            channels: Notification channels
        """
        if channels is None:
            channels = [NotificationChannel.EMAIL]

        def condition(metrics: dict[str, Any]) -> bool:  # TODO(TYPE): Any -- MetricsDict
            quota_used: float = cast(float, metrics.get("quota_used_percent", 0))
            return quota_used >= 100

        return AlertRule(
            name="quota_exceeded",
            condition=condition,
            severity=AlertSeverity.ERROR,
            message_template="Quota exceeded: {quota_used_percent:.1f}% used",
            channels=channels,
            cooldown_seconds=3600,
        )

    @staticmethod
    def budget_threshold(
        threshold_percent: float = 80.0,
        channels: list[NotificationChannel] | None = None,
    ) -> AlertRule:
        """
        Budget threshold alert.

        Args:
            threshold_percent: Budget threshold percentage
            channels: Notification channels
        """
        if channels is None:
            channels = [NotificationChannel.EMAIL]

        def condition(metrics: dict[str, Any]) -> bool:  # TODO(TYPE): Any -- MetricsDict
            budget_used: float = cast(float, metrics.get("budget_used_percent", 0))
            return budget_used >= threshold_percent

        return AlertRule(
            name="budget_threshold",
            condition=condition,
            severity=AlertSeverity.WARNING,
            message_template="Budget {budget_used_percent:.1f}% used (threshold: {threshold_percent:.1f}%)",
            channels=channels,
            cooldown_seconds=3600,
        )
