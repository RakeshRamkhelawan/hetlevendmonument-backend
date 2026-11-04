"""Crediteuren: leveranciers en inkoopfacturen van een tenant (Keten F, dag 1).

Brief `docs/agent-briefs/generated/2026-10-24-sprint-dag-crediteuren-dag1-inkoopfacturen-vastleggen.md`. Alleen het vastleggen;
goedkeuren, een betaalbestand en afboeken volgen op latere dagen. De opbouw volgt `receivable_models.py` (debiteuren).

**Geld is een geheel aantal centen.** `amount_cents` is `BigInteger`, nooit float en geen tekst: een bedrag is dan overal
exact te vergelijken en op te tellen, ook in een SEPA-betaalbestand (dag 4). De valuta staat er los naast.

**Een factuur kan niet naar de leverancier van een ander bedrijf wijzen.** `payables (tenant_id, supplier_id)` verwijst naar
`suppliers (tenant_id, id)`, geen kale `supplier_id`. Row Level Security schermt de rijen af voor de applicatierol; deze sleutel
houdt de relatie zelf binnen een tenant, ook voor de eigenaar (de applicatie verbindt nu als eigenaar, OP-151).

**Geen dubbele factuur.** Uniek per tenant: (leverancier, factuurnummer van de leverancier), HOOFDLETTERONGEVOELIG
(`lower(...)` in een unieke index): "INK-1" en "ink-1" zijn een factuur. Dezelfde regel geldt voor de naam van een leverancier.

**Tenantscheiding.** `tenant_id` NOT NULL met een sleutel naar `tenants` en een leidende index (RLS-prestatie, OP-161). De
migratie `20261024_payables_rls.py` zet RLS aan met de standaardpolicy.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.database.database import Base

#: Gesloten vocabulaire van het statusverloop; dezelfde waarden staan in de CHECK-constraint. Dag 1 zet alleen
#: `ontvangen` en `gecontroleerd`; de rest is voor dag 3 (goedkeuren) en dag 4 (betaalbestand, afboeken).
PAYABLE_STATUSES = (
    "ontvangen",
    "gecontroleerd",
    "goedgekeurd",
    "in_betaalbestand",
    "betaald",
    "afgewezen",
)


def _nu_utc() -> datetime:
    return datetime.now(timezone.utc)


class Supplier(Base):  # type: ignore[misc]
    """Een leverancier van een tenant."""

    __tablename__ = "suppliers"
    __table_args__ = (
        # Hoofdletterongevoelig: "Acme BV" en "ACME BV" zijn een leverancier (Gate 2: dubbel betalen is het risico).
        Index("uq_suppliers_tenant_lower_name", "tenant_id", text("lower(name)"), unique=True),
        # Doel van de samengestelde sleutel van `payables`; (tenant_id, id) is al uniek omdat `id` dat is.
        UniqueConstraint("tenant_id", "id", name="uq_suppliers_tenant_id_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_nu_utc, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_nu_utc,
        onupdate=_nu_utc,
        server_default=func.now(),
    )


class Payable(Base):  # type: ignore[misc]
    """Een inkoopfactuur van een leverancier van de tenant."""

    __tablename__ = "payables"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["suppliers.tenant_id", "suppliers.id"],
            name="fk_payables_tenant_supplier",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_payables_tenant_supplier_lower_invoice",
            "tenant_id",
            "supplier_id",
            text("lower(invoice_number)"),
            unique=True,
        ),
        CheckConstraint(
            "status IN ('ontvangen', 'gecontroleerd', 'goedgekeurd', 'in_betaalbestand', 'betaald', 'afgewezen')",
            name="ck_payables_status",
        ),
        CheckConstraint("amount_cents > 0", name="ck_payables_amount_positive"),
        # Bewust geen regex: `~` is PostgreSQL, en de unit-tests bouwen deze tabel met `create_all` op SQLite.
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)", name="ck_payables_currency_iso"
        ),
        CheckConstraint("due_date >= invoice_date", name="ck_payables_due_after_invoice"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ontvangen")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_nu_utc, server_default=func.now()
    )
    #: Wie de factuur heeft vastgelegd; `SET NULL` zodat het wissen van een gebruiker (AVG) de factuur niet meeneemt.
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    checked_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: `joined`: een lijst heeft de naam van de leverancier nodig, en een lazy load werkt niet in async.
    supplier: Mapped[Supplier] = relationship(
        Supplier,
        primaryjoin="and_(Payable.tenant_id == Supplier.tenant_id, Payable.supplier_id == Supplier.id)",
        foreign_keys=[tenant_id, supplier_id],
        lazy="joined",
        viewonly=True,
    )
