"""Welk pakket uit de catalogus staat voor welke klant AAN (pakket aanzetten, dag 1).

De catalogus (`config/domain_packs.yaml`) is globaal: hij weet niet welke klant welk pakket gebruikt.
Deze tabel legt per klant vast of een pakket aan staat. Het ontbreken van een rij betekent UIT: een
pakket is pas uitvoerbaar nadat een beheerder het heeft aangezet (ADR-039: de beheerder richt in, de
medewerker voert uit).

Bewust NIET de bestaande `domain_packs` (`src/core/procedures/models.py`): die is per klant maar niet
gekoppeld aan de catalogus-id (`mkb.zero_admin`), dus daarmee is het ene pakket niet van het andere te
onderscheiden.

`pack_id` is de catalogus-id als tekst, zonder vreemde sleutel: de catalogus staat in een
configuratiebestand, niet in de database. Een id die later uit de catalogus verdwijnt laat een
onschuldige rij achter; de routes tonen en gebruiken alleen id's die in de catalogus staan.

`enabled_at` is het moment van de LAATSTE wijziging (aan of uit) en `enabled_by_user_id` degene die die
wijziging deed: een herhaalde wijziging door een ander overschrijft ze, bedoeld, want deze twee kolommen
zijn "laatst gewijzigd door". De volledige geschiedenis staat in de auditlog
(`pack_activation_changed`): een regel per wijziging, met de gebruiker, het pakket en de nieuwe stand;
gemeten in tests/integration/test_pakketten_nazorg.py. De lijst toont "laatst gewijzigd door".

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

#: Grens voor de catalogus-id; een bron voor het model, de API-validatie en de CHECK-constraint.
PACK_ID_MAX_LENGTE = 100


class TenantPackActivation(Base):  # type: ignore[misc]
    """De stand (aan of uit) van een pakket voor een klant."""

    __tablename__ = "tenant_pack_activations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "pack_id", name="uq_tenant_pack_activations_tenant_pack"),
        CheckConstraint(
            # `length`, niet `char_length`: de unit-tests maken de tabellen in SQLite aan, waar
            # `char_length` niet bestaat; in PostgreSQL telt `length` ook tekens.
            f"length(pack_id) BETWEEN 1 AND {PACK_ID_MAX_LENGTE}",
            name="ck_tenant_pack_activations_pack_id_lengte",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pack_id: Mapped[str] = mapped_column(String(PACK_ID_MAX_LENGTE), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    enabled_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    enabled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
