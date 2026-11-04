"""
Dependencies for Agentic API endpoints.

Provides FastAPI Depends() injectables for:
- Database sessions
- Feedback processing service
- Adaptation rule service (with Redis caching)
"""

import logging
from typing import cast

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.agent_registry import AgentRegistry
from src.core.agents.capabilities.agency_capabilities import AgencyCapabilityRegistry
from src.core.agents.capabilities.planner_agent_with_agency import create_planner_agent_with_agency
from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository
from src.core.als.agents.loader import AgentCatalogLoader, AgentConfig
from src.core.als.enterprise.packs import DomainPack, DomainPackOrchestrator, Voortgang
from src.core.als.enterprise.roi import ROICalculator
from src.core.als.supervisors.enums import SupervisorID, TaskStatus
from src.core.als.supervisors.finance_supervisor import FinanceSupervisor
from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.agentic.orchestration_service import AgenticOrchestrationService
from src.core.auth.dependencies import require_resource_permission
from src.core.database.database import get_db
from src.core.database.redis import get_redis_client
from src.core.governance.audit import audit_service
from src.core.governance.governance_helper import (  # noqa: F401
    AuditServiceAdapter,
    PolicyEngineAdapter,
)
from src.core.governance.oversight_gate import OversightGate  # noqa: F401
from src.core.governance.rate_limiter import agent_execute_limit  # noqa: F401
from src.core.learning.cache import create_cached_adaptation_service
from src.core.learning.health import check_learning_health
from src.core.learning.service import (
    AdaptationRuleService,
    FeedbackProcessingService,
    LearningAnalyticsService,
)
from src.core.middleware.tenant_context import require_tenant_id
from src.core.repositories.tenant_pack_activations_repository import (
    TenantPackActivationsRepository,
)

logger = logging.getLogger(__name__)


async def get_pack_activations_repository(
    db: AsyncSession = Depends(get_db),
) -> TenantPackActivationsRepository:
    """De pakketstand per klant (pakket aanzetten, dag 1); dezelfde sessie als de route."""
    return TenantPackActivationsRepository(db)


async def get_feedback_service(db: AsyncSession = Depends(get_db)) -> FeedbackProcessingService:
    """Dependency for feedback processing service."""
    return FeedbackProcessingService(db)


async def get_adaptation_service(db: AsyncSession = Depends(get_db)) -> AdaptationRuleService:
    """Dependency for adaptation rule service with Redis caching."""
    redis = None
    try:
        redis = await get_redis_client()
    except Exception:
        logger.warning("Redis unavailable for adaptation service; caching disabled")
    return cast(AdaptationRuleService, create_cached_adaptation_service(db, redis_client=redis))


async def get_analytics_service(db: AsyncSession = Depends(get_db)) -> LearningAnalyticsService:
    """Dependency for analytics service."""
    return LearningAnalyticsService(db)


async def get_agentic_orchestration_service(
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
) -> AgenticOrchestrationService:
    """Dependency for agentic orchestration service (ADR-033)."""
    return AgenticOrchestrationService(db=db, tenant_id=tenant_id)


__all__ = [
    "AdaptationRuleService",
    "AgencyCapabilityRegistry",
    "AgenticOrchestrationService",
    "AgentCatalogLoader",
    "AgentConfig",
    "AgentRegistry",
    "AgentRegistryRepository",
    "AuditServiceAdapter",
    "audit_service",
    "create_planner_agent_with_agency",
    "DomainPack",
    "DomainPackOrchestrator",
    "FeedbackProcessingService",
    "FinanceSupervisor",
    "LearningAnalyticsService",
    "TenantPackActivationsRepository",
    "OversightGate",
    "agent_execute_limit",
    "PolicyEngineAdapter",
    "ROICalculator",
    "SupervisorID",
    "TaskStatus",
    "Voortgang",
    "check_learning_health",
    "require_resource_permission",
    "validate_csrf_token",
    "get_agentic_orchestration_service",
    "get_db",
    "get_feedback_service",
    "get_pack_activations_repository",
    "get_adaptation_service",
    "get_analytics_service",
]
