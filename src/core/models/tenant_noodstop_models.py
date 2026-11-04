"""De noodstop per klant: staat een klant stil of niet (noodstop per klant, ADR-036 OP-03).

Een rij per klant. Het ontbreken van een rij betekent: de klant is NIET stilgezet. Een rij met
`is_stilgezet = true` betekent dat geen enkele agent van deze klant nog een actie mag starten
(zie `src/core/noodstop/guard.py`, de controle die elke deur uitvoert).

Waarom een tabel en geen geheugen of alleen Redis: de stand moet een herstart overleven en gelden
in elke worker en elk proces (ADR-010). De database is de bron.

`changed_by_platform` onthoudt dat een PLATFORMBEHEERDER de klant heeft stilgezet. Alleen een
platformbeheerder mag dat weer opheffen: anders kon de klant een stop van het platform (bijvoorbeeld
bij misbruik) zelf ongedaan maken.

`reden`, `changed_by_user_id` en `changed_at` beschrijven de LAATSTE wijziging; de volledige
geschiedenis staat in de auditlog (`noodstop_changed`).

Elke query filtert op `tenant_id` (ADR-005) en de tabel heeft Row Level Security.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import false, func

from src.core.database.database import Base

#: Grens voor de reden; een bron voor het model, de API-validatie en de CHECK-constraint.
REDEN_MAX_LENGTE = 500


class TenantNoodstop(Base):  # type: ignore[misc]
    """De noodstopstand van een klant."""

    __tablename__ = "tenant_noodstop"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_noodstop_tenant"),
        CheckConstraint(
            # `length`, niet `char_length`: zie `tenant_pack_activation_models` (SQLite in unit-tests).
            f"reden IS NULL OR length(reden) BETWEEN 1 AND {REDEN_MAX_LENGTE}",
            name="ck_tenant_noodstop_reden_lengte",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_stilgezet: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    reden: Mapped[str | None] = mapped_column(String(REDEN_MAX_LENGTE), nullable=True)
    changed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_by_platform: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
