"""
Comprehensive Monitoring Dashboard - TAAK 3.1 Implementation
Real-time system monitoring and health dashboard for Sanskriti Setu
"""

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.database.database import db_manager
from src.core.monitoring.alert_system import AlertSystem
from src.core.monitoring.metrics_collector import (
    SystemMetrics,
    collect_system_metrics,
    get_basic_health_check,
)
from src.core.monitoring.performance_monitor import PerformanceMonitor

logger = logging.getLogger(__name__)


@dataclass
class AgentStatus:
    """Agent status information"""

    agent_id: str
    agent_type: str
    status: str
    last_seen: datetime
    load_factor: float
    capabilities: list[str]
    performance_score: float = 0.0


@dataclass
class DatabaseHealth:
    """Database health information"""

    connection_status: bool
    active_connections: int
    response_time_ms: float
    last_check: datetime
    error_count: int = 0


@dataclass
class DashboardMetrics:
    """Complete dashboard metrics"""

    timestamp: datetime
    system_health: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    agent_status: list[AgentStatus]
    database_health: DatabaseHealth
    performance_metrics: dict[str, float]
    learning_progress: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    recent_alerts: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    resource_usage: SystemMetrics


class MonitoringDashboard:
    """
    Comprehensive monitoring dashboard for Sanskriti Setu backend
    Provides real-time system health, performance metrics, and operational insights
    """

    def __init__(self) -> None:
        self.alert_system = AlertSystem()
        self.performance_monitor = PerformanceMonitor()
        self.learning_engine: Any | None = None  # TODO(TYPE): replace Any with concrete type
        self._last_update: datetime | None = None
        self._cache_duration = 5  # Cache metrics for 5 seconds
        self._cached_metrics: dict[str, object] | None = None

        logger.info("Monitoring dashboard initialized")

    async def initialize(self) -> bool:
        """Initialize dashboard components"""
        try:
            # Initialize learning engine
            from src.core.ai.adaptive_learning_engine import get_adaptive_learning_engine

            self.learning_engine = await get_adaptive_learning_engine()

            # Initialize alert system if not already done
            await self.alert_system.initialize()  # type: ignore[attr-defined]

            logger.info("Dashboard components initialized successfully")
            return True

        except Exception as e:
            logger.error(
                "Failed to initialize dashboard components: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            return False

    async def get_system_overview(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get complete system overview with caching"""
        now = datetime.now(timezone.utc)

        # Return cached data if recent enough
        if (
            self._cached_metrics
            and self._last_update
            and (now - self._last_update).total_seconds() < self._cache_duration
        ):
            return self._cached_metrics

        try:
            metrics = DashboardMetrics(
                timestamp=now,
                system_health=await self._get_system_health(),
                agent_status=await self._get_agent_status(),
                database_health=await self._get_database_health(),
                performance_metrics=await self._get_performance_metrics(),
                learning_progress=await self._get_learning_progress(),
                recent_alerts=await self._get_recent_alerts(),
                resource_usage=collect_system_metrics(),
            )

            # Convert to dict and cache
            metrics_dict = asdict(metrics)
            self._cached_metrics = metrics_dict
            self._last_update = now

            return metrics_dict

        except Exception as e:
            logger.error(
                "Failed to get system overview: %s: %s", type(e).__name__, e, exc_info=True
            )
            return self._get_fallback_metrics()

    async def _get_system_health(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get overall system health status"""
        try:
            # Basic system health
            basic_health = get_basic_health_check()

            # Database health
            db_healthy = await db_manager.health_check()

            # Learning engine health
            learning_healthy = True
            if self.learning_engine:
                try:
                    stats = await self.learning_engine.get_learning_stats()
                    learning_healthy = stats.get("events_processed", 0) >= 0
                except Exception:
                    learning_healthy = False

            # Aggregate health status
            components_healthy = [
                basic_health.get("status") == "healthy",
                db_healthy,
                learning_healthy,
            ]

            overall_status = "healthy" if all(components_healthy) else "warning"
            if not any(components_healthy):
                overall_status = "critical"

            return {
                "overall_status": overall_status,
                "components": {
                    "system": basic_health.get("status", "unknown"),
                    "database": "healthy" if db_healthy else "unhealthy",
                    "learning_engine": "healthy" if learning_healthy else "unhealthy",
                    "alerts": self._get_alerts_health_status(),
                },
                "uptime_hours": self._get_uptime_hours(),
                "last_check": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error("Failed to get system health: %s: %s", type(e).__name__, e, exc_info=True)
            return {
                "overall_status": "unknown",
                "components": {},
                "uptime_hours": 0,
                "last_check": datetime.now(timezone.utc).isoformat(),
            }

    async def _get_agent_status(self) -> list[AgentStatus]:
        """Get status of all registered agents"""
        try:
            # TODO: Integrate with actual agent registry
            # For now, return mock data based on available agents
            agents: list[AgentStatus] = [
                AgentStatus(
                    agent_id="knowledge_agent",
                    agent_type="knowledge",
                    status="active",
                    last_seen=datetime.now(timezone.utc),
                    load_factor=0.3,
                    capabilities=["knowledge_search", "document_analysis"],
                    performance_score=0.85,
                ),
                AgentStatus(
                    agent_id="sentiment_agent",
                    agent_type="sentiment",
                    status="active",
                    last_seen=datetime.now(timezone.utc),
                    load_factor=0.2,
                    capabilities=["sentiment_analysis", "emotion_detection"],
                    performance_score=0.92,
                ),
                AgentStatus(
                    agent_id="diagnostics_agent",
                    agent_type="diagnostics",
                    status="active",
                    last_seen=datetime.now(timezone.utc),
                    load_factor=0.1,
                    capabilities=["system_diagnostics", "health_monitoring"],
                    performance_score=0.78,
                ),
            ]

            return agents

        except Exception as e:
            logger.error("Failed to get agent status: %s: %s", type(e).__name__, e, exc_info=True)
            return []

    async def _get_database_health(self) -> DatabaseHealth:
        """Get detailed database health information"""
        try:
            start_time = datetime.now(timezone.utc)

            # Test database connection
            connection_healthy = await db_manager.health_check()

            end_time = datetime.now(timezone.utc)
            response_time = (end_time - start_time).total_seconds() * 1000

            return DatabaseHealth(
                connection_status=connection_healthy,
                active_connections=self._get_db_connection_count(),
                response_time_ms=round(response_time, 2),
                last_check=end_time,
                error_count=0,  # TODO: Implement error tracking
            )

        except Exception as e:
            logger.error(
                "Failed to get database health: %s: %s", type(e).__name__, e, exc_info=True
            )
            return DatabaseHealth(
                connection_status=False,
                active_connections=0,
                response_time_ms=0.0,
                last_check=datetime.now(timezone.utc),
                error_count=1,
            )

    async def _get_performance_metrics(self) -> dict[str, float]:
        """Get system performance metrics"""
        try:
            # Get current system metrics
            system_metrics = collect_system_metrics()

            # TODO: Integrate with performance monitor for more detailed metrics
            return {
                "cpu_usage_percent": system_metrics.cpu_percent,
                "memory_usage_percent": system_metrics.memory_percent,
                "disk_usage_percent": system_metrics.disk_usage_percent,
                "network_connections": float(system_metrics.network_connections),
                "process_count": float(system_metrics.process_count),
                "average_response_time_ms": 45.2,  # TODO: Calculate from actual requests
                "requests_per_minute": 12.5,  # TODO: Calculate from actual requests
                "error_rate_percent": 0.1,  # TODO: Calculate from actual errors
            }

        except Exception as e:
            logger.error(
                "Failed to get performance metrics: %s: %s", type(e).__name__, e, exc_info=True
            )
            return {}

    async def _get_learning_progress(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get adaptive learning engine progress and statistics"""
        try:
            if not self.learning_engine:
                return {"status": "not_available"}

            stats = await self.learning_engine.get_learning_stats()

            return {
                "status": "active",
                "total_events": stats.get("total_events", 0),
                "events_processed": stats.get("events_processed", 0),
                "insights_generated": stats.get("insights_generated", 0),
                "adaptations_applied": stats.get("adaptations_applied", 0),
                "learning_rate_per_hour": stats.get("learning_rate_per_hour", 0.0),
                "active_insights": stats.get("active_insights", 0),
                "last_analysis": stats.get("last_analysis"),
                "insight_distribution": stats.get("insight_distribution", {}),
            }

        except Exception as e:
            logger.error(
                "Failed to get learning progress: %s: %s", type(e).__name__, e, exc_info=True
            )
            return {"status": "error", "error": str(e)}

    async def _get_recent_alerts(
        self,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get recent system alerts"""
        try:
            # Integrate with actual alert system
            from src.core.monitoring.alert_system import get_alert_system

            alert_system = get_alert_system()
            active_alerts = alert_system.get_active_alerts()

            # Convert alerts to dict format for API response
            recent_alerts = [
                {
                    "id": f"alert_{hash(alert)}",
                    "level": alert.level.value,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "component": alert.component,
                    "resolved": alert.resolved,
                }
                for alert in active_alerts[-10:]
            ]

            return recent_alerts

        except Exception as e:
            logger.error("Failed to get recent alerts: %s: %s", type(e).__name__, e, exc_info=True)
            return []

    def _get_uptime_hours(self) -> float:
        """Calculate system uptime in hours"""
        try:
            # TODO: Implement proper uptime tracking
            # For now, return a mock value
            return 24.5
        except Exception:
            return 0.0

    def _get_db_connection_count(self) -> int:
        """Get current database connection count"""
        try:
            # TODO: Get actual connection count from pool
            return 5
        except Exception:
            return 0

    def _get_alerts_health_status(self) -> str:
        """Get alert system health status based on active alerts"""
        try:
            from src.core.monitoring.alert_system import get_alert_system

            alert_system = get_alert_system()
            active_alerts = alert_system.get_active_alerts()

            # Check for critical or emergency alerts
            critical_count = sum(
                1 for alert in active_alerts if alert.level.value in ["critical", "emergency"]
            )

            if critical_count > 0:
                return "critical"
            elif len(active_alerts) > 5:
                return "warning"
            else:
                return "healthy"
        except Exception as e:
            logger.error(
                "Failed to get alerts health status: %s: %s", type(e).__name__, e, exc_info=True
            )
            return "unknown"

    def _get_fallback_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return fallback metrics when main collection fails"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_health": {
                "overall_status": "unknown",
                "components": {},
                "uptime_hours": 0,
                "last_check": datetime.now(timezone.utc).isoformat(),
            },
            "agent_status": [],
            "database_health": {
                "connection_status": False,
                "active_connections": 0,
                "response_time_ms": 0.0,
                "last_check": datetime.now(timezone.utc).isoformat(),
                "error_count": 1,
            },
            "performance_metrics": {},
            "learning_progress": {"status": "unknown"},
            "recent_alerts": [],
            "resource_usage": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "disk_usage_percent": 0.0,
                "network_connections": 0,
                "process_count": 0,
            },
        }


# Global dashboard instance
_dashboard_instance: MonitoringDashboard | None = None


async def get_monitoring_dashboard() -> MonitoringDashboard:
    """Get global monitoring dashboard instance"""
    global _dashboard_instance

    if _dashboard_instance is None:
        _dashboard_instance = MonitoringDashboard()
        await _dashboard_instance.initialize()

    return _dashboard_instance


# Export for external use
__all__ = [
    "MonitoringDashboard",
    "DashboardMetrics",
    "AgentStatus",
    "DatabaseHealth",
    "get_monitoring_dashboard",
]
