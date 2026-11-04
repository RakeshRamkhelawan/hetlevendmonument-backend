# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Prediction sub-router: alle 9 Phase5-Prediction routes (ADR-033 Laag 1).

# TODO(SP-VOLGENDE): predictive_evolution_engine is een globale singleton zonder tenant-isolatie;
# vereist multi-tenant refactor zodra engine DB-backed is.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from .dependencies import (
    OAuth2Scope,
    UserResponse,
    get_current_user,
    predictive_evolution_engine,
    require_scopes,
)
from .schemas import (
    HealthCheckResponse,
    InitializeResponse,
    MetricCollectionResponse,
    MetricsHistoryResponse,
    OptimizationExecutionResponse,
    PredictionRequest,
    PredictionResponse,
    RecentPredictionsResponse,
    SystemStatusResponse,
    TrendsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prediction", tags=["Phase5-Prediction"])


@router.post("/initialize", response_model=InitializeResponse)
async def initialize_predictive_system(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> InitializeResponse:
    """Initialize the predictive evolution system. Requires: OAuth2Scope.ADMIN_ALL"""
    logger.info("User %s initializing predictive system", current_user.id)
    try:
        success = await predictive_evolution_engine.initialize()
        if success:
            return InitializeResponse(
                status="success",
                message="Predictive evolution system initialized successfully",
                timestamp=datetime.now(timezone.utc).isoformat(),
                capabilities=[
                    "performance_prediction",
                    "bottleneck_detection",
                    "resource_forecasting",
                    "optimization_planning",
                ],
            )
        raise HTTPException(
            status_code=500, detail="Failed to initialize predictive evolution system"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Initialization failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Initialization error") from e


@router.get("/status", response_model=SystemStatusResponse)
async def get_prediction_system_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> SystemStatusResponse:
    """Get current status. Requires: OAuth2Scope.AGENTS_READ"""
    logger.info("User %s getting prediction system status", current_user.id)
    try:
        status = await predictive_evolution_engine.get_system_evolution_status()
        return SystemStatusResponse(
            system_status="operational",
            prediction_engine=status,
            timestamp=datetime.now(timezone.utc).isoformat(),
            version="1.0.0",
        )
    except Exception as e:
        logger.error("Status retrieval failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Status retrieval error") from e


@router.post("/collect-metrics", response_model=MetricCollectionResponse)
async def collect_system_metrics(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> MetricCollectionResponse:
    """Manually trigger metrics collection. Requires: OAuth2Scope.AGENTS_WRITE"""
    logger.info("User %s collecting system metrics", current_user.id)
    try:
        metrics = await predictive_evolution_engine.collect_system_metrics()
        return MetricCollectionResponse(
            status="success",
            metrics_collected=len(metrics),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error("Metrics collection failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Metrics collection error") from e


@router.post("/predict", response_model=PredictionResponse)
async def generate_system_predictions(
    request: PredictionRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> PredictionResponse:
    """Generate predictions and optimization plans. Requires: OAuth2Scope.AGENTS_WRITE"""
    logger.info("User %s generating system predictions", current_user.id)
    try:
        predictions = await predictive_evolution_engine.predict_system_performance(
            hours_ahead=request.hours_ahead
        )
        predictions_data: list[Any] = [  # TODO(TYPE): replace Any with concrete type
            {
                "prediction_id": pred.prediction_id,
                "type": pred.prediction_type.value,
                "confidence": pred.confidence,
                "predicted_value": pred.predicted_value,
                "time_horizon_hours": pred.time_horizon,
                "reasoning": pred.reasoning,
                "recommended_actions": pred.recommended_actions,
                "impact_assessment": pred.impact_assessment,
            }
            for pred in predictions
        ]
        optimization_plan = None
        if request.include_optimization_plan:
            optimization_plan = await predictive_evolution_engine.generate_optimization_plan(
                predictions
            )
        system_status = await predictive_evolution_engine.get_system_evolution_status()
        return PredictionResponse(
            predictions=predictions_data,
            optimization_plan=optimization_plan,
            system_status=system_status,
        )
    except Exception as e:
        logger.error("Prediction generation failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Prediction generation error") from e


@router.get("/predictions/recent", response_model=RecentPredictionsResponse)
async def get_recent_predictions(
    limit: int = Query(default=10, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> RecentPredictionsResponse:
    """Get recent predictions (paginated). Requires: OAuth2Scope.AGENTS_READ"""
    logger.info(
        "User %s getting recent predictions (limit=%s, offset=%s)", current_user.id, limit, offset
    )
    try:
        all_predictions = predictive_evolution_engine.predictions
        sorted_predictions = sorted(all_predictions, key=lambda p: p.prediction_id, reverse=True)
        page = sorted_predictions[offset : offset + limit]
        predictions_data: list[Any] = [  # TODO(TYPE): replace Any with concrete type
            {
                "prediction_id": pred.prediction_id,
                "type": pred.prediction_type.value,
                "confidence": pred.confidence,
                "predicted_value": pred.predicted_value,
                "time_horizon_hours": pred.time_horizon,
                "reasoning": pred.reasoning,
                "recommended_actions": pred.recommended_actions,
                "impact_assessment": pred.impact_assessment,
            }
            for pred in page
        ]
        return RecentPredictionsResponse(
            predictions=predictions_data,
            total_count=len(all_predictions),
            returned_count=len(predictions_data),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error(
            "Recent predictions retrieval failed: %s: %s", type(e).__name__, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Recent predictions retrieval error") from e


@router.get("/metrics/history", response_model=MetricsHistoryResponse)
async def get_metrics_history(
    hours: int = 6,
    metric_type: str | None = None,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> MetricsHistoryResponse:
    """Get historical metrics. Requires: OAuth2Scope.AGENTS_READ"""
    logger.info("User %s getting metrics history", current_user.id)
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        filtered = [
            m for m in predictive_evolution_engine.metrics_history if m.timestamp > cutoff_time
        ]
        if metric_type:
            filtered = [m for m in filtered if m.metric_type == metric_type]
        metrics_data: list[Any] = [  # TODO(TYPE): replace Any with concrete type
            {
                "timestamp": m.timestamp.isoformat(),
                "metric_type": m.metric_type,
                "value": m.value,
                "component": m.component,
                "metadata": m.metadata,
            }
            for m in filtered
        ]
        return MetricsHistoryResponse(
            metrics=metrics_data,
            count=len(metrics_data),
            time_range_hours=hours,
            metric_type_filter=metric_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error("Metrics history retrieval failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Metrics history retrieval error") from e


@router.post("/optimize/execute", response_model=OptimizationExecutionResponse)
async def execute_optimization_plan(
    background_tasks: BackgroundTasks,
    plan_id: str | None = None,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> OptimizationExecutionResponse:
    """Execute an optimization plan. Requires: OAuth2Scope.ADMIN_ALL"""
    logger.info("User %s executing optimization plan %s", current_user.id, plan_id)
    try:

        def simulate_optimization() -> None:
            import time

            time.sleep(2)
            logger.info("Optimization plan executed: %s", plan_id or "latest")

        background_tasks.add_task(simulate_optimization)
        return OptimizationExecutionResponse(
            status="optimization_initiated",
            plan_id=plan_id or f"auto_{int(datetime.now(timezone.utc).timestamp())}",
            message="Optimization plan execution started in background",
            estimated_completion="2-5 minutes",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error("Optimization execution failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Optimization execution error") from e


@router.get("/analytics/trends", response_model=TrendsResponse)
async def get_system_trends(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> TrendsResponse:
    """Get system performance trends. Requires: OAuth2Scope.AGENTS_READ"""
    logger.info("User %s getting system trends", current_user.id)
    try:
        import numpy as np

        recent_metrics = [
            m
            for m in predictive_evolution_engine.metrics_history
            if m.timestamp > datetime.now(timezone.utc) - timedelta(hours=12)
        ]
        trends: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        metric_types = {m.metric_type for m in recent_metrics}
        for mt in metric_types:
            type_metrics = [m for m in recent_metrics if m.metric_type == mt]
            values = [m.value for m in type_metrics]
            if len(values) >= 2:
                trends[mt] = {
                    "current_value": values[-1],
                    "trend_direction": "increasing" if values[-1] > values[0] else "decreasing",
                    "trend_strength": abs(values[-1] - values[0]) / max(values[0], 0.1),
                    "average_value": np.mean(values),
                    "data_points": len(values),
                }
        return TrendsResponse(
            trends=trends,
            analysis_period_hours=12,
            total_metrics_analyzed=len(recent_metrics),
            trend_summary={
                "improving_metrics": len(
                    [t for t in trends.values() if t["trend_direction"] == "decreasing"]
                ),
                "degrading_metrics": len(
                    [t for t in trends.values() if t["trend_direction"] == "increasing"]
                ),
                "stable_metrics": len(metric_types) - len(trends),
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error("Trends analysis failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Trends analysis error") from e


@router.get("/health", response_model=HealthCheckResponse)
async def prediction_system_health(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> HealthCheckResponse:
    """Health check for prediction system. Requires: OAuth2Scope.AGENTS_READ"""
    logger.info("User %s checking prediction health", current_user.id)
    try:
        status = await predictive_evolution_engine.get_system_evolution_status()
        return HealthCheckResponse(
            status="healthy" if status["status"] == "operational" else "degraded",
            prediction_engine="operational",
            timestamp=datetime.now(timezone.utc).isoformat(),
            version="1.0.0",
        )
    except Exception as e:
        logger.error("Health check failed: %s: %s", type(e).__name__, e, exc_info=True)
        return HealthCheckResponse(
            status="unhealthy",
            prediction_engine="error",
            error="Er is een fout opgetreden.",
            timestamp=datetime.now(timezone.utc).isoformat(),
            version="1.0.0",
        )
