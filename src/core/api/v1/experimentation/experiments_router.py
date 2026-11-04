# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
REST API endpoints for A/B Testing Framework - FASE 4 Production RBAC Protection.
Migrated from src/core/api/experimentation_endpoints.py (SP-API-007 Dag 1).
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import UserResponse, get_current_user, require_scopes, OAuth2Scope
from src.core.api.v1.experimentation.dependencies import get_db
from src.core.experimentation.ab_testing import (
    AssignmentStrategy,
    ExperimentManager,
    ExperimentStatus,
    ExperimentVariant,
)
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)
router = APIRouter(tags=["experimentation"])

# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class VariantRequest(BaseModel):
    """Request model for experiment variant"""

    name: str = Field(..., min_length=1, max_length=255, description="Variant name")
    description: str = Field(..., min_length=1, max_length=1000, description="Variant description")
    config: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        ..., description="Variant configuration"
    )  # TODO(TYPE): replace Any with concrete type
    traffic_weight: float = Field(0.5, ge=0.0, le=1.0, description="Traffic weight")


class CreateExperimentRequest(BaseModel):
    """Request model for creating experiment"""

    name: str = Field(..., min_length=1, max_length=255, description="Experiment name")
    description: str = Field(..., min_length=1, max_length=1000, description="Description")
    variants: list[VariantRequest] = Field(..., min_length=2, description="Variants list")
    assignment_strategy: AssignmentStrategy = Field(
        AssignmentStrategy.RANDOM, description="Assignment strategy"
    )
    metadata: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        None, description="Additional metadata"
    )  # TODO(TYPE): replace Any with concrete type


class ExperimentResponse(BaseModel):
    """Response model for experiment"""

    id: str
    name: str
    description: str
    status: str
    assignment_strategy: str
    variants: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    created_at: datetime
    start_date: datetime | None
    end_date: datetime | None


class AssignVariantRequest(BaseModel):
    """Request model for variant assignment"""

    experience_id: int = Field(..., description="Experience ID")
    stratification_key: str | None = Field(None, description="Stratification key")


class AssignVariantResponse(BaseModel):
    """Response model for variant assignment"""

    experiment_id: str
    experience_id: int
    variant: str
    assigned_at: datetime


class MetricsResponse(BaseModel):
    """Response model for metrics"""

    variant_name: str
    total_experiences: int
    success_count: int
    success_rate: float
    avg_duration: float
    avg_confidence: float


class SignificanceRequest(BaseModel):
    """Request model for significance testing"""

    primary_metric: str = Field("success_rate", description="Metric to test")
    confidence_level: float = Field(0.95, ge=0.0, le=1.0, description="Confidence level")


class SignificanceResponse(BaseModel):
    """Response model for statistical results"""

    test_name: str
    statistic: float
    p_value: float
    is_significant: bool
    confidence_level: float
    effect_size: float | None


# ============================================================================
# EXPERIMENTATION ENDPOINTS - FASE 4 (9 endpoints with RBAC)
# ============================================================================


@router.post(
    "/create", status_code=status.HTTP_201_CREATED, response_model=dict[str, Any]
)  # TODO(TYPE): replace Any with concrete type
async def create_experiment(
    request: CreateExperimentRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Create a new A/B test experiment.
    Requires: OAuth2Scope.ADMIN_ALL
    """
    try:
        if len(request.variants) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Experiment requires at least 2 variants",
            )

        logger.info("User %s creating experiment: %s", current_user.id, request.name)

        manager = ExperimentManager(db)

        variants = [
            ExperimentVariant(
                name=v.name,
                description=v.description,
                config=v.config,
                traffic_weight=v.traffic_weight,
            )
            for v in request.variants
        ]

        experiment_id = await manager.create_experiment(
            name=request.name,
            description=request.description,
            variants=variants,
            assignment_strategy=request.assignment_strategy,
            metadata=request.metadata,
        )

        logger.info("Experiment created by user %s: %s", current_user.id, experiment_id)

        return {
            "experiment_id": str(experiment_id),
            "name": request.name,
            "status": ExperimentStatus.DRAFT.value,
            "message": "Experiment created successfully",
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error creating experiment: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.")
    except Exception as e:
        logger.exception("Error creating experiment: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create experiment",
        )


@router.get("/active", response_model=list[ExperimentResponse])
async def list_active_experiments(
    limit: int = Query(default=50, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ExperimentResponse]:
    """
    List all active experiments (paginated).
    Requires: OAuth2Scope.AGENTS_READ
    # TODO(SP-VOLGENDE): voeg tenant_id filtering toe zodra ExperimentManager DB-backed is
    """
    try:
        logger.info(
            "User %s listing active experiments (limit=%s, offset=%s)",
            current_user.id,
            limit,
            offset,
        )

        manager = ExperimentManager(db)
        experiments = await manager.list_experiments(status=ExperimentStatus.ACTIVE)

        paginated = experiments[offset : offset + limit]
        return [
            ExperimentResponse(
                id=str(exp["id"]),
                name=exp["name"],
                description=exp["description"],
                status=exp["status"],
                assignment_strategy=exp["assignment_strategy"],
                variants=exp["variants"],
                metadata=exp.get("metadata", {}),
                created_at=exp["created_at"],
                start_date=exp.get("start_date"),
                end_date=exp.get("end_date"),
            )
            for exp in paginated
        ]

    except Exception as e:
        logger.exception("Error listing active experiments: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list experiments",
        )


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
) -> ExperimentResponse:
    """
    Get experiment details.
    Requires: OAuth2Scope.AGENTS_READ
    # TODO(SP-VOLGENDE): B1 -- ExperimentManager direct in route-handler (ADR-033 thin delivery violation)
    # TODO(SP-VOLGENDE): R-001/B2 -- cross-tenant data-lek: ExperimentManager is shared in-memory cache zonder tenant-isolatie;
    # vereist DB-backed implementatie met tenant_id filtering op alle queries
    """
    try:
        logger.info("User %s retrieving experiment: %s", current_user.id, experiment_id)

        manager = ExperimentManager(db)
        experiment = await manager.get_experiment(experiment_id)

        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment {experiment_id} not found",
            )

        return ExperimentResponse(
            id=str(experiment["id"]),
            name=experiment["name"],
            description=experiment["description"],
            status=experiment["status"],
            assignment_strategy=experiment["assignment_strategy"],
            variants=experiment["variants"],
            metadata=experiment.get("metadata", {}),
            created_at=experiment["created_at"],
            start_date=experiment.get("start_date"),
            end_date=experiment.get("end_date"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error retrieving experiment: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve experiment",
        )


@router.post(
    "/{experiment_id}/start", response_model=dict[str, Any]
)  # TODO(TYPE): replace Any with concrete type
async def start_experiment(
    experiment_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Start an experiment (activate traffic allocation).
    Requires: OAuth2Scope.ADMIN_ALL
    """
    try:
        logger.info("User %s starting experiment: %s", current_user.id, experiment_id)

        manager = ExperimentManager(db)
        await manager.start_experiment(experiment_id)

        return {
            "experiment_id": str(experiment_id),
            "status": ExperimentStatus.ACTIVE.value,
            "message": "Experiment started successfully",
        }

    except ValueError as e:
        logger.warning("Cannot start experiment: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.")
    except Exception as e:
        logger.exception("Error starting experiment: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start experiment",
        )


@router.post(
    "/{experiment_id}/pause", response_model=dict[str, Any]
)  # TODO(TYPE): replace Any with concrete type
async def pause_experiment(
    experiment_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Pause an active experiment.
    Requires: OAuth2Scope.ADMIN_ALL
    """
    try:
        logger.info("User %s pausing experiment: %s", current_user.id, experiment_id)

        manager = ExperimentManager(db)
        await manager.pause_experiment(experiment_id)

        return {
            "experiment_id": str(experiment_id),
            "status": ExperimentStatus.PAUSED.value,
            "message": "Experiment paused successfully",
        }

    except ValueError as e:
        logger.warning("Cannot pause experiment: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.")
    except Exception as e:
        logger.exception("Error pausing experiment: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to pause experiment",
        )


@router.post(
    "/{experiment_id}/stop", response_model=dict[str, Any]
)  # TODO(TYPE): replace Any with concrete type
async def stop_experiment(
    experiment_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Stop and complete an experiment.
    Requires: OAuth2Scope.ADMIN_ALL
    """
    try:
        logger.info("User %s stopping experiment: %s", current_user.id, experiment_id)

        manager = ExperimentManager(db)
        await manager.stop_experiment(experiment_id)

        return {
            "experiment_id": str(experiment_id),
            "status": ExperimentStatus.COMPLETED.value,
            "message": "Experiment stopped successfully",
        }

    except ValueError as e:
        logger.warning("Cannot stop experiment: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.")
    except Exception as e:
        logger.exception("Error stopping experiment: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop experiment",
        )


@router.post("/{experiment_id}/assign", response_model=AssignVariantResponse)
async def assign_variant(
    experiment_id: UUID,
    request: AssignVariantRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> AssignVariantResponse:
    """
    Assign an experience to an experiment variant.
    Requires: OAuth2Scope.AGENTS_WRITE
    """
    try:
        if request.experience_id < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid experience ID"
            )

        logger.info(
            "User %s assigning variant for experience %s",
            current_user.id,
            request.experience_id,
        )

        manager = ExperimentManager(db)
        variant_name = await manager.assign_variant(
            experiment_id=experiment_id,
            experience_id=request.experience_id,
            stratification_key=request.stratification_key,
        )

        return AssignVariantResponse(
            experiment_id=str(experiment_id),
            experience_id=request.experience_id,
            variant=variant_name,
            assigned_at=datetime.now(timezone.utc),
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Cannot assign variant: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.")
    except Exception as e:
        logger.exception("Error assigning variant: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign variant",
        )


@router.get("/{experiment_id}/metrics", response_model=dict[str, MetricsResponse])
async def get_metrics(
    experiment_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    since: datetime | None = Query(None, description="Filter metrics since this datetime"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, MetricsResponse]:
    """
    Get aggregated metrics per variant.
    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info("User %s retrieving metrics for experiment %s", current_user.id, experiment_id)

        manager = ExperimentManager(db)
        metrics = await manager.get_variant_metrics(experiment_id, since=since)

        return {
            variant_name: MetricsResponse(
                variant_name=m.variant_name,
                total_experiences=m.total_experiences,
                success_count=m.success_count,
                success_rate=m.success_rate,
                avg_duration=m.avg_duration,
                avg_confidence=m.avg_confidence,
            )
            for variant_name, m in metrics.items()
        }

    except ValueError as e:
        logger.warning("Invalid metrics request: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.")
    except Exception as e:
        logger.exception("Error calculating metrics: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate metrics",
        )


# TODO(SP-VOLGENDE): R-003 -- POST semantiek op read-only endpoint; wijzigen naar GET met query params
@router.post("/{experiment_id}/results", response_model=list[SignificanceResponse])
async def get_results(
    experiment_id: UUID,
    request: SignificanceRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[SignificanceResponse]:
    """
    Calculate statistical significance for variants.
    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(
            "User %s calculating significance for experiment %s",
            current_user.id,
            experiment_id,
        )

        manager = ExperimentManager(db)
        results = await manager.calculate_significance(
            experiment_id=experiment_id,
            primary_metric=request.primary_metric,
            confidence_level=request.confidence_level,
        )

        return [
            SignificanceResponse(
                test_name=r.test_name,
                statistic=r.statistic,
                p_value=r.p_value,
                is_significant=r.is_significant,
                confidence_level=r.confidence_level,
                effect_size=r.effect_size,
            )
            for r in results
        ]

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Invalid significance request: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.")
    except Exception as e:
        logger.exception("Error calculating significance: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate significance",
        )


# list_active_experiments verplaatst naar boven /{experiment_id} (B3 fix -- route volgorde)
