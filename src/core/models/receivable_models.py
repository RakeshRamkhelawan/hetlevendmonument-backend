"""Debiteuren: openstaande facturen van een tenant -- de databron van de debiteurenagent.

Dag 1 van 4 (brief `docs/agent-briefs/generated/2026-10-04-sprint-dag-debiteurenagent-dag-1-databron.md`).
Alleen de tabel; invoerroutes, import en koppeling komen later.

**Herkomst.** Een debiteur komt handmatig, uit een import of uit een koppeling met een
boekhoudpakket. `source` zegt welke, `external_id` is het nummer in het bronsysteem (leeg bij
handmatig). De unieke sleutel `(tenant_id, source, external_id)` laat een tweede import of
een koppeling dezelfde factuur bijwerken in plaats van dupliceren. PostgreSQL ziet twee NULLs
niet als gelijk, dus handmatige rijen (external_id NULL) botsen niet op die sleutel.

**Geld is decimaal.** `amount` is `Numeric(14, 2)`, nooit float.

**Tenantscheiding.** `tenant_id` NOT NULL met een sleutel naar `tenants` en een leidende
index (RLS-prestatie, OP-161). De migratie `20261005_receivables_rls.py` zet RLS aan met de
standaardpolicy.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

#: Gesloten vocabulaire; dezelfde waarden staan in de CHECK-constraint.
RECEIVABLE_STATUSES = ("open", "herinnerd", "geescaleerd", "betaald")
RECEIVABLE_SOURCES = ("handmatig", "import", "koppeling")


def _nu_utc() -> datetime:
    return datetime.now(timezone.utc)


class Receivable(Base):  # type: ignore[misc]
    """Een openstaande factuur van een klant van de tenant."""

    __tablename__ = "receivables"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source", "external_id", name="uq_receivables_tenant_source_external"
        ),
        CheckConstraint(
            "status IN ('open', 'herinnerd', 'geescaleerd', 'betaald')",
            name="ck_receivables_status",
        ),
        CheckConstraint(
            "source IN ('handmatig', 'import', 'koppeling')", name="ck_receivables_source"
        ),
        CheckConstraint(
            "(source = 'handmatig') = (external_id IS NULL)",
            name="ck_receivables_external_id_matches_source",
        ),
        # Dag 2 (migratie `20261006_receivables_checks.py`): geen negatieve vordering, en een
        # valuta van drie hoofdletters. Bewust geen regex: `~` is PostgreSQL, en de unit-tests
        # bouwen deze tabel met `create_all` op SQLite. De repository toetst de volle ISO-vorm
        # (drie letters A-Z); deze regel is het vangnet in de database.
        CheckConstraint("amount >= 0", name="ck_receivables_amount_not_negative"),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_receivables_currency_iso",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="handmatig")
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_nu_utc, server_default=func.now()
    )
    herinnerd_op: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    betaald_op: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
