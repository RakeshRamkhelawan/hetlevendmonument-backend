# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Admin Experiment Endpoints - A/B Testing Management

Provides admin endpoints for managing experiments, viewing metrics,
and controlling experiment lifecycle (start, stop, pause).
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import UserResponse, require_admin
from src.core.api.v1.admin.dependencies import (
    Experiment,
    ExperimentService,
    ExperimentVariant,
    _resolve_tenant_id,
    get_db,
)

router = APIRouter(prefix="/admin/experiments", tags=["Admin - Experiments"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class VariantConfig(BaseModel):
    """Variant configuration for experiment creation."""

    name: str = Field(..., description="Variant name (control or treatment)")
    config: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        None, description="Variant-specific configuration"
    )  # TODO(TYPE): replace Any with concrete type


class CreateExperimentRequest(BaseModel):
    """Request schema for creating an experiment."""

    name: str = Field(..., min_length=1, max_length=255, description="Experiment name")
    description: str = Field("", description="Experiment description")
    variants: list[VariantConfig] = Field(..., min_length=2, description="Experiment variants")
    traffic_split: float = Field(
        0.5, ge=0.0, le=1.0, description="Traffic split for treatment (0.0-1.0)"
    )


class UpdateExperimentRequest(BaseModel):
    """Request schema for updating an experiment."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(None, pattern="^(draft|running|paused|completed)$")
    traffic_split: float | None = Field(None, ge=0.0, le=1.0)


class VariantResponse(BaseModel):
    """Response schema for experiment variant."""

    id: UUID
    name: str
    config: dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
    created_at: datetime


class ExperimentMetrics(BaseModel):
    """Metrics for a single variant."""

    exposures: int = 0
    conversions: int = 0
    conversion_rate: float = 0.0


class StatisticalSignificance(BaseModel):
    """Statistical significance test results."""

    chi2_stat: float
    p_value: float
    is_significant: bool
    degrees_of_freedom: int
    sample_size: int
    recommendation: str
    control_conversion_rate: float
    treatment_conversion_rate: float
    lift: float


class ExperimentResponse(BaseModel):
    """Response schema for experiment."""

    id: UUID
    name: str
    description: str | None
    status: str
    traffic_split: float
    start_date: datetime
    end_date: datetime | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    variants: list[VariantResponse]


class ExperimentDetailResponse(BaseModel):
    """Detailed experiment response with metrics."""

    id: UUID
    name: str
    description: str | None
    status: str
    traffic_split: float
    start_date: datetime
    end_date: datetime | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    variants: list[VariantResponse]
    metrics: dict[str, ExperimentMetrics]
    total_exposures: int
    total_conversions: int
    statistical_significance: StatisticalSignificance | None


class ExperimentListResponse(BaseModel):
    """Response schema for experiment list."""

    experiments: list[ExperimentResponse]
    total: int


# =============================================================================
# Helper Functions
# =============================================================================


async def get_experiment_service(db: AsyncSession) -> ExperimentService:
    """Factory function to create ExperimentService."""
    return ExperimentService(db)


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/", response_model=ExperimentListResponse)
async def list_experiments(
    status: str | None = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
) -> ExperimentListResponse:
    """List all experiments with optional status filter."""
    tenant_id = _resolve_tenant_id(current_user)  # TI-003: always scope to current tenant

    query = select(Experiment).where(Experiment.tenant_id == tenant_id)

    if status:
        query = query.where(Experiment.status == status)

    # Get total count
    count_query = select(Experiment).where(Experiment.tenant_id == tenant_id)
    if status:
        count_query = count_query.where(Experiment.status == status)

    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Experiment.created_at.desc())
    result = await db.execute(query)
    experiments = result.scalars().all()

    # Fetch variants for each experiment
    experiment_list = []
    for exp in experiments:
        variants_result = await db.execute(
            select(ExperimentVariant).where(ExperimentVariant.experiment_id == exp.id)
        )
        variants = variants_result.scalars().all()

        experiment_list.append(
            ExperimentResponse(
                id=exp.id,
                name=exp.name,
                description=exp.description,
                status=exp.status,
                traffic_split=exp.traffic_split,
                start_date=exp.start_date,
                end_date=exp.end_date,
                created_by=exp.created_by,
                created_at=exp.created_at,
                updated_at=exp.updated_at,
                variants=[
                    VariantResponse(
                        id=v.id,
                        name=v.name,
                        config=v.config,
                        created_at=v.created_at,
                    )
                    for v in variants
                ],
            )
        )

    return ExperimentListResponse(experiments=experiment_list, total=total)


@router.post("/", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    data: CreateExperimentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
) -> ExperimentResponse:
    """Create a new experiment."""
    tenant_id = _resolve_tenant_id(current_user)
    service = await get_experiment_service(db)

    # Convert variants to dict format expected by service
    variants_dicts = [{"name": v.name, "config": v.config} for v in data.variants]

    experiment = await service.create_experiment(
        tenant_id=tenant_id,
        name=data.name,
        description=data.description,
        variants=variants_dicts,
        traffic_split=data.traffic_split,
        created_by=UUID(int=current_user.id)
        if isinstance(current_user.id, int)
        else current_user.id,
    )

    # Fetch created experiment with variants
    variants_result = await db.execute(
        select(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment.id)
    )
    variants = variants_result.scalars().all()

    return ExperimentResponse(
        id=experiment.id,
        name=experiment.name,
        description=experiment.description,
        status=experiment.status,
        traffic_split=experiment.traffic_split,
        start_date=experiment.start_date,
        end_date=experiment.end_date,
        created_by=experiment.created_by,
        created_at=experiment.created_at,
        updated_at=experiment.updated_at,
        variants=[
            VariantResponse(
                id=v.id,
                name=v.name,
                config=v.config,
                created_at=v.created_at,
            )
            for v in variants
        ],
    )


@router.get("/{experiment_id}", response_model=ExperimentDetailResponse)
async def get_experiment(
    experiment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
) -> ExperimentDetailResponse:
    """Get experiment details with metrics and statistical significance."""
    tenant_id = _resolve_tenant_id(current_user)
    service = await get_experiment_service(db)

    # Get experiment -- TI-003: always scope to current tenant
    result = await db.execute(
        select(Experiment).where(Experiment.id == experiment_id, Experiment.tenant_id == tenant_id)
    )
    experiment = result.scalar_one_or_none()

    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found",
        )

    # Get variants
    variants_result = await db.execute(
        select(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment.id)
    )
    variants = variants_result.scalars().all()

    # Get metrics
    metrics_result = await service.calculate_metrics(experiment_id)
    metrics_data = metrics_result.get("metrics", {})

    metrics = {}
    for variant_name, data in metrics_data.items():
        metrics[variant_name] = ExperimentMetrics(
            exposures=data.get("exposures", 0),
            conversions=data.get("conversions", 0),
            conversion_rate=data.get("conversion_rate", 0.0),
        )

    # Get statistical significance
    significance_result = await service.check_statistical_significance(experiment_id)
    significance = None
    if "error" not in significance_result:
        significance = StatisticalSignificance(
            chi2_stat=significance_result.get("chi2_stat", 0.0),
            p_value=significance_result.get("p_value", 1.0),
            is_significant=significance_result.get("is_significant", False),
            degrees_of_freedom=significance_result.get("degrees_of_freedom", 1),
            sample_size=significance_result.get("sample_size", 0),
            recommendation=significance_result.get("recommendation", "continue"),
            control_conversion_rate=significance_result.get("control_conversion_rate", 0.0),
            treatment_conversion_rate=significance_result.get("treatment_conversion_rate", 0.0),
            lift=significance_result.get("lift", 0.0),
        )

    return ExperimentDetailResponse(
        id=experiment.id,
        name=experiment.name,
        description=experiment.description,
        status=experiment.status,
        traffic_split=experiment.traffic_split,
        start_date=experiment.start_date,
        end_date=experiment.end_date,
        created_by=experiment.created_by,
        created_at=experiment.created_at,
        updated_at=experiment.updated_at,
        variants=[
            VariantResponse(
                id=v.id,
                name=v.name,
                config=v.config,
                created_at=v.created_at,
            )
            for v in variants
        ],
        metrics=metrics,
        total_exposures=metrics_result.get("total_exposures", 0),
        total_conversions=metrics_result.get("total_conversions", 0),
        statistical_significance=significance,
    )


@router.patch("/{experiment_id}", response_model=ExperimentResponse)
async def update_experiment(
    experiment_id: UUID,
    data: UpdateExperimentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
) -> ExperimentResponse:
    """Update experiment status or configuration."""
    tenant_id = _resolve_tenant_id(current_user)
    service = await get_experiment_service(db)

    # Get experiment -- TI-003: always scope to current tenant
    result = await db.execute(
        select(Experiment).where(Experiment.id == experiment_id, Experiment.tenant_id == tenant_id)
    )
    experiment = result.scalar_one_or_none()

    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found",
        )

    # Handle status transitions
    if data.status:
        if data.status == "running" and experiment.status == "draft":
            await service.start_experiment(experiment_id)
        elif data.status == "completed":
            await service.stop_experiment(experiment_id, reason="manual_update")
        elif data.status == "paused":
            # Just update status for pause
            experiment.status = "paused"
            experiment.updated_at = datetime.now(timezone.utc)
        else:
            experiment.status = data.status
            experiment.updated_at = datetime.now(timezone.utc)

    # Update other fields
    if data.name is not None:
        experiment.name = data.name
    if data.description is not None:
        experiment.description = data.description
    if data.traffic_split is not None:
        experiment.traffic_split = data.traffic_split

    await db.commit()
    await db.refresh(experiment)

    # Get variants
    variants_result = await db.execute(
        select(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment.id)
    )
    variants = variants_result.scalars().all()

    return ExperimentResponse(
        id=experiment.id,
        name=experiment.name,
        description=experiment.description,
        status=experiment.status,
        traffic_split=experiment.traffic_split,
        start_date=experiment.start_date,
        end_date=experiment.end_date,
        created_by=experiment.created_by,
        created_at=experiment.created_at,
        updated_at=experiment.updated_at,
        variants=[
            VariantResponse(
                id=v.id,
                name=v.name,
                config=v.config,
                created_at=v.created_at,
            )
            for v in variants
        ],
    )


@router.post("/{experiment_id}/start", response_model=ExperimentResponse)
async def start_experiment(
    experiment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
) -> ExperimentResponse:
    """Start a draft or paused experiment."""
    service = await get_experiment_service(db)

    experiment = await service.start_experiment(experiment_id)

    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found",
        )

    # Get variants
    variants_result = await db.execute(
        select(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment.id)
    )
    variants = variants_result.scalars().all()

    return ExperimentResponse(
        id=experiment.id,
        name=experiment.name,
        description=experiment.description,
        status=experiment.status,
        traffic_split=experiment.traffic_split,
        start_date=experiment.start_date,
        end_date=experiment.end_date,
        created_by=experiment.created_by,
        created_at=experiment.created_at,
        updated_at=experiment.updated_at,
        variants=[
            VariantResponse(
                id=v.id,
                name=v.name,
                config=v.config,
                created_at=v.created_at,
            )
            for v in variants
        ],
    )


@router.post("/{experiment_id}/stop", response_model=ExperimentResponse)
async def stop_experiment(
    experiment_id: UUID,
    reason: str = Query("manual", description="Reason for stopping"),
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
) -> ExperimentResponse:
    """Stop a running experiment."""
    service = await get_experiment_service(db)

    experiment = await service.stop_experiment(experiment_id, reason=reason)

    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found",
        )

    # Get variants
    variants_result = await db.execute(
        select(ExperimentVariant).where(ExperimentVariant.experiment_id == experiment.id)
    )
    variants = variants_result.scalars().all()

    return ExperimentResponse(
        id=experiment.id,
        name=experiment.name,
        description=experiment.description,
        status=experiment.status,
        traffic_split=experiment.traffic_split,
        start_date=experiment.start_date,
        end_date=experiment.end_date,
        created_by=experiment.created_by,
        created_at=experiment.created_at,
        updated_at=experiment.updated_at,
        variants=[
            VariantResponse(
                id=v.id,
                name=v.name,
                config=v.config,
                created_at=v.created_at,
            )
            for v in variants
        ],
    )


@router.delete("/{experiment_id}", status_code=status.HTTP_200_OK)
async def delete_experiment(
    experiment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
) -> None:
    """Delete an experiment and all related data."""
    tenant_id = _resolve_tenant_id(current_user)

    # Get experiment -- TI-003: always scope to current tenant
    result = await db.execute(
        select(Experiment).where(Experiment.id == experiment_id, Experiment.tenant_id == tenant_id)
    )
    experiment = result.scalar_one_or_none()

    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found",
        )

    # Delete experiment (cascade will handle variants, assignments, events)
    await db.delete(experiment)
    await db.commit()


@router.post(
    "/ml-recommendations/init", response_model=dict[str, Any]
)  # TODO(TYPE): replace Any with concrete type
async def init_ml_recommendation_experiment(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Initialize ML recommendation A/B test experiment.

    Creates a new experiment comparing ML-enhanced recommendations
    against heuristic-only recommendations.

    Returns:
        Dict with experiment_id and status
    """
    tenant_id = _resolve_tenant_id(current_user)
    service = await get_experiment_service(db)

    experiment = await service.create_ml_recommendation_experiment(tenant_id=tenant_id)

    return {
        "experiment_id": str(experiment.id),
        "status": experiment.status,
        "name": experiment.name,
        "message": (
            "Experiment already exists"
            if experiment.status != "draft"
            else "Experiment created successfully"
        ),
    }


@router.get(
    "/metrics/ml", response_model=dict[str, Any]
)  # TODO(TYPE): replace Any with concrete type
async def get_ml_metrics(
    current_user: UserResponse = Depends(require_admin),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get ML model performance metrics.

    Returns:
        Dict with current ML model metrics (accuracy, precision, recall, etc.)
    """
    from src.ml.monitoring import MLMonitor

    return MLMonitor.get_metrics_summary()
