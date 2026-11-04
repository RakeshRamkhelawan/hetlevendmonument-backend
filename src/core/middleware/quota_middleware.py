"""
Unified Tenant Quota Enforcement Middleware
Enforces both count-based (users, agents) and usage-based (AI tokens, workflow runs) limits.

Integrated with Sprint 3 Usage Metering.
"""

import logging
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from starlette.types import Receive, Scope, Send

from src.core.database.database import db_manager
from src.core.middleware.tenant_context import get_tenant_id
from src.core.models.rbac_models import Tenant, User
from src.core.shared.security_events import SecurityEvent, log_security_event
from src.core.services.usage_service import UsageService

logger = logging.getLogger(__name__)


class TenantQuotaMiddleware:
    """
    Pure ASGI middleware for tenant resource quota enforcement.
    """

    # Endpoints that trigger quota checks mapped to metric types
    QUOTA_ENDPOINTS = {
        "/api/users": "user",
        "/api/v1/users": "user",
        "/api/auth/register": "user",
        "/api/v1/auth/register": "user",
        "/api/agents": "agent",
        "/api/v1/agents": "agent",
        "/api/v1/workflows": "workflow_run",
        "/api/v1/ai": "ai_token",
        "/api/v1/synthesis": "synthesis_run",
    }

    # Tier limits (In production, these should come from a dynamic configuration service)
    TIER_LIMITS = {
        "free": {
            "workflow_run": 50,
            "ai_token": 10000,
            "synthesis_run": 5,
            "user": 2,
            "agent": 3,
        },
        "pro": {
            "workflow_run": 1000,
            "ai_token": 500000,
            "synthesis_run": 100,
            "user": 10,
            "agent": 20,
        },
        "enterprise": {
            "workflow_run": 999999,
            "ai_token": 99999999,
            "synthesis_run": 999999,
            "user": 999,
            "agent": 999,
        },
    }

    def __init__(self, app: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # Only check POST requests for resource-consuming actions
        if request.method != "POST":
            await self.app(scope, receive, send)
            return

        path = request.url.path
        metric_type = None
        for prefix, mtype in self.QUOTA_ENDPOINTS.items():
            if path.startswith(prefix):
                metric_type = mtype
                break

        if not metric_type:
            await self.app(scope, receive, send)
            return

        tenant_id = get_tenant_id()
        if tenant_id is None:
            await self.app(scope, receive, send)
            return

        try:
            async with db_manager.get_session() as db:
                # 1. Get Tenant details
                tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
                if not tenant:
                    await self.app(scope, receive, send)
                    return

                tier = getattr(tenant, "subscription_tier", "free")

                # 2. Enforce Count-based Quotas
                if metric_type == "user":
                    await self._check_count_quota(
                        db,
                        User,
                        tenant_id,
                        tenant.max_users or self.TIER_LIMITS[tier]["user"],
                    )
                elif metric_type == "agent":
                    from src.core.agents.models import Agent

                    await self._check_count_quota(
                        db,
                        Agent,
                        tenant_id,
                        tenant.max_agents or self.TIER_LIMITS[tier]["agent"],
                    )

                # 3. Enforce Usage-based Quotas
                elif metric_type in ["workflow_run", "ai_token", "synthesis_run"]:
                    # Ensure path is an execution path
                    if any(x in path for x in ["/run", "/execute", "/generate"]):
                        usage_service = UsageService(db)
                        limit = self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"]).get(
                            metric_type, 0
                        )

                        has_quota = await usage_service.check_quota(tenant_id, metric_type, limit)
                        if not has_quota:
                            raise HTTPException(
                                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                                detail=f"Monthly limit ({limit}) reached for {metric_type} in {tier} tier. Please upgrade.",
                            )

        except HTTPException as e:
            await log_security_event(
                event_type=SecurityEvent.QUOTA_EXCEEDED,
                tenant_id=tenant_id,
                request_path=str(path),
                request_method=request.method,
                details={"metric": metric_type, "error": str(e.detail)},
                threat_level="low",
            )
            from fastapi.responses import JSONResponse

            response = JSONResponse(status_code=e.status_code, content={"detail": e.detail})
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    async def _check_count_quota(
        self,
        db: Any,  # TODO(TYPE): replace Any with concrete type
        model: Any,  # TODO(TYPE): replace Any with concrete type
        tenant_id: int,
        limit: int,
    ) -> None:
        result = await db.execute(select(func.count(model.id)).where(model.tenant_id == tenant_id))
        count = result.scalar() or 0
        if count >= limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Resource limit reached ({limit}). Please upgrade your plan.",
            )
