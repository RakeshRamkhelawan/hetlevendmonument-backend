"""Uitgaande berichten: de post die een agent klaarzet, NA menselijke goedkeuring.

Debiteurenagent dag 2 (brief
`docs/agent-briefs/generated/2026-10-05-sprint-dag-debiteurenagent-dag-2-tools-en-goedkeuring.md`).

**Waarom een tabel en geen e-mail (besluit 2 van dag 1).** "Versturen" betekent vandaag: een rij
in deze tabel met precies de tekst die de mens heeft goedgekeurd. Dat maakt scenario 5 lokaal en
in CI vast te stellen, en er gaat niets de deur uit zonder goedkeuring. De echte verzending
(SMTP) leest later uit deze tabel; `status` staat daarom op `klaar` en niet op `verzonden`.

**Een bericht per goedkeuring.** `hitl_ticket_ref` is uniek: dezelfde goedkeuring kan nooit twee
berichten opleveren, ook niet als de eenmaligheid van het ticket elders ooit zou falen.

**Tenantscheiding.** `tenant_id` NOT NULL met een sleutel naar `tenants` en een leidende index;
de migratie `20261006_outgoing_messages_rls.py` zet RLS aan met de standaardpolicy.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

#: Gesloten vocabulaires; dezelfde waarden staan in de CHECK-constraints.
OUTGOING_MESSAGE_KINDS = ("herinnering", "aanmaning")
OUTGOING_MESSAGE_STATUSES = ("klaar", "verzonden", "mislukt")

#: Na dit aantal pogingen wordt een mislukt bericht niet meer opgepakt.
MAX_POGINGEN = 3

#: Een geannuleerd bericht is `mislukt` met `pogingen = MAX_POGINGEN` en een foutreden met dit voorvoegsel. Een eigen
#: status `geannuleerd` vraagt een nieuwe CHECK (migratie); tot die er is, is dit de afgesproken vorm: het wordt nooit
#: meer opgepakt en de tijdlijn herkent het aan het voorvoegsel.
GEANNULEERD_VOORVOEGSEL = "Geannuleerd:"
FOUTREDEN_GEANNULEERD_BETAALD = (
    "Geannuleerd: de factuur is betaald of staat niet meer open, dus de brief is niet verstuurd."
)
FOUTREDEN_GEANNULEERD_ONBEKEND = (
    "Geannuleerd: de factuur is niet gevonden bij dit bedrijf, dus de brief is niet verstuurd."
)


def _nu_utc() -> datetime:
    return datetime.now(timezone.utc)


class OutgoingMessage(Base):  # type: ignore[misc]
    """Een goedgekeurd bericht aan een klant van de tenant, klaar voor verzending."""

    __tablename__ = "outgoing_messages"
    __table_args__ = (
        CheckConstraint("channel IN ('email')", name="ck_outgoing_messages_channel"),
        CheckConstraint(
            "kind IN ('herinnering', 'aanmaning')", name="ck_outgoing_messages_kind"
        ),
        CheckConstraint(
            "status IN ('klaar', 'verzonden', 'mislukt')", name="ck_outgoing_messages_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SET NULL en niet CASCADE: het bericht is het bewijs van wat er is goedgekeurd en hoort niet
    # stil mee te verdwijnen als iemand de factuur later weghaalt.
    receivable_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("receivables.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="klaar")
    hitl_ticket_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_nu_utc, server_default=func.now()
    )
    verzonden_op: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pogingen: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    foutreden: Mapped[str | None] = mapped_column(Text, nullable=True)
