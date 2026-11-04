"""Rendementscijfers (ROI): een rij per pack-run en een aanname per pack, per tenant.

SP-KLANT-04, brief `docs/agent-briefs/generated/2026-10-10-sprint-dag-roi-eerlijk-gemeten.md`,
onderzoek `docs/onderzoek-roi-rendementscijfers.md`.

**Twee lagen, en de database houdt ze uit elkaar.** `agent_run_metrics` bevat alleen wat gemeten
is: wat liep er, hoe liep het af, hoe lang, hoeveel items. `roi_assumptions` bevat wat de KLANT zegt
(minuten handwerk per item, uurtarief). Een besparing in euro's bestaat alleen als beide er zijn;
een vast getal in code is geen aanname maar een claim van ons (art. 6:195 BW).

**Geen medewerker in de meting.** Geen `user_id`, geen naam, geen e-mail, geen afdeling: een
rendementscijfer per persoon is monitoring (OR-instemming, art. 27 lid 1 sub l WOR; AVG art. 88).
Wie een run startte staat in de auditketen; de ROI-tabel heeft het niet nodig. Een architectuurtest
(`tests/architecture/test_roi_tabellen_kennen_geen_medewerker.py`) houdt dat zo.

**Tenantscheiding.** `tenant_id` NOT NULL met een sleutel naar `tenants` en een leidende index; de
migratie `20261010_roi_tabellen.py` zet RLS aan met de standaardpolicy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

#: Gesloten vocabulaires; dezelfde waarden staan in de CHECK-constraints. De statussen zijn die van
#: `ExecutionStatusContract` (`src/core/types.py`), zodat er geen tweede vocabulaire ontstaat.
RUN_STATUSSEN = ("klaar", "gedeeltelijk", "meer_budget_nodig", "geblokkeerd", "mislukt")
ASSUMPTION_SOURCES = ("klant_ingevuld",)


def _nu_utc() -> datetime:
    return datetime.now(timezone.utc)


class AgentRunMetric(Base):  # type: ignore[misc]
    """Een pack-stap die gelopen heeft: wat, hoe afgelopen, hoe lang, hoeveel items."""

    __tablename__ = "agent_run_metrics"
    __table_args__ = (
        CheckConstraint(
            "status IN ('klaar', 'gedeeltelijk', 'meer_budget_nodig', 'geblokkeerd', 'mislukt')",
            name="ck_agent_run_metrics_status",
        ),
        CheckConstraint(
            "items_processed IS NULL OR items_processed >= 0",
            name="ck_agent_run_metrics_items_processed",
        ),
        CheckConstraint(
            "llm_cost_eur IS NULL OR llm_cost_eur >= 0", name="ck_agent_run_metrics_llm_cost_eur"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pack_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    task_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL = niet gemeten. Een telling die niemand heeft gedaan is geen 0.
    items_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Eerlijkheid: menselijk nakijkwerk is geen nul. Staat standaard op false; de schrijver zet
    # hem alleen op true als de run zelf meldt dat een mens moest kijken.
    needed_human_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # NULL = niet gemeten (de pack-stap legt geen LLM-kosten per run vast).
    llm_cost_eur: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_nu_utc, server_default=func.now()
    )


class RoiAssumption(Base):  # type: ignore[misc]
    """De aanname van de klant per pack: hoeveel handwerk een item kost en wat een uur kost."""

    __tablename__ = "roi_assumptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "pack_id", name="uq_roi_assumptions_tenant_pack"),
        CheckConstraint(
            "manual_minutes_per_item > 0", name="ck_roi_assumptions_manual_minutes_per_item"
        ),
        CheckConstraint("hourly_rate_eur >= 0", name="ck_roi_assumptions_hourly_rate_eur"),
        CheckConstraint("source IN ('klant_ingevuld')", name="ck_roi_assumptions_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pack_id: Mapped[str] = mapped_column(String(100), nullable=False)
    manual_minutes_per_item: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    hourly_rate_eur: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="klant_ingevuld", server_default="klant_ingevuld"
    )
    set_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_nu_utc, server_default=func.now()
    )
