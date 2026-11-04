"""
Digital Twin API endpoints.

Endpoints:
- POST /learning/track-user-behavior   Track een user gedrags-observatie
- POST /learning/analyze-struggle      Analyseer struggle + suggestie
- GET  /learning/twin/consent          Haal consent status op
- PUT  /learning/twin/consent          Update consent status
- DELETE /learning/twin/data           GDPR: Verwijder alle twin data (Right to Erasure)
- GET  /learning/twin/export           GDPR: Exporteer alle twin data (Data Portability)
"""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.learning.consent.consent_manager import TwinConsentManager
    from src.core.learning.services.practical_twin_service import PracticalTwinService

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db
from src.core.database.redis import get_redis_client
from src.core.middleware.rate_limiter import get_limiter
from src.core.models.rbac_models import User

# Rate limiter for Digital Twin endpoints
# Reads get at least 6x the write limit (per AGENTS.md)
twin_limiter = get_limiter(service_name="twin")

router = APIRouter(prefix="/learning", tags=["Digital Twin"])

# --- Pydantic Schemas ----------------------------------------------------------


class TrackBehaviorRequest(BaseModel):
    """Request voor het tracken van een user gedrags-observatie."""

    session_id: str = Field(..., description="Unieke sessie-identifier")
    behavior_type: str = Field(
        ...,
        description="Type gedrag: file_edit, rapid_switch, undo_loop, etc.",
        max_length=100,
    )
    context: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        None,
        description="Geanonimiseerde context (wordt gefilterd door PrivacyFilter)",
    )
    outcome_metrics: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        None, description="Uitkomst-metrics van de observatie"
    )
    confidence_score: float = Field(
        1.0, ge=0.0, le=1.0, description="Betrouwbaarheidsscore van de observatie"
    )


class TrackBehaviorResponse(BaseModel):
    """Response na het tracken van een observatie."""

    trace_id: str | None = Field(
        None, description="Trace ID van de observatie (None als verworpen)"
    )
    accepted: bool = Field(description="True als de observatie is geaccepteerd")
    reason: str | None = Field(None, description="Reden voor verwerping (indien van toepassing)")


class AnalyzeStruggleRequest(BaseModel):
    """Request voor struggle analyse."""

    context: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        ...,
        description="Gedragscontext voor WeightedStruggleScore berekening",
    )
    user_profile: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Cognitief profiel van de user"
    )


class AnalyzeStruggleResponse(BaseModel):
    """Response van struggle analyse."""

    score: float = Field(description="WeightedStruggleScore (0.0 - 1.0)")
    needs_intervention: bool = Field(description="True als score > 0.8")
    suggestion: str = Field(description="LLM-suggestie (leeg als geen interventie nodig)")
    reason: str | None = Field(
        None, description="Reden voor geen interventie (bijv. user_opted_out_art22)"
    )


class ConsentCategoriesResponse(BaseModel):
    """Response voor granular consent categories."""

    behavior_tracking: bool = Field(description="Allow behavior observations")
    profile_aggregation: bool = Field(description="Allow cognitive profile building")
    ai_interventions: bool = Field(description="Allow AI-generated suggestions")
    cross_session_memory: bool = Field(description="Allow profile to persist across sessions")


class ConsentStatusResponse(BaseModel):
    """Response voor consent status."""

    status: str = Field(description="enabled, disabled, of paused")
    categories: ConsentCategoriesResponse | None = Field(
        None, description="Granular consent categories"
    )


class ConsentUpdateRequest(BaseModel):
    """Request voor legacy consent update."""

    status: str = Field(..., description="Nieuwe consent status: enabled, disabled, of paused")


class ConsentCategoriesUpdateRequest(BaseModel):
    """Request voor granular consent update."""

    behavior_tracking: bool | None = Field(None, description="Allow behavior observations")
    profile_aggregation: bool | None = Field(None, description="Allow cognitive profile building")
    ai_interventions: bool | None = Field(None, description="Allow AI-generated suggestions")
    cross_session_memory: bool | None = Field(
        None, description="Allow profile to persist across sessions"
    )


class TwinProfileResponse(BaseModel):
    """Response voor het cognitieve profiel van de Digital Twin."""

    coding_style: dict[str, object] = Field(default_factory=dict)
    work_patterns: dict[str, object] = Field(default_factory=dict)
    optimal_help_style: str | None = Field(None)
    confidence_level: float | None = Field(None)
    observation_count: int | None = Field(None)


class TwinBehaviorPatternResponse(BaseModel):
    """Een gedragspatroon binnen het consent-profiel (SP-ARCH-ARCH-2)."""

    name: str
    frequency: int
    last_observed: str


class TwinConsentProfileResponse(BaseModel):
    """Aggregate consent + gedragsprofiel voor de huidige user (SP-ARCH-ARCH-2).

    avg_cognitive_delay_ms/context_usage_percent hebben nog geen onderliggende
    metric in dit domein -- retourneren None (niet 0.0) totdat een echte bron
    bestaat. 0.0 zou een data subject in een AVG-transparantie-endpoint kunnen
    laten lezen als "gemeten en nul", wat een misleidende feitelijke claim is.
    """

    user_id: str
    consent_status: str  # active | revoked | pending
    behavior_patterns: list[TwinBehaviorPatternResponse]
    avg_cognitive_delay_ms: float | None
    context_usage_percent: float | None
    last_updated_at: str
    data_retained_until: str | None


class Art22InfoResponse(BaseModel):
    """Response voor AVG Artikel 22 informatie."""

    applies_to_user: bool = Field(
        description="True als de user momenteel onderhevig is aan geautomatiseerde besluitvorming"
    )
    description: str = Field(description="Uitleg van wat de Digital Twin doet")
    opt_out_path: str = Field(description="Hoe de user kan opt-outen")
    legal_basis: str = Field(description="Rechtsgrondslag voor de verwerking")
    human_oversight: str = Field(description="Beschrijving van menselijke tussenkomst")


class ConsentFeedbackRequest(BaseModel):
    """Request voor feedback bij consent wijziging."""

    category: str = Field(
        ..., description="Welke categorie: ai_interventions, behavior_tracking, etc."
    )
    enabled: bool = Field(..., description="True = ingeschakeld, False = uitgeschakeld")
    reason: str | None = Field(None, description="Vrijwillige reden voor de wijziging")
    source: str = Field("settings_page", description="Waar de wijziging vandaan komt")


class SuggestionFeedbackRequest(BaseModel):
    """Request voor feedback op een specifieke twin suggestie."""

    was_useful: bool = Field(..., description="True = suggestie was nuttig, False = niet nuttig")
    comment: str | None = Field(None, description="Optionele toelichting")


# --- Dependency: PracticalTwinService -----------------------------------------


async def _get_redis_safe() -> Any | None:  # TODO(TYPE): replace Any with concrete type
    """Get Redis client with graceful fallback to None."""
    try:
        return await get_redis_client()
    except Exception as exc:
        logger.debug("twin_redis_unavailable", error=str(exc))
        return None


async def _get_twin_service(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AsyncGenerator["PracticalTwinService", None]:
    """Maak een PracticalTwinService aan met alle dependencies.

    De batch manager en event bus zijn singletons (gestart bij app boot).
    """
    from src.core.learning.services.practical_twin_service import PracticalTwinService
    from src.core.learning.services.twin_service_factory import (
        create_practical_twin_service,
    )

    redis_client = await _get_redis_safe()
    service = await create_practical_twin_service(
        db=db, tenant_id=current_user.tenant_id, redis_client=redis_client
    )
    yield service


async def _get_consent_manager(
    db: AsyncSession = Depends(get_db),
) -> "TwinConsentManager":
    from src.core.learning.consent.consent_manager import (
        TwinConsentManager,
    )

    redis_client = await _get_redis_safe()
    return TwinConsentManager(db=db, cache=redis_client)


# --- Endpoints ----------------------------------------------------------------


@router.post(
    "/track-user-behavior",
    response_model=TrackBehaviorResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Track een user gedrags-observatie",
    description=(
        "Slaat een geanonimiseerde user gedrags-observatie op. "
        "De observatie wordt gefilterd door de PrivacyFilter voordat opslag. "
        "Geeft 202 Accepted terug zodra de observatie in de batch queue is."
    ),
)
@twin_limiter.limit("30/minute")
async def track_user_behavior(
    request: Request,
    response: Response,
    body: TrackBehaviorRequest,
    current_user: User = Depends(get_current_user),
    service: "PracticalTwinService" = Depends(_get_twin_service),
) -> TrackBehaviorResponse:
    """Track een user gedrags-observatie."""
    try:
        trace_id = await service.track_behavior(
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
            session_id=body.session_id,
            behavior_type=body.behavior_type,
            context=body.context,
            outcome_metrics=body.outcome_metrics,
            confidence_score=body.confidence_score,
        )

        if trace_id is None:
            return TrackBehaviorResponse(
                trace_id=None,
                accepted=False,
                reason="rejected_by_guard",
            )

        return TrackBehaviorResponse(trace_id=trace_id, accepted=True, reason=None)

    except Exception as exc:
        logger.error(
            "twin_api_track_error",
            user_id=current_user.id,
            behavior_type=body.behavior_type,
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
        # Geen 500 -- de twin mag de hoofdapp niet storen
        return TrackBehaviorResponse(
            trace_id=None, accepted=False, reason=f"internal_error:{type(exc).__name__}"
        )


@router.post(
    "/analyze-struggle",
    response_model=AnalyzeStruggleResponse,
    summary="Analyseer struggle score en genereer suggestie",
)
@twin_limiter.limit("10/minute")
async def analyze_struggle(
    request: Request,
    response: Response,
    body: AnalyzeStruggleRequest,
    current_user: User = Depends(get_current_user),
    service: "PracticalTwinService" = Depends(_get_twin_service),
) -> AnalyzeStruggleResponse:
    """Bereken WeightedStruggleScore en genereer een suggestie indien nodig."""
    result = await service.analyze_struggle(
        context=body.context,
        user_profile=body.user_profile,
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )
    return AnalyzeStruggleResponse(**result)


@router.get(
    "/twin/consent",
    response_model=ConsentStatusResponse,
    summary="Haal consent status op voor de huidige user",
)
@twin_limiter.limit("180/minute")
async def get_consent_status(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    consent_mgr: "TwinConsentManager" = Depends(_get_consent_manager),
) -> ConsentStatusResponse:
    """Geef de huidige consent status + granular categories terug."""
    consent_status = await consent_mgr.get_consent_status(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )
    categories = await consent_mgr.get_consent_categories(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )
    return ConsentStatusResponse(
        status=consent_status.value,
        categories=ConsentCategoriesResponse(
            behavior_tracking=categories.behavior_tracking,
            profile_aggregation=categories.profile_aggregation,
            ai_interventions=categories.ai_interventions,
            cross_session_memory=categories.cross_session_memory,
        ),
    )


@router.put(
    "/twin/consent",
    response_model=ConsentStatusResponse,
    summary="Update consent status",
)
@twin_limiter.limit("30/minute")
async def update_consent_status(
    request: Request,
    response: Response,
    body: ConsentUpdateRequest,
    current_user: User = Depends(get_current_user),
    consent_mgr: "TwinConsentManager" = Depends(_get_consent_manager),
) -> ConsentStatusResponse:
    """Update de consent status van de huidige user."""
    try:
        from src.core.learning.consent.consent_manager import TwinConsentStatus

        new_status = TwinConsentStatus(body.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Ongeldige status '{body.status}'. Geldige waarden: enabled, disabled, paused"
            ),
        )

    await consent_mgr.set_consent_status(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
        status=new_status,
    )
    categories = await consent_mgr.get_consent_categories(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )
    return ConsentStatusResponse(
        status=new_status.value,
        categories=ConsentCategoriesResponse(
            behavior_tracking=categories.behavior_tracking,
            profile_aggregation=categories.profile_aggregation,
            ai_interventions=categories.ai_interventions,
            cross_session_memory=categories.cross_session_memory,
        ),
    )


@router.patch(
    "/twin/consent",
    response_model=ConsentStatusResponse,
    summary="Update granular consent categories",
)
@twin_limiter.limit("30/minute")
async def update_consent_categories(
    request: Request,
    response: Response,
    body: ConsentCategoriesUpdateRequest,
    current_user: User = Depends(get_current_user),
    consent_mgr: "TwinConsentManager" = Depends(_get_consent_manager),
) -> ConsentStatusResponse:
    """Update de granular consent categories van de huidige user (partial update)."""
    # Fetch current categories
    current = await consent_mgr.get_consent_categories(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )

    # Apply partial update
    from src.core.learning.consent.consent_manager import ConsentCategories

    updated = ConsentCategories(
        behavior_tracking=body.behavior_tracking
        if body.behavior_tracking is not None
        else current.behavior_tracking,
        profile_aggregation=body.profile_aggregation
        if body.profile_aggregation is not None
        else current.profile_aggregation,
        ai_interventions=body.ai_interventions
        if body.ai_interventions is not None
        else current.ai_interventions,
        cross_session_memory=body.cross_session_memory
        if body.cross_session_memory is not None
        else current.cross_session_memory,
    )

    await consent_mgr.set_consent_categories(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
        categories=updated,
    )

    # Return updated status
    status_value = await consent_mgr.get_consent_status(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )
    return ConsentStatusResponse(
        status=status_value.value,
        categories=ConsentCategoriesResponse(
            behavior_tracking=updated.behavior_tracking,
            profile_aggregation=updated.profile_aggregation,
            ai_interventions=updated.ai_interventions,
            cross_session_memory=updated.cross_session_memory,
        ),
    )


class DeleteTwinDataResponse(BaseModel):
    """Response model for async hard delete request."""

    job_id: str = Field(..., description="Dramatiq message ID voor tracking")
    status: str = Field(default="queued", description="Status van de delete job")
    message: str = Field(
        default="Verwijdering van twin data is gequeued en wordt async uitgevoerd.",
        description="Menselijk leesbare status",
    )


@router.delete(
    "/twin/data",
    status_code=status.HTTP_202_ACCEPTED,
    summary="GDPR: Verwijder alle twin data (Right to Erasure)",
    response_model=DeleteTwinDataResponse,
)
@twin_limiter.limit("10/minute")
async def delete_twin_data(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> DeleteTwinDataResponse:
    """
    GDPR Artikel 17: Right to Erasure.

    Queued een async job om alle twin data (observaties, profiel, consent,
    suggestion logs) voor de huidige user te verwijderen.

    Returns 202 Accepted met een job ID voor tracking.
    """
    from src.core.learning.worker import twin_hard_delete_async

    message = twin_hard_delete_async.send(
        str(current_user.id),
        current_user.tenant_id,
    )
    job_id = str(message.message_id) if hasattr(message, "message_id") else "unknown"

    logger.info(
        "twin_data_hard_delete_queued",
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        job_id=job_id,
    )

    return DeleteTwinDataResponse(
        job_id=job_id,
        status="queued",
        message="Verwijdering van twin data is gequeued en wordt async uitgevoerd.",
    )


@router.get(
    "/twin/export",
    summary="GDPR: Exporteer alle twin data (Data Portability)",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
)
@twin_limiter.limit("30/minute")
async def export_twin_data(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    consent_mgr: "TwinConsentManager" = Depends(_get_consent_manager),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    GDPR Artikel 20: Data Portability.

    Exporteert alle twin data voor de huidige user als JSON.
    """
    return await consent_mgr.export_user_data(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )


@router.get(
    "/twin/profile",
    response_model=TwinProfileResponse,
    summary="Haal het cognitieve profiel op",
)
@twin_limiter.limit("180/minute")
async def get_twin_profile(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    service: "PracticalTwinService" = Depends(_get_twin_service),
    db: AsyncSession = Depends(get_db),
) -> TwinProfileResponse:
    """Lees het cognitieve profiel van de huidige user uit de Digital Twin."""
    profile = await service.get_profile(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
        db=db,
    )
    return TwinProfileResponse(**profile)


_CONSENT_STATUS_MAP = {"enabled": "active", "disabled": "revoked", "paused": "pending"}


@router.get(
    "/twin/consent-profile",
    response_model=TwinConsentProfileResponse,
    summary="Aggregate consent + gedragsprofiel voor de huidige user",
)
@twin_limiter.limit("180/minute")
async def get_twin_consent_profile(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    consent_mgr: "TwinConsentManager" = Depends(_get_consent_manager),
    db: AsyncSession = Depends(get_db),
) -> TwinConsentProfileResponse:
    """Aggregeert consent-status, geleerde gedragspatronen en retentiedatum
    (SP-ARCH-ARCH-2 / ARCH-002 -- frontend contract voor useDigitalTwinProfile).
    """
    from datetime import datetime, timezone

    from sqlalchemy import func, select

    from src.core.learning.privacy.privacy_filter import PrivacyFilter
    from src.core.learning.twin_models import UserBehaviorObservation, UserCognitiveProfile

    consent_status = await consent_mgr.get_consent_status(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )

    hashed_user_id = PrivacyFilter.hash_user_id(str(current_user.id), current_user.tenant_id)
    obs_result = await db.execute(
        select(
            UserBehaviorObservation.behavior_type,
            func.count(UserBehaviorObservation.id),
            func.max(UserBehaviorObservation.created_at),
            func.max(UserBehaviorObservation.expires_at),
        )
        .where(
            UserBehaviorObservation.human_user_id == hashed_user_id,
            UserBehaviorObservation.tenant_id == current_user.tenant_id,
        )
        .group_by(UserBehaviorObservation.behavior_type)
    )
    rows = obs_result.all()

    behavior_patterns = [
        TwinBehaviorPatternResponse(
            name=behavior_type,
            frequency=count,
            last_observed=last_observed.isoformat() if last_observed else "",
        )
        for behavior_type, count, last_observed, _expires in rows
    ]
    data_retained_until = max(
        (expires for _bt, _c, _lo, expires in rows if expires is not None), default=None
    )

    profile_result = await db.execute(
        select(UserCognitiveProfile.updated_at).where(
            UserCognitiveProfile.human_user_id == str(current_user.id),
            UserCognitiveProfile.tenant_id == current_user.tenant_id,
        )
    )
    last_updated_at = profile_result.scalar_one_or_none() or datetime.now(timezone.utc)

    return TwinConsentProfileResponse(
        user_id=str(current_user.id),
        consent_status=_CONSENT_STATUS_MAP.get(consent_status.value, "pending"),
        behavior_patterns=behavior_patterns,
        avg_cognitive_delay_ms=None,
        context_usage_percent=None,
        last_updated_at=last_updated_at.isoformat(),
        data_retained_until=data_retained_until.isoformat() if data_retained_until else None,
    )


@router.get(
    "/twin/consent/art22-info",
    response_model=Art22InfoResponse,
    summary="AVG Artikel 22: Informatie over geautomatiseerde besluitvorming",
)
@twin_limiter.limit("180/minute")
async def get_art22_info(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    consent_mgr: "TwinConsentManager" = Depends(_get_consent_manager),
) -> Art22InfoResponse:
    """
    AVG Artikel 22: Right not to be subject to automated decision-making.

    Retourneert informatie over of en hoe de Digital Twin
    geautomatiseerde besluitvorming toepast op de huidige user.
    """
    categories = await consent_mgr.get_consent_categories(
        user_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )

    # The Twin generates AI suggestions based on struggle detection.
    # This is NOT a decision with legal or significant impact, so
    # strictly speaking it falls outside Art. 22's strict regime.
    # However, we treat it as Art. 22-applicable for transparency.
    return Art22InfoResponse(
        applies_to_user=categories.ai_interventions,
        description=(
            "The Digital Twin analyzes your workflow patterns (e.g. repeated edits, "
            "file switches) to detect when you might be stuck. When a high struggle "
            "score is detected, it generates an AI-powered suggestion. "
            "This is a recommendation, not a binding decision."
        ),
        opt_out_path=(
            "Disable 'AI Interventions' in your Digital Twin settings. "
            "You can do this at any time without affecting other features."
        ),
        legal_basis="AVG Art. 6(1)(f) legitimate interest + Art. 7 consent",
        human_oversight=(
            "All AI suggestions are optional. You choose whether to follow them. "
            "No automated decision produces legal effects or significantly affects you."
        ),
    )


@router.post(
    "/twin/consent/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Feedback bij consent wijziging (voor audit trail)",
    response_class=Response,
)
@twin_limiter.limit("30/minute")
async def post_consent_feedback(
    request: Request,
    response: Response,
    body: ConsentFeedbackRequest,
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Log feedback wanneer een user een consent categorie wijzigt.

    Deze endpoint is best-effort: als logging faalt, krijgt de user
    geen error (per AGENTS.md non-critical operations rule).
    """
    from src.core.utils.best_effort import best_effort

    async with best_effort("consent_feedback"):
        logger.info(
            "consent_feedback_received",
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            category=body.category,
            enabled=body.enabled,
            reason=body.reason,
            source=body.source,
        )


@router.post(
    "/twin/suggestion/{log_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Feedback op een twin suggestie (eval harness)",
    response_class=Response,
)
@twin_limiter.limit("60/minute")
async def post_suggestion_feedback(
    request: Request,
    response: Response,
    log_id: int,
    body: SuggestionFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Geef feedback op een specifieke AI suggestie (eval harness).

    Wordt gebruikt om suggestie kwaliteit te meten en providers
    te vergelijken. Best-effort: faalt stil.
    """
    from src.core.learning.cost.cost_tracker import CostTracker
    from src.core.utils.best_effort import best_effort

    async with best_effort("suggestion_feedback"):
        tracker = CostTracker(db=db)
        await tracker.record_feedback(log_id=log_id, was_useful=body.was_useful)
        logger.info(
            "suggestion_feedback_received",
            log_id=log_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            was_useful=body.was_useful,
            comment=body.comment,
        )
