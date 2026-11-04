"""Pack selector endpoint - exposes PackActivationScorer to the frontend.

Used by: frontend/src/components/company/AIMatching.tsx
Golden Rule R2: every result includes match_reason, confidence, input_signals, audit_log_id.

A/B Testing Integration:
- Checks for active experiments
- Assigns variants consistently per company
- Tracks exposed and converted events
- Applies different scoring strategies per variant
"""
# orphan:exempt -- registered dynamically via importlib in company registry

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import get_current_user
from src.core.company.models import Company
from src.core.company.pack_activation import ActivationSignals, PackActivationScorer
from src.core.api.v1.company.dependencies import ExperimentService, get_db
from src.core.observability.tracing import HAS_OPENTELEMETRY

router = APIRouter(prefix="/pack-selector", tags=["pack-selector"])


class PackSelectorRequest(BaseModel):
    company_id: UUID
    department_id: UUID | None = None
    signals: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


class PackSelectorResult(BaseModel):
    pack_id: str
    pack_name: str
    confidence: float
    match_reason: str
    input_signals: list[str]
    score_breakdown: dict[str, float]
    audit_log_id: str
    activated_automatically: bool


@router.post("", response_model=list[PackSelectorResult])
async def select_packs(
    body: PackSelectorRequest,
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
    session: AsyncSession = Depends(get_db),
) -> list[PackSelectorResult]:
    """Score available packs against the provided signals and return ranked results.

    Returns only packs above the suggestion threshold (confidence >= 0.30).
    Auto-activation threshold is 0.70 - indicated by activated_automatically=True.

    A/B Testing: This endpoint participates in active experiments, assigning
    companies to control or treatment variants and tracking exposures/conversions.
    """
    # Validate company belongs to user's tenant
    company = await session.get(Company, body.company_id)
    if not company or company.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Execute pack selection once (never retry on error)
    results = await _execute_pack_selection(body, session, tenant_id=current_user.tenant_id)

    # Add OpenTelemetry span attributes after successful execution
    if HAS_OPENTELEMETRY:
        try:
            from opentelemetry import trace

            active_tracer = trace.get_tracer(
                instrumenting_module_name="sanskritisetu.pack_selector"
            )
            with active_tracer.start_as_current_span("pack_selector_endpoint") as span:
                span.set_attribute("company.id", str(body.company_id))
                if body.department_id:
                    span.set_attribute("department.id", str(body.department_id))
                if results:
                    span.set_attribute("pack.count", len(results))
                    top_result = max(results, key=lambda x: x.confidence)
                    span.set_attribute("recommendation.top_score", top_result.confidence)
        except Exception:
            pass  # Telemetry failures must not fail the request

    return results


async def _execute_pack_selection(
    body: PackSelectorRequest,
    session: AsyncSession | None = None,
    tenant_id: int | None = None,
) -> list[PackSelectorResult]:
    """Execute the pack selection logic with A/B testing integration.

    Args:
        body: Pack selector request
        session: Optional database session for experiment tracking

    Returns:
        List of pack selector results
    """
    # Initialize experiment service if session provided
    experiment_service = None
    active_experiment = None
    variant = None

    if session:
        experiment_service = ExperimentService(session)
        # Check for active experiments
        active_experiments = await experiment_service.get_active_experiments()
        if active_experiments:
            # Use first active experiment (can be extended for multiple)
            active_experiment = active_experiments[0]
            # Assign variant consistently for this company
            variant = await experiment_service.assign_variant_with_split(
                active_experiment.id, body.company_id
            )
            # Track exposure event
            await experiment_service.track_event(
                experiment_id=active_experiment.id,
                company_id=body.company_id,
                event_type="exposed",
                variant=variant,
                metadata={"department_id": str(body.department_id) if body.department_id else None},
            )

    # Apply variant-specific scoring strategy
    signals = ActivationSignals(
        department_name=body.signals.get("department_name", ""),
        company_type=body.signals.get("company_type", ""),
        sector=body.signals.get("sector", ""),
        sector_tags=body.signals.get("sector_tags", []),
        explicit_pack_ids=body.signals.get("explicit_pack_ids", []),
    )

    # Modify signals based on variant (A/B testing)
    if variant == "treatment" and active_experiment:
        # Treatment variant: use alternative scoring strategy
        # Example: Boost explicit pack matches
        signals.explicit_pack_ids = _boost_explicit_packs(signals.explicit_pack_ids)

    # Fetch active packs for this tenant from the database
    packs_for_scorer: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    if session is not None and tenant_id is not None:
        from types import SimpleNamespace

        from sqlalchemy import select

        from src.core.procedures.models import DomainPack

        stmt = select(DomainPack).where(
            DomainPack.tenant_id == tenant_id,
            DomainPack.status == "active",
        )
        db_result = await session.execute(stmt)
        packs_for_scorer = [
            SimpleNamespace(
                pack_id=str(p.id),
                name=p.name,
                department=p.department,
                intent_tags=p.capabilities or [],
            )
            for p in db_result.scalars().all()
        ]

    scorer = PackActivationScorer()
    results = scorer.score_all_packs(
        packs_for_scorer, signals, str(body.company_id), str(body.department_id)
    )

    # Track conversion if any packs are auto-activated (confidence >= 0.70)
    if experiment_service and active_experiment and variant:
        auto_activated = any(r.activated_automatically for r in results)
        if auto_activated:
            await experiment_service.track_event(
                experiment_id=active_experiment.id,
                company_id=body.company_id,
                event_type="converted",
                variant=variant,
                metadata={
                    "auto_activated_count": sum(1 for r in results if r.activated_automatically),
                    "top_confidence": (
                        max(results, key=lambda x: x.confidence).confidence if results else 0
                    ),
                },
            )

    return [
        PackSelectorResult(
            pack_id=r.pack_id,
            pack_name=r.pack_name,
            confidence=r.score,
            match_reason=r.match_reason,
            input_signals=r.input_signals,
            score_breakdown=r.score_breakdown,
            audit_log_id=str(r.audit_log_id),
            activated_automatically=r.activated_automatically,
        )
        for r in results
    ]


def _boost_explicit_packs(pack_ids: list[str]) -> list[str]:
    """Boost explicit pack IDs for treatment variant.

    This is an example of how the treatment variant can apply
    different scoring logic. In a real scenario, this could:
    - Add additional pack IDs based on ML predictions
    - Reorder packs based on historical performance
    - Include experimental pack recommendations

    Args:
        pack_ids: Original explicit pack IDs

    Returns:
        Potentially modified pack IDs
    """
    # For now, just return original (placeholder for treatment logic)
    # This could add additional packs or reorder them
    return pack_ids
