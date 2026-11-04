# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Orchestration health monitor endpoints (ADR-033 Laag 1)."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status

from src.core.api.v1.orchestration.dependencies import (
    AgentHealthMonitorAgent,
    AgentHealthMonitorStatus as AgentHealthStatus,
    get_health_monitor,
)
from src.core.api.v1.orchestration.schemas import (
    AgentHealthSchema,
    HealthRecordRequest,
    HealthReportResponse,
    HealthSnapshotResponse,
    HealthStatus,
)
from src.core.api.v1.orchestration.dependencies import limiter

logger = logging.getLogger(__name__)

__all__ = ["health_router", "get_health_monitor"]

health_router = APIRouter()


def _convert_health_status(health_status: AgentHealthStatus) -> str:
    return health_status.value if hasattr(health_status, "value") else str(health_status).lower()


@health_router.get("/health", response_model=HealthReportResponse)
@limiter.limit("10/minute")
async def get_health_report(
    request: Request,
    response: Response,
    health_monitor: AgentHealthMonitorAgent = Depends(get_health_monitor),
) -> HealthReportResponse:
    """Get full health report for all monitored agents."""
    report = health_monitor.health_report()

    agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for agent_data in report.get("agents", []):
        raw_status = str(agent_data.get("status", "unknown")).lower()
        mapped_status = raw_status if raw_status in HealthStatus._value2member_map_ else "unknown"
        agents.append(
            AgentHealthSchema(
                agent_id=agent_data.get("agent_id", "unknown-agent"),
                agent_type=agent_data.get("agent_type", "unknown"),
                status=HealthStatus(mapped_status),
                error_rate=float(agent_data.get("error_rate", 0.0)),
                success_rate=float(agent_data.get("success_rate", 0.0)),
                avg_latency_ms=float(agent_data.get("avg_latency_ms", 0.0)),
                current_load=float(agent_data.get("current_load", 0.0)),
                tasks_processed=int(agent_data.get("tasks_processed", 0)),
                last_heartbeat=agent_data.get("last_heartbeat"),
                alerts=agent_data.get("alerts", []),
            )
        )

    return HealthReportResponse(
        timestamp=datetime.now(timezone.utc),
        total_agents=report["total_agents"],
        agents=agents,
        by_status=report.get("by_status", {}),
        overall_health_score=report.get("overall_health_score", 0.0),
        degraded_agents=report.get("degraded_agents", []),
    )


@health_router.get("/health/agent/{agent_id}", response_model=HealthSnapshotResponse)
@limiter.limit("30/minute")
async def get_agent_health(
    request: Request,
    response: Response,
    agent_id: str,
    health_monitor: AgentHealthMonitorAgent = Depends(get_health_monitor),
) -> HealthSnapshotResponse:
    """Get health snapshot for a specific agent."""
    snapshot = health_monitor.agent_status(agent_id)

    if snapshot is None:
        return HealthSnapshotResponse(agent_id=agent_id, exists=False)

    return HealthSnapshotResponse(
        agent_id=agent_id,
        exists=True,
        snapshot=AgentHealthSchema(
            agent_id=snapshot.agent_id,
            agent_type=snapshot.agent_type,
            status=HealthStatus(_convert_health_status(snapshot.status)),
            error_rate=snapshot.error_rate,
            success_rate=snapshot.success_rate,
            avg_latency_ms=snapshot.avg_latency_ms,
            current_load=snapshot.current_load,
            tasks_processed=snapshot.tasks_processed,
            last_heartbeat=snapshot.last_heartbeat,
            alerts=snapshot.alerts,
        ),
    )


@health_router.post(
    "/health/record",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
@limiter.limit("60/minute")
async def record_health(
    request: Request,
    response: Response,
    health_record: HealthRecordRequest,
    health_monitor: AgentHealthMonitorAgent = Depends(get_health_monitor),
) -> None:
    """Record health metrics for an agent."""
    await health_monitor.record(
        agent_id=health_record.agent_id,
        agent_type=health_record.agent_type,
        latency_ms=health_record.latency_ms,
        success=health_record.success,
        load=health_record.load,
    )
