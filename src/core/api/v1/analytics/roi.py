"""Rendementscijfers (ROI) van de eigen tenant, in twee lagen, plus de aannames van de klant.

GET  /analytics/roi                         -- GEMETEN en GESCHAT per pack (alleen per tenant)
GET  /analytics/roi/assumptions             -- de aannames van de klant
PUT  /analytics/roi/assumptions/{pack_id}   -- stel de aanname in (recht `packs:manage`)

Deze route stond tot 2026-10-10 in `src/core/api/v1/analytics.py`, een module die door het pakket
`src/core/api/v1/analytics/` werd overschaduwd en dus nooit werd geladen; `tests/integration/
test_roi_eerlijk_gemeten.py` eist de route nu in de echte app. De tenant komt uit de JWT, nooit uit
de body of de query.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.analytics.roi_service import AssumptionOut, ROIService, ROISummary
from src.core.api.dependencies import get_db
from src.core.api.v1.company.dependencies import (
    audit_service,
    require_resource_permission,
    validate_csrf_token,
)
from src.core.middleware.tenant_context import require_tenant_id
from src.core.utils.best_effort import best_effort

router = APIRouter(prefix="/analytics", tags=["Analytics"])


class AssumptionIn(BaseModel):
    """Wat de klant zegt. Geen `tenant_id`: die komt uit de login (extra velden worden genegeerd)."""

    model_config = ConfigDict(extra="ignore")

    manual_minutes_per_item: Decimal = Field(gt=0, le=100000)
    hourly_rate_eur: Decimal = Field(ge=0, le=100000)


@router.get("/roi", response_model=ROISummary)
async def get_tenant_roi_summary(
    tenant_id: int = Depends(require_tenant_id), db: AsyncSession = Depends(get_db)
) -> ROISummary:
    """GEMETEN (runs, geslaagd, items, kosten) en GESCHAT (uren, euro's, alleen met aanname)."""
    return await ROIService(db).get_tenant_roi(tenant_id)


@router.get("/roi/assumptions", response_model=list[AssumptionOut])
async def list_roi_assumptions(
    tenant_id: int = Depends(require_tenant_id), db: AsyncSession = Depends(get_db)
) -> list[AssumptionOut]:
    return await ROIService(db).list_assumptions(tenant_id)


@router.put(
    "/roi/assumptions/{pack_id}",
    response_model=AssumptionOut,
    dependencies=[Depends(validate_csrf_token)],
)
async def set_roi_assumption(
    pack_id: Annotated[str, Path(min_length=1, max_length=100)],
    data: AssumptionIn,
    tenant_id: int = Depends(require_tenant_id),
    user_id: int = Depends(require_resource_permission("packs", "manage")),
    db: AsyncSession = Depends(get_db),
) -> AssumptionOut:
    """Stel de handmatige tijd per item en het uurtarief voor dit pack in (de klant, niet wij)."""
    aanname = await ROIService(db).set_assumption(
        tenant_id, pack_id, float(data.manual_minutes_per_item), float(data.hourly_rate_eur)
    )
    await db.commit()

    # Een echte auditregel; de aanname is vastgelegd, ook als de regel faalt (best_effort).
    async with best_effort("roi.assumption_set audit log", db_session=db):
        await audit_service.log_action(
            tenant_id=tenant_id,
            action="roi.assumption_set",
            resource=f"roi_assumption:{pack_id}",
            user_id=user_id,
            details={
                "manual_minutes_per_item": aanname.manual_minutes_per_item,
                "hourly_rate_eur": aanname.hourly_rate_eur,
            },
            session=db,
        )
    return aanname
