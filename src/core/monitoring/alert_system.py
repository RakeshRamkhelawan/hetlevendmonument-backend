#!/usr/bin/env python3
"""
Alert System for M-MDP Performance Monitoring
ASCII-compliant alert handling and notification system
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from collections.abc import Callable

logger = logging.getLogger("AlertSystem")


class AlertLevel(Enum):
    """Alert severity levels"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class Alert:
    """Alert data structure"""

    level: AlertLevel
    message: str
    component: str
    timestamp: datetime
    metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    resolved: bool = False


class AlertSystem:
    """Alert management and notification system"""

    def __init__(self) -> None:
        self.active_alerts: list[Alert] = []
        self.alert_handlers: dict[AlertLevel, list[Callable[..., Any]]] = {  # TODO(TYPE): replace Any with concrete type
            level: [] for level in AlertLevel
        }

    def trigger_alert(
        self, level: AlertLevel, message: str, component: str, **metadata: Any  # TODO(TYPE): replace Any with concrete type
    ) -> Alert:
        """Trigger a new alert"""
        alert = Alert(
            level=level,
            message=message,
            component=component,
            timestamp=datetime.now(timezone.utc),
            metadata=metadata,
        )

        self.active_alerts.append(alert)
        logger.info(f"Alert triggered: {level.value} - {message}")

        # Call registered handlers
        for handler in self.alert_handlers.get(level, []):
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")

        return alert

    def resolve_alert(self, alert: Alert) -> None:
        """Mark alert as resolved"""
        alert.resolved = True
        logger.info(f"Alert resolved: {alert.message}")

    def get_active_alerts(self) -> list[Alert]:
        """Get all active (unresolved) alerts"""
        return [alert for alert in self.active_alerts if not alert.resolved]

    def add_handler(self, level: AlertLevel, handler: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Add alert handler for specific level"""
        self.alert_handlers[level].append(handler)


# Global alert system instance
_alert_system: AlertSystem | None = None


def get_alert_system() -> AlertSystem:
    """Get global alert system instance"""
    global _alert_system
    if _alert_system is None:
        _alert_system = AlertSystem()
    return _alert_system
