# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""AI Features -- System status and capabilities sub-router (ADR-033 Laag 1)."""

from datetime import datetime, timezone

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from src.core.api.dependencies import require_admin_user

from src.core.ai.adaptive_learning_engine import AdaptiveLearningEngine
from src.core.ai.intelligent_routing import IntelligentRouter
from src.core.ai.predictive_analytics import PredictiveAnalyticsEngine
from src.core.auth.api_deps import UserResponse, get_current_user, require_scopes, OAuth2Scope
from src.core.container import Container
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)

router = APIRouter()


@router.get("/system/status", response_model=dict[str, object])
@inject
async def get_ai_system_status(
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    adaptive_learning_engine: AdaptiveLearningEngine = Depends(
        Provide[Container.adaptive_learning_engine]
    ),
    intelligent_router: IntelligentRouter = Depends(Provide[Container.intelligent_router]),
    predictive_analytics: PredictiveAnalyticsEngine = Depends(
        Provide[Container.predictive_analytics]
    ),
) -> dict[str, object]:
    """
    Get comprehensive AI system status.
    Requires: READ permission (USER level).
    """
    try:
        logger.info("User %s requesting AI system status", current_user.id)

        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {
                "adaptive_learning": {
                    "status": "operational",
                    "events_processed": await adaptive_learning_engine.get_event_count(),
                    "insights_available": len(await adaptive_learning_engine.get_insights()),
                },
                "intelligent_routing": {
                    "status": "operational",
                    "routes_available": await intelligent_router.get_available_routes(),
                    "average_decision_time_ms": await intelligent_router.get_average_decision_time(),
                },
                "predictive_analytics": {
                    "status": "operational",
                    "models_active": await predictive_analytics.get_active_models_count(),
                    "average_prediction_confidence": await predictive_analytics.get_average_confidence(),
                },
            },
        }

    except Exception as e:
        logger.exception("Error getting AI system status: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get system status",
        ) from e


@router.get("/capabilities", response_model=dict[str, object])
async def get_ai_capabilities(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, object]:
    """
    Get list of available AI capabilities and features.
    Requires: READ permission (USER level).
    """
    try:
        logger.info("User %s requesting AI capabilities", current_user.id)

        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "capabilities": {
                "adaptive_learning": {
                    "available": True,
                    "description": "Continuous learning from user interactions and outcomes",
                    "features": [
                        "Event processing",
                        "Pattern recognition",
                        "Insight generation",
                        "Model adaptation",
                    ],
                },
                "intelligent_routing": {
                    "available": True,
                    "description": "Smart routing based on context and performance prediction",
                    "features": [
                        "Dynamic route selection",
                        "Performance prediction",
                        "Load balancing",
                        "User preference learning",
                    ],
                },
                "predictive_analytics": {
                    "available": True,
                    "description": "Forecasting and trend analysis",
                    "features": [
                        "Time series prediction",
                        "Classification",
                        "Anomaly detection",
                        "Feature importance analysis",
                    ],
                },
            },
            "version": "1.0.0",
        }

    except Exception as e:
        logger.exception("Error getting AI capabilities: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get capabilities",
        ) from e
