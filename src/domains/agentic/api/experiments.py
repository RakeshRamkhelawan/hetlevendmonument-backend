from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db
from src.domains.agentic.api.dependencies import (
    get_experiment_repository,
    get_experimentation_service,
    get_promotion_service,
)
from src.domains.agentic.models import PromptExperiment
from src.domains.agentic.repositories.prompt_repository import SQLAlchemyPromptRepository
from src.domains.agentic.schemas.experiment_schema import (
    CreateExperimentRequest,
    ExperimentResponse,
    PromoteRequest,
)
from src.domains.agentic.services.experimentation_service import ExperimentationService
from src.domains.agentic.services.promotion_service import AutoPromotionService
from src.core.exceptions import ValidatieFout

# Absolute prefix to match application standards
router = APIRouter(prefix="/api/v1/agentic/experiments", tags=["Prompt Experiments"])


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=ExperimentResponse)
async def create_experiment(
    request: CreateExperimentRequest,
    service: ExperimentationService = Depends(get_experimentation_service),
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> ExperimentResponse:
    """Create a new prompt experiment."""
    variants_dicts = [v.model_dump() for v in request.variants]

    # ValueError uit onze EIGEN validatie is ongeldige invoer, geen storing (ADR-036 OP-135).
    # `production_integration._validate_test_config` gooit hem onder meer op een te kleine
    # steekproef, een onbekende variant en een verkeerde verkeersverdeling. Zonder deze tak kwam
    # dat naar buiten als een onafgehandelde 500 met een volledige stacktrace in de log, terwijl
    # `.claude/rules/error-handling.md` voor ongeldige invoer een 400 voorschrijft. De aanroeper
    # kreeg "Internal server error" en hoorde dus niet wat hij fout deed.
    #
    # De boodschap komt uit onze eigen validatie en bevat geen databasefout of intern pad, dus hij
    # mag terug naar de aanroeper -- dat is juist het punt van een 400.
    try:
        experiment_id = await service.create_experiment(
            db=db,
            tenant_id=current_user.tenant_id,
            name=request.name,
            description=request.description,
            prompt_template_id=request.prompt_template_id,
            variants=variants_dicts,
            min_sample_size=request.min_sample_size,
        )
    except ValidatieFout as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.") from e

    # Fetch created experiment to return full response
    repo = SQLAlchemyPromptRepository(db)
    exp = await repo.get_experiment(experiment_id, tenant_id=current_user.tenant_id)
    if not exp:
        raise HTTPException(status_code=500, detail="Experiment created but not found")

    return exp


@router.get("/", response_model=list[ExperimentResponse])
async def list_experiments(
    repo: SQLAlchemyPromptRepository = Depends(get_experiment_repository),
    current_user: UserResponse = Depends(get_current_user),
) -> list[ExperimentResponse]:
    """List all experiments, serialized via response_model=list[ExperimentResponse]."""
    results: Sequence[PromptExperiment] = await repo.list_experiments(
        tenant_id=current_user.tenant_id
    )
    return [ExperimentResponse.model_validate(e) for e in results]


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_id: str,
    repo: SQLAlchemyPromptRepository = Depends(get_experiment_repository),
    current_user: UserResponse = Depends(get_current_user),
) -> ExperimentResponse:
    """Get experiment details."""
    exp = await repo.get_experiment(experiment_id, tenant_id=current_user.tenant_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp


@router.post("/{experiment_id}/promote", status_code=200)
async def promote_experiment(
    experiment_id: str,
    request: PromoteRequest,
    service: AutoPromotionService = Depends(get_promotion_service),
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, str]:
    """Trigger promotion check manually."""
    success = await service.check_and_promote(
        experiment_id,
        request.template_id,
        tenant_id=current_user.tenant_id,
    )

    # Even if false (no winner yet), the check was successful
    # But usually user expects something happened.
    # Logic: True = Promoted, False = No significant winner or error log.

    if not success:
        return {"message": "No winner promoted (insufficient data or not significant)"}

    return {"message": "Winner promoted successfully"}
