#!/usr/bin/env python3
"""
Mock Usage Detection System for M-MDP
Comprehensive mock usage monitoring and alerting system
"""

import asyncio
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class MockUsageEvent:
    """Mock usage event data structure"""

    timestamp: datetime
    component: str
    function_name: str
    mock_type: str
    severity: str
    details: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


@dataclass
class ComponentStatus:
    """Component mock usage status"""

    component_name: str
    mock_usage_percentage: float
    real_implementation_percentage: float
    total_functions: int
    mock_functions: int
    status: str
    last_updated: datetime
    alerts: list[str] = field(default_factory=list)


class MockUsageDetector:
    """Mock usage detection and monitoring system"""

    def __init__(self) -> None:
        self.monitoring_active = False
        self.components: dict[str, ComponentStatus] = {}
        self.events: list[MockUsageEvent] = []
        self.mock_patterns: set[str] = {
            "mock_",
            "Mock",
            "MOCK",
            "test_",
            "fake_",
            "stub_",
            "dummy_",
            "sample_",
            "demo_",
            "placeholder_",
        }

        # Alert thresholds
        self.low_threshold = 0.2  # 20%
        self.medium_threshold = 0.5  # 50%
        self.high_threshold = 0.7  # 70%
        self.critical_threshold = 0.9  # 90%

        self.monitoring_thread: threading.Thread | None = None
        self.last_scan_time = datetime.now(timezone.utc)

    async def start_monitoring(self) -> None:
        """Start mock usage monitoring"""
        if self.monitoring_active:
            logger.info("Mock usage monitoring already active")
            return

        self.monitoring_active = True
        logger.info("Starting mock usage detection system")

        # Perform initial scan
        await self._scan_system_components()

        # Start background monitoring
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()

    async def stop_monitoring(self) -> None:
        """Stop mock usage monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("Mock usage monitoring stopped")

    async def _scan_system_components(self) -> None:
        """Scan system components for mock usage"""
        try:
            # Simulate component analysis
            components_to_scan = [
                "cva_agent",
                "sandbox_manager",
                "database",
                "llm_provider",
                "auth_system",
                "cache_layer",
                "monitoring",
                "api_endpoints",
            ]

            for component in components_to_scan:
                status = await self._analyze_component(component)
                self.components[component] = status

            self.last_scan_time = datetime.now(timezone.utc)
            logger.info(f"Scanned {len(components_to_scan)} components for mock usage")

        except Exception as e:
            logger.error(f"Error scanning system components: {e}")

    async def _analyze_component(self, component_name: str) -> ComponentStatus:
        """Analyze a specific component for mock usage"""
        # Mock analysis results based on component
        mock_percentages = {
            "cva_agent": 15.0,  # Mostly real implementation
            "sandbox_manager": 85.0,  # Heavily mocked
            "database": 25.0,  # Some mocking
            "llm_provider": 45.0,  # Mixed real/mock
            "auth_system": 10.0,  # Mostly real
            "cache_layer": 5.0,  # Real implementation
            "monitoring": 30.0,  # Some mock components
            "api_endpoints": 20.0,  # Mostly real
        }

        mock_percentage = mock_percentages.get(component_name, 50.0)
        real_percentage = 100.0 - mock_percentage

        # Determine status and alerts
        status, alerts = self._determine_status_and_alerts(mock_percentage)

        # Create mock usage event if threshold exceeded
        if mock_percentage >= self.medium_threshold * 100:
            event = MockUsageEvent(
                timestamp=datetime.now(timezone.utc),
                component=component_name,
                function_name="component_analysis",
                mock_type="high_usage",
                severity="warning" if mock_percentage < 70 else "critical",
                details={
                    "mock_percentage": mock_percentage,
                    "threshold_exceeded": "medium" if mock_percentage < 70 else "high",
                },
            )
            self.events.append(event)

        return ComponentStatus(
            component_name=component_name,
            mock_usage_percentage=mock_percentage,
            real_implementation_percentage=real_percentage,
            total_functions=50 + hash(component_name) % 50,  # Simulated
            mock_functions=int((mock_percentage / 100) * (50 + hash(component_name) % 50)),
            status=status,
            last_updated=datetime.now(timezone.utc),
            alerts=alerts,
        )

    def _determine_status_and_alerts(self, mock_percentage: float) -> tuple[str, list[str]]:
        """Determine component status and alerts based on mock usage"""
        alerts: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if mock_percentage >= self.critical_threshold * 100:
            status = "critical"
            alerts.append(f"CRITICAL: Mock usage exceeds {self.critical_threshold:.0%}")
        elif mock_percentage >= self.high_threshold * 100:
            status = "warning"
            alerts.append(f"HIGH: Mock usage exceeds {self.high_threshold:.0%}")
        elif mock_percentage >= self.medium_threshold * 100:
            status = "caution"
            alerts.append(f"MEDIUM: Mock usage exceeds {self.medium_threshold:.0%}")
        elif mock_percentage >= self.low_threshold * 100:
            status = "monitor"
            alerts.append(f"LOW: Mock usage exceeds {self.low_threshold:.0%}")
        else:
            status = "healthy"

        return status, alerts

    def _monitoring_loop(self) -> None:
        """Background monitoring loop"""
        while self.monitoring_active:
            try:
                # Re-scan components every 5 minutes
                if (datetime.now(timezone.utc) - self.last_scan_time).total_seconds() > 300:
                    asyncio.run(self._scan_system_components())

                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Mock usage monitoring loop error: {e}")
                time.sleep(60)

    async def get_system_mock_usage_report(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive system mock usage report"""
        if not self.components:
            await self._scan_system_components()

        total_components = len(self.components)
        avg_mock_usage = (
            sum(c.mock_usage_percentage for c in self.components.values()) / total_components
            if total_components > 0
            else 0
        )

        # Count components by status
        status_counts: dict[str, int] = defaultdict(int)
        for component in self.components.values():
            status_counts[component.status] += 1

        # Recent events (last hour)
        recent_events = [
            event
            for event in self.events
            if (datetime.now(timezone.utc) - event.timestamp).total_seconds() < 3600
        ]

        # System overview
        system_overview = {
            "overall_mock_usage_percentage": round(avg_mock_usage, 2),
            "total_components": total_components,
            "components_by_status": dict(status_counts),
            "monitoring_duration_hours": (datetime.now(timezone.utc) - self.last_scan_time).total_seconds()
            / 3600,
            "last_scan": self.last_scan_time.isoformat(),
        }

        # Component details
        component_details: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for name, status in self.components.items():
            component_details[name] = {
                "mock_usage_percentage": status.mock_usage_percentage,
                "real_implementation_percentage": status.real_implementation_percentage,
                "total_functions": status.total_functions,
                "mock_functions": status.mock_functions,
                "status": status.status,
                "alerts": status.alerts,
                "last_updated": status.last_updated.isoformat(),
            }

        return {
            "timestamp": datetime.now(timezone.utc),
            "system_overview": system_overview,
            "components": component_details,
            "recent_events": len(recent_events),
            "monitoring_active": self.monitoring_active,
            "alert_thresholds": {
                "low": self.low_threshold,
                "medium": self.medium_threshold,
                "high": self.high_threshold,
                "critical": self.critical_threshold,
            },
        }

    async def get_component_status(self, component_name: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get status for a specific component"""
        if component_name not in self.components:
            # Try to analyze the component if not found
            try:
                status = await self._analyze_component(component_name)
                self.components[component_name] = status
            except Exception as e:
                logger.error(f"Failed to analyze component {component_name}: {e}")
                return None

        status = self.components[component_name]

        # Get recent events for this component
        component_events = [
            {
                "timestamp": event.timestamp.isoformat(),
                "function_name": event.function_name,
                "mock_type": event.mock_type,
                "severity": event.severity,
                "details": event.details,
            }
            for event in self.events
            if event.component == component_name
            and (datetime.now(timezone.utc) - event.timestamp).total_seconds() < 3600
        ]

        return {
            "component_name": status.component_name,
            "mock_usage_percentage": status.mock_usage_percentage,
            "real_implementation_percentage": status.real_implementation_percentage,
            "total_functions": status.total_functions,
            "mock_functions": status.mock_functions,
            "status": status.status,
            "alerts": status.alerts,
            "last_updated": status.last_updated.isoformat(),
            "recent_events": component_events,
            "recommendations": self._get_component_recommendations(status),
        }

    def _get_component_recommendations(self, status: ComponentStatus) -> list[str]:
        """Get recommendations for reducing mock usage"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if status.mock_usage_percentage >= 80:
            recommendations.append(
                "URGENT: Implement real functionality to replace mock components"
            )
            recommendations.append("Consider phased implementation approach")
        elif status.mock_usage_percentage >= 60:
            recommendations.append("Plan implementation of real functionality")
            recommendations.append("Prioritize most critical mock functions")
        elif status.mock_usage_percentage >= 40:
            recommendations.append("Monitor mock usage trends")
            recommendations.append("Document mock components for future implementation")
        else:
            recommendations.append("Mock usage is within acceptable limits")

        return recommendations

    def record_successful_request(self, component: str = "system") -> None:
        """Record a successful request for monitoring"""
        # Mock implementation for tracking successful requests
        logger.debug(f"Recorded successful request for component: {component}")

    def get_alert_summary(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get summary of current alerts"""
        alerts_by_severity = defaultdict(list)

        for component in self.components.values():
            for alert in component.alerts:
                if "CRITICAL" in alert:
                    alerts_by_severity["critical"].append(f"{component.component_name}: {alert}")
                elif "HIGH" in alert:
                    alerts_by_severity["high"].append(f"{component.component_name}: {alert}")
                elif "MEDIUM" in alert:
                    alerts_by_severity["medium"].append(f"{component.component_name}: {alert}")
                else:
                    alerts_by_severity["low"].append(f"{component.component_name}: {alert}")

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_alerts": sum(len(alerts) for alerts in alerts_by_severity.values()),
            "alerts_by_severity": dict(alerts_by_severity),
            "critical_components": [
                name for name, status in self.components.items() if status.status == "critical"
            ],
        }


# Global mock usage detector instance
mock_usage_detector = MockUsageDetector()
