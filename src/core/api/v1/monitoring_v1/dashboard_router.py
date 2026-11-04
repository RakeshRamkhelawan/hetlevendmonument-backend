# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Monitoring dashboard endpoints (REST + WebSocket + HTML page).

Migrated from monitoring_dashboard_endpoints.py (SP-API-003 Dag 4).
Routes: GET /dashboard/health, GET /system-overview, GET /system-health,
        GET /agents, GET /performance, GET /learning, GET /alerts,
        WS /ws/dashboard, WS /ws/alerts, GET /dashboard (HTML),
        GET /get_dashboard, GET /get_widget/{widget_id}, GET /overview,
        GET /metrics (Prometheus), GET /api/metrics
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from src.core.api.dependencies import require_admin_user
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from src.core.api.v1.monitoring_v1.dependencies import (
    OAuth2Scope,
    UserResponse,
    get_current_user,
    require_scopes,
)
from src.core.auth import UserResponse  # noqa: F811 -- re-import for explicit clarity
from src.core.middleware.tenant_context import set_tenant_id
from src.core.monitoring.dashboard import get_monitoring_dashboard

logger = logging.getLogger(__name__)

router = APIRouter()

# Active WebSocket connections
active_connections: list[WebSocket] = []


class ConnectionManager:
    """Manage WebSocket connections for real-time dashboard updates."""

    def __init__(self) -> None:
        self._connections: dict[int, list[WebSocket]] = {}
        self._tenant_of: dict[int, int] = {}

    async def connect(self, websocket: WebSocket, tenant_id: int) -> None:
        await websocket.accept()
        self._connections.setdefault(tenant_id, []).append(websocket)
        self._tenant_of[id(websocket)] = tenant_id

    def disconnect(self, websocket: WebSocket) -> None:
        tenant_id = self._tenant_of.pop(id(websocket), None)
        if tenant_id is not None:
            bucket = self._connections.get(tenant_id, [])
            try:
                bucket.remove(websocket)
            except ValueError:
                pass
            if not bucket:
                self._connections.pop(tenant_id, None)

    async def send_to_tenant(self, tenant_id: int, data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        bucket = list(self._connections.get(tenant_id, []))
        if not bucket:
            return
        disconnected: list[WebSocket] = []
        for connection in bucket:
            try:
                await connection.send_json(data)
            except Exception as e:
                logger.warning("Failed to send to tenant %s client: %s", tenant_id, e)
                disconnected.append(connection)
        for connection in disconnected:
            self.disconnect(connection)

    async def send_to_connection(self, websocket: WebSocket, data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.warning("Failed to send to specific client: %s", e)
            self.disconnect(websocket)

    @property
    def active_connections(self) -> list[WebSocket]:
        return [ws for bucket in self._connections.values() for ws in bucket]


connection_manager = ConnectionManager()


@router.get("/dashboard/health")
async def dashboard_health(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Health check endpoint for monitoring dashboard. Requires: OAuth2Scope.AGENTS_READ"""
    try:
        logger.info("User %s checking dashboard health", current_user.id)
        dashboard = await get_monitoring_dashboard()
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_connections": len(connection_manager.active_connections),
            "dashboard_initialized": dashboard is not None,
        }
    except Exception as e:
        logger.exception("Dashboard health check failed: %s", e)
        raise HTTPException(status_code=500, detail="Dashboard health check failed")


@router.get("/system-overview")
async def get_system_overview(
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get complete system overview (REST endpoint). Requires: OAuth2Scope.AGENTS_READ"""
    try:
        logger.info("User %s requesting system overview", current_user.id)
        dashboard = await get_monitoring_dashboard()
        overview = await dashboard.get_system_overview()
        return overview
    except Exception as e:
        logger.exception("Failed to get system overview: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve system overview")


@router.get("/system-health")
async def get_system_health(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get system health status. Requires: OAuth2Scope.AGENTS_READ"""
    try:
        logger.info("User %s requesting system health", current_user.id)
        dashboard = await get_monitoring_dashboard()
        overview = await dashboard.get_system_overview()
        return cast(dict[str, Any], overview.get("system_health", {}))
    except Exception as e:
        logger.exception("Failed to get system health: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve system health")


@router.get("/agents")
async def get_agent_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Get all agent status information. Requires: OAuth2Scope.AGENTS_READ"""
    try:
        logger.info("User %s requesting agent status", current_user.id)
        dashboard = await get_monitoring_dashboard()
        overview = await dashboard.get_system_overview()
        return cast(list[dict[str, Any]], overview.get("agent_status", []))
    except Exception as e:
        logger.exception("Failed to get agent status: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve agent status")


@router.get("/performance")
async def get_performance_metrics(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get system performance metrics. Requires: OAuth2Scope.AGENTS_READ"""
    try:
        logger.info("User %s requesting performance metrics", current_user.id)
        dashboard = await get_monitoring_dashboard()
        overview = await dashboard.get_system_overview()
        return {
            "performance_metrics": overview.get("performance_metrics", {}),
            "resource_usage": overview.get("resource_usage", {}),
            "database_health": overview.get("database_health", {}),
        }
    except Exception as e:
        logger.exception("Failed to get performance metrics: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve performance metrics")


@router.get("/learning")
async def get_learning_progress(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get adaptive learning engine progress. Requires: OAuth2Scope.AGENTS_READ"""
    try:
        logger.info("User %s requesting learning progress", current_user.id)
        dashboard = await get_monitoring_dashboard()
        overview = await dashboard.get_system_overview()
        return cast(dict[str, Any], overview.get("learning_progress", {}))
    except Exception as e:
        logger.exception("Failed to get learning progress: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve learning progress")


@router.get("/alerts")
async def get_recent_alerts(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get recent system alerts. Requires: OAuth2Scope.AGENTS_READ"""
    try:
        logger.info("User %s requesting recent alerts", current_user.id)
        dashboard = await get_monitoring_dashboard()
        overview = await dashboard.get_system_overview()
        return cast(dict[str, Any], overview.get("recent_alerts", []))
    except Exception as e:
        logger.exception("Failed to get recent alerts: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve recent alerts")


@router.websocket("/ws/dashboard")
async def dashboard_websocket(
    websocket: WebSocket,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> None:
    """WebSocket endpoint for real-time dashboard updates. Requires: OAuth2Scope.AGENTS_READ"""
    set_tenant_id(current_user.tenant_id)
    await connection_manager.connect(websocket, tenant_id=current_user.tenant_id)
    logger.info(
        "User %s (tenant %s) connected to dashboard WebSocket",
        current_user.id,
        current_user.tenant_id,
    )

    try:
        dashboard = await get_monitoring_dashboard()
        initial_data = await dashboard.get_system_overview()
        await connection_manager.send_to_connection(
            websocket, {"type": "initial_data", "data": initial_data}
        )

        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            except TimeoutError:
                try:
                    updated_data = await dashboard.get_system_overview()
                    await connection_manager.send_to_connection(
                        websocket,
                        {
                            "type": "update",
                            "data": updated_data,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                except Exception as e:
                    logger.error("Failed to send periodic update: %s", e, exc_info=True)
                    break
            except Exception as e:
                logger.info("WebSocket receive error (client may have disconnected): %s", e)
                break

    except WebSocketDisconnect:
        logger.info("User %s disconnected from dashboard WebSocket", current_user.id)
    except Exception as e:
        logger.exception("Dashboard WebSocket error: %s", e)
    finally:
        connection_manager.disconnect(websocket)


@router.websocket("/ws/alerts")
async def alerts_websocket(
    websocket: WebSocket,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> None:
    """WebSocket endpoint for real-time alert notifications. Requires: OAuth2Scope.AGENTS_READ"""
    set_tenant_id(current_user.tenant_id)
    await connection_manager.connect(websocket, tenant_id=current_user.tenant_id)

    try:
        await connection_manager.send_to_connection(
            websocket,
            {"type": "alert_status", "data": {"active_alerts": 0, "status": "monitoring"}},
        )

        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except TimeoutError:
                await connection_manager.send_to_connection(
                    websocket,
                    {"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()},
                )
            except Exception as e:
                logger.info("Alert WebSocket receive error: %s", e)
                break

    except WebSocketDisconnect:
        logger.info("User %s disconnected from alerts WebSocket", current_user.id)
    except Exception as e:
        logger.exception("Alert WebSocket error: %s", e)
    finally:
        connection_manager.disconnect(websocket)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> str:
    """Serve the monitoring dashboard HTML page. Requires: OAuth2Scope.AGENTS_READ"""
    logger.info("User %s accessing dashboard page", current_user.id)
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Sanskriti Setu - Monitoring Dashboard</title>
</head>
<body>
  <h1>Sanskriti Setu - Monitoring Dashboard</h1>
  <p>Real-time system monitoring and health status</p>
  <script>
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(protocol + '//' + window.location.host + '/api/v1/monitoring/ws/dashboard');
    ws.onmessage = function(event) { console.log(JSON.parse(event.data)); };
  </script>
</body>
</html>"""


@router.get("/get_dashboard")
async def get_dashboard() -> JSONResponse:
    """Get complete dashboard with widgets array (test compatibility endpoint)."""
    try:
        dashboard = await get_monitoring_dashboard()
        overview = await dashboard.get_system_overview()
        widgets = [
            {
                "id": 1,
                "type": "system_health",
                "title": "System Health",
                "data": overview.get("system_health", {}),
            },
            {
                "id": 2,
                "type": "agent_stats",
                "title": "Agent Statistics",
                "data": overview.get("agents", {}),
            },
            {
                "id": 3,
                "type": "performance",
                "title": "Performance Metrics",
                "data": overview.get("performance", {}),
            },
        ]
        response = JSONResponse(
            content={
                "status": "success",
                "widgets": widgets,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response
    except Exception as e:
        logger.exception("Failed to get dashboard: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve dashboard")


@router.get("/get_widget/{widget_id}")
async def get_widget(widget_id: int) -> JSONResponse:
    """Get single widget by ID (test compatibility endpoint)."""
    try:
        dashboard = await get_monitoring_dashboard()
        overview = await dashboard.get_system_overview()
        widgets_map = {
            1: {
                "id": 1,
                "type": "system_health",
                "title": "System Health",
                "data": overview.get("system_health", {}),
            },
            2: {
                "id": 2,
                "type": "agent_stats",
                "title": "Agent Statistics",
                "data": overview.get("agents", {}),
            },
            3: {
                "id": 3,
                "type": "performance",
                "title": "Performance Metrics",
                "data": overview.get("performance", {}),
            },
        }
        if widget_id not in widgets_map:
            raise HTTPException(status_code=404, detail=f"Widget {widget_id} not found")
        response = JSONResponse(content={"status": "success", "widget": widgets_map[widget_id]})
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get widget %s: %s", widget_id, e)
        raise HTTPException(status_code=500, detail="Failed to retrieve widget")


@router.get("/overview")
async def get_dashboard_overview() -> JSONResponse:
    """Get dashboard overview with summary statistics."""
    try:
        dashboard = await get_monitoring_dashboard()
        overview = await dashboard.get_system_overview()
        summary = {
            "total_agents": len(overview.get("agents", {}).get("active_agents", [])),
            "system_status": overview.get("system_health", {}).get("status", "unknown"),
            "uptime": overview.get("system_health", {}).get("uptime", 0),
            "active_connections": len(connection_manager.active_connections),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        response = JSONResponse(content={"status": "success", "summary": summary})
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response
    except Exception as e:
        logger.exception("Failed to get overview: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve overview")


@router.get("/metrics", response_class=PlainTextResponse)
async def get_dashboard_metrics() -> str:
    """Prometheus-format metrics endpoint (unauthenticated)."""
    try:
        dashboard = await get_monitoring_dashboard()
        overview = await dashboard.get_system_overview()
        performance = overview.get("performance", {})
        health_score = performance.get("health_score", 1.0)
        lines = ["# TYPE sanskriti_health_score gauge", f"sanskriti_health_score {health_score}"]
        for key, value in performance.items():
            if isinstance(value, (int, float)):
                metric_name = f"sanskriti_system_{key}"
                lines.extend([f"# TYPE {metric_name} gauge", f"{metric_name} {value}"])
        return "\n".join(lines)
    except Exception:
        return "# TYPE sanskriti_health_score gauge\nsanskriti_health_score 0"


@router.get("/api/metrics", response_class=PlainTextResponse)
async def get_api_metrics() -> str:
    """Alias at /api/metrics for Prometheus scraping compatibility."""
    return await get_dashboard_metrics()
