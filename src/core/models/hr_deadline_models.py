"""Termijnen voor de HR-pilot (dag 3): een contract dat eindigt, verzuim, een certificaat.

Er wordt alleen vastgelegd WAT de regel is en welke datums de klant invult. De signaaldata zijn
afgeleid en worden BEREKEND (`src/core/utils/hr_deadline_rules.py`), niet opgeslagen.

**Verzuim is een gezondheidsgegeven.** De werkgever mag de aard of oorzaak van de ziekte niet
registreren. Daarom heeft een verzuimregel GEEN vrije tekst: de database dwingt af dat
`description` bij verzuim leeg is (CHECK). De rest van de regel (eerste ziektedag, datum van de
probleemanalyse) zegt niets over de ziekte zelf. Alleen wie `hr:read` heeft ziet deze rijen.

Enkelvoudige FKs, net als de andere HR-tabellen: de repository filtert elke query expliciet op
`tenant_id` en de tabel heeft RLS.
"""

from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

#: Gesloten vocabulaires, een bron voor model, API en CHECK-constraints.
DEADLINE_KINDS = ("contract_einde", "verzuim", "certificaat")
DEADLINE_STATUSES = ("open", "afgerond")


class HRDeadline(Base):  # type: ignore[misc]
    """Een ingevulde termijnregel van een medewerker."""

    __tablename__ = "hr_deadlines"
    __table_args__ = (
        CheckConstraint(
            "kind IN (" + ",".join(f"'{k}'" for k in DEADLINE_KINDS) + ")",
            name="ck_hr_deadlines_kind",
        ),
        CheckConstraint(
            "status IN (" + ",".join(f"'{s}'" for s in DEADLINE_STATUSES) + ")",
            name="ck_hr_deadlines_status",
        ),
        # Verzuim: een eerste ziektedag en GEEN vrije tekst. De andere soorten: een einddatum.
        CheckConstraint(
            "(kind = 'verzuim' AND start_date IS NOT NULL AND description IS NULL) "
            "OR (kind IN ('contract_einde','certificaat') AND end_date IS NOT NULL)",
            name="ck_hr_deadlines_dates",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    analysis_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", server_default="open"
    )
    # De termijnen (labels) van deze regel die al zijn afgehandeld; de rest blijft in de lijst.
    done_labels: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
