"""Self-Healing sub-router (ADR-033 Laag 1)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from src.core.api.dependencies import require_admin_user

from src.core.auth.api_deps import UserResponse, require_scopes, OAuth2Scope
from src.core.api.autonomous_endpoints import FailureReportModel
from src.core.autonomy.self_healing_system import get_self_healing_system

logger = logging.getLogger(__name__)

healing_router = APIRouter(prefix="/api/v1/autonomous")


@healing_router.post("/healing/report-failure")
async def report_system_failure(
    failure: FailureReportModel,
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Report a system failure for autonomous healing. Requires: AGENTS_WRITE

    Uitgeschakeld sinds ADR-036 D12.5 (CRITICAL/P0,
    docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md): kan met
    auto_repair=true een reparatieplan direct laten UITVOEREN zonder ooit
    GovernanceContract.is_action_permitted() aan te roepen. Zelfde
    onderliggende oorzaak als D12.5, ontdekt tijdens de Gate 2-doc-review van
    die fix. Zie tests/architecture/test_agent_factory_governance_gate.py.
    """
    raise HTTPException(
        status_code=503,
        detail=(
            "Self-healing failure reporting is temporarily disabled pending a "
            "governance review (ADR-036 D12.5)."
        ),
    )


@healing_router.get("/healing/status")
async def get_healing_system_status(
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get self-healing system status and metrics. Requires: AGENTS_READ"""
    try:
        healing_system = get_self_healing_system()
        status = await healing_system.get_system_status()
        return {
            "overall_health": status.get("system_status", "unknown"),
            "active_failures": status.get("failure_history_count", 0),
            "repairs_in_progress": status.get("repairs_in_progress", 0),
            "repairs_completed": status.get("repair_history_count", 0),
            "success_rate": status.get("healing_metrics", {}).get("healing_success_rate", 0.0),
            "avg_repair_time": status.get("healing_metrics", {}).get("mean_time_to_repair", 0.0),
            "system_uptime": status.get("uptime", 0.0),
            "component_health": status.get("components", {}),
            "recent_failures": status.get("recent_failures", 0),
            "monitoring_active": status.get("monitoring_active", False),
            "registered_components": status.get("registered_components", 0),
            "emergency_protocols": status.get("emergency_protocols_available", 0),
        }
    except Exception as e:
        logger.error("Failed to get healing status: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@healing_router.post("/healing/execute-repair/{failure_id}")
async def execute_repair(
    failure_id: str,
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute repair plan for a specific failure. Requires: ADMIN_ALL

    Uitgeschakeld sinds ADR-036 D12.5 (CRITICAL/P0,
    docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md): voert een
    reparatieplan direct uit zonder ooit GovernanceContract.
    is_action_permitted() aan te roepen. Zelfde onderliggende oorzaak als
    D12.5, ontdekt tijdens de Gate 2-doc-review van die fix.
    """
    raise HTTPException(
        status_code=503,
        detail=(
            "Self-healing repair execution is temporarily disabled pending a "
            "governance review (ADR-036 D12.5)."
        ),
    )
