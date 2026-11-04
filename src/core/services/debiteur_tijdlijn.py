"""De tijdlijn van een factuur: wat er met haar is gebeurd, door wie en wanneer (debiteuren vanzelf afronden, B4).

De medewerker moet per factuur kunnen volgen wat er is gebeurd zonder het logboek te lezen: aangemaakt, voorgesteld door,
goedgekeurd door, verstuurd, betaald of geescaleerd, met datum en naam, in het Nederlands. `bouw_tijdlijn` is een
zuivere functie over gewone gegevens (geen database); `lees_bronnen` haalt die gegevens op voor EEN vordering van EEN
tenant.

**Wat er NIET in staat.** Geen brieftekst, geen bedragen van een bankafschrift, geen tegenrekening, geen adres van de
debiteur: alleen gebeurtenissen, tijdstippen en de e-mailadressen van de medewerkers die handelden (er is geen aparte
naam; het adres is hoe `hitl_store` een besluiter toont). Een medewerker die niet meer bestaat staat er als "een
gebruiker die niet meer bestaat", geen verzonnen naam en geen kaal nummer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.outgoing_message_models import GEANNULEERD_VOORVOEGSEL

#: De naam voor een medewerker die niet (meer) te vinden is.
ONBEKENDE_MEDEWERKER = "een gebruiker die niet meer bestaat"

_SOORT_AANGEMAAKT = "receivable_created"
_SOORT_VOORGESTELD = "receivable_reminder_proposed"
_SOORT_STATUS = "receivable_status_changed"
_SOORT_BETAALD_AFSCHRIFT = "receivable_paid_via_bankstatement"
_SOORT_ESCALATIE = "debiteuren_dossier_geescaleerd"
_SOORT_BERICHT_MISLUKT = "debiteuren_bericht_mislukt"
_SOORT_BERICHT_GEANNULEERD = "debiteuren_bericht_geannuleerd"

_BRIEF = {"herinnering": "Herinnering", "aanmaning": "Aanmaning"}
_MAX_POGINGEN_TEKST = 3
#: De vrije notitie van een mens kan persoonsgegevens of brieftekst bevatten; de tijdlijn toont hem afgekapt (Gate 2).
_MAX_NOTITIE = 200


@dataclass(frozen=True)
class AuditBron:
    """Een auditregel zoals de tijdlijn hem nodig heeft."""

    soort: str
    resource: str | None
    tijdstip: datetime
    user_id: int | None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TicketBron:
    ticket_ref: str
    status: str
    resolved_by: int | None
    resolved_at: datetime | None
    notitie: str | None


@dataclass(frozen=True)
class BerichtBron:
    id: int
    kind: str
    status: str
    pogingen: int
    foutreden: str | None
    created_at: datetime
    verzonden_op: datetime | None
    hitl_ticket_ref: str | None


@dataclass(frozen=True)
class Bronnen:
    created_at: datetime
    status: str
    betaald_op: datetime | None
    audits: list[AuditBron] = field(default_factory=list)
    tickets: list[TicketBron] = field(default_factory=list)
    berichten: list[BerichtBron] = field(default_factory=list)
    namen: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Gebeurtenis:
    soort: str
    tekst: str
    tijdstip: datetime | None
    door: str | None


def _naam(bronnen: Bronnen, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    return bronnen.namen.get(user_id, ONBEKENDE_MEDEWERKER)


def _met_naam(tekst: str, naam: str | None) -> str:
    return f"{tekst} door {naam}" if naam else tekst


def _bericht_gebeurtenissen(bronnen: Bronnen, bericht: BerichtBron) -> list[Gebeurtenis]:
    brief = _BRIEF.get(bericht.kind, "Brief")
    uit = [
        Gebeurtenis("klaargezet", f"{brief} klaargezet voor verzending", bericht.created_at, None)
    ]
    if bericht.status == "verzonden":
        uit.append(Gebeurtenis("verzonden", f"{brief} verzonden", bericht.verzonden_op, None))
        return uit
    if bericht.status != "mislukt":
        return uit
    geannuleerd = (bericht.foutreden or "").startswith(GEANNULEERD_VOORVOEGSEL)
    soort = _SOORT_BERICHT_GEANNULEERD if geannuleerd else _SOORT_BERICHT_MISLUKT
    wanneer = next(
        (
            a.tijdstip
            for a in bronnen.audits
            if a.resource == f"outgoing_message:{bericht.id}" and a.soort == soort
        ),
        None,
    )
    if geannuleerd:
        reden = (bericht.foutreden or "")[len(GEANNULEERD_VOORVOEGSEL) :].strip()
        # `PATCH` naar betaald annuleert in dezelfde transactie en schrijft geen eigen auditregel: dan is het moment van
        # betalen het moment van annuleren (acceptatie 2026-10-21). Een mislukte brief leent dit tijdstip NIET.
        wanneer = wanneer or bronnen.betaald_op
        uit.append(Gebeurtenis("geannuleerd", f"{brief} niet verstuurd: {reden}", wanneer, None))
    else:
        tekst = (
            f"{brief} versturen mislukt (poging {bericht.pogingen} van de {_MAX_POGINGEN_TEKST})"
        )
        uit.append(Gebeurtenis("mislukt", tekst, wanneer, None))
    return uit


def bouw_tijdlijn(bronnen: Bronnen) -> list[Gebeurtenis]:
    """De gebeurtenissen van een factuur, oudste eerst, elk met een Nederlandse tekst."""
    gebeurtenissen: list[Gebeurtenis] = []
    aanmaker = next((a for a in bronnen.audits if a.soort == _SOORT_AANGEMAAKT), None)
    naam = _naam(bronnen, aanmaker.user_id) if aanmaker else None
    gebeurtenissen.append(
        Gebeurtenis("aangemaakt", _met_naam("Factuur aangemaakt", naam), bronnen.created_at, naam)
    )

    eigen_tickets: set[str] = {b.hitl_ticket_ref for b in bronnen.berichten if b.hitl_ticket_ref}
    for audit in bronnen.audits:
        if audit.soort != _SOORT_VOORGESTELD:
            continue
        brief = _BRIEF.get(str(audit.metadata.get("kind")), "Brief")
        naam = _naam(bronnen, audit.user_id)
        gebeurtenissen.append(
            Gebeurtenis(
                "voorgesteld", _met_naam(f"{brief} voorgesteld", naam), audit.tijdstip, naam
            )
        )
        ref = audit.metadata.get("ticket_ref")
        if isinstance(ref, str):
            eigen_tickets.add(ref)

    for ticket in bronnen.tickets:
        if ticket.ticket_ref not in eigen_tickets or ticket.resolved_at is None:
            continue
        naam = _naam(bronnen, ticket.resolved_by)
        if ticket.status in ("approved", "consumed"):
            gebeurtenissen.append(
                Gebeurtenis("goedgekeurd", _met_naam("Goedgekeurd", naam), ticket.resolved_at, naam)
            )
        elif ticket.status == "rejected":
            tekst = _met_naam("Afgekeurd", naam)
            if ticket.notitie:
                notitie = ticket.notitie
                if len(notitie) > _MAX_NOTITIE:
                    notitie = notitie[:_MAX_NOTITIE] + "..."
                tekst = f"{tekst}: {notitie}"
            gebeurtenissen.append(Gebeurtenis("afgekeurd", tekst, ticket.resolved_at, naam))

    for bericht in bronnen.berichten:
        gebeurtenissen.extend(_bericht_gebeurtenissen(bronnen, bericht))

    betaald_vastgelegd = False
    for audit in bronnen.audits:
        if audit.soort == _SOORT_ESCALATIE:
            gebeurtenissen.append(
                Gebeurtenis(
                    "geescaleerd",
                    "Dossier geescaleerd: de factuur is niet op tijd betaald",
                    audit.tijdstip,
                    None,
                )
            )
        elif audit.soort == _SOORT_BETAALD_AFSCHRIFT:
            betaald_vastgelegd = True
            gebeurtenissen.append(
                Gebeurtenis(
                    "betaald",
                    "Betaald, afgevinkt via een bankafschrift",
                    bronnen.betaald_op or audit.tijdstip,
                    None,
                )
            )
        elif audit.soort == _SOORT_STATUS and audit.metadata.get("new_status") == "betaald":
            betaald_vastgelegd = True
            naam = _naam(bronnen, audit.user_id)
            gebeurtenissen.append(
                Gebeurtenis(
                    "betaald",
                    _met_naam("Op betaald gezet", naam),
                    bronnen.betaald_op or audit.tijdstip,
                    naam,
                )
            )
    if bronnen.status == "betaald" and not betaald_vastgelegd:
        gebeurtenissen.append(Gebeurtenis("betaald", "Betaald", bronnen.betaald_op, None))

    zonder_tijd = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(gebeurtenissen, key=lambda g: g.tijdstip or zonder_tijd)


async def lees_bronnen(db: AsyncSession, *, tenant_id: int, receivable_id: int) -> Bronnen | None:
    """De gegevens voor de tijdlijn van EEN vordering van DEZE tenant; `None` als hij niet bestaat.

    Elke query filtert zelf op `tenant_id` (naast de hook). Een auditregel wordt alleen gelezen op de eigen resource
    van de vordering of van haar berichten, een ticket alleen binnen de tenant en alleen als zijn ref bij deze
    vordering hoort.
    """
    # Via importlib: `src/core/services` telt als agent_runtime en een statische import van governance telt mee in
    # het plafond van `test_dsm006_ar_governance_fan_out.py`.
    import importlib

    AuditLog = importlib.import_module("src.core.governance.models").AuditLog  # noqa: N806
    from src.core.models.outgoing_message_models import OutgoingMessage
    from src.core.models.rbac_models import User
    from src.core.models.receivable_models import Receivable
    from src.core.tool_broker.models import HITLTicket

    rij = (
        await db.execute(
            select(Receivable).where(
                Receivable.id == receivable_id, Receivable.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    if rij is None:
        return None
    berichten = list(
        (
            await db.execute(
                select(OutgoingMessage)
                .where(
                    OutgoingMessage.tenant_id == tenant_id,
                    OutgoingMessage.receivable_id == receivable_id,
                )
                .order_by(OutgoingMessage.id)
            )
        )
        .scalars()
        .all()
    )
    resources = [f"/api/v1/receivables/{receivable_id}", f"receivable:{receivable_id}"]
    resources += [f"outgoing_message:{b.id}" for b in berichten]
    audit_rijen = list(
        (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id, AuditLog.resource.in_(resources))
                .order_by(AuditLog.timestamp, AuditLog.id)
            )
        )
        .scalars()
        .all()
    )
    audits = [
        AuditBron(
            # De werker-auditregels (`log_action`) dragen hun soort in `action`, de API-regels in `event_type`.
            soort=(
                a.action
                if (a.resource or "").startswith(("outgoing", "receivable:"))
                else a.event_type
            )
            or "",
            resource=a.resource,
            tijdstip=a.timestamp,
            user_id=a.user_id,
            metadata=dict(a.event_metadata or {}),
        )
        for a in audit_rijen
    ]
    refs = {b.hitl_ticket_ref for b in berichten if b.hitl_ticket_ref}
    refs |= {
        str(a.metadata["ticket_ref"])
        for a in audits
        if a.soort == _SOORT_VOORGESTELD and isinstance(a.metadata.get("ticket_ref"), str)
    }
    ticket_rijen = []
    if refs:
        ticket_rijen = list(
            (
                await db.execute(
                    select(HITLTicket).where(
                        HITLTicket.tenant_id == tenant_id, HITLTicket.ticket_ref.in_(refs)
                    )
                )
            )
            .scalars()
            .all()
        )
    tickets = [
        TicketBron(t.ticket_ref, t.status, t.resolved_by, t.resolved_at, t.resolution_note)
        for t in ticket_rijen
    ]
    ids = {a.user_id for a in audits if a.user_id is not None}
    ids |= {t.resolved_by for t in tickets if t.resolved_by is not None}
    namen: dict[int, str] = {}
    if ids:
        resultaat = await db.execute(
            select(User.id, User.email).where(User.tenant_id == tenant_id, User.id.in_(ids))
        )
        namen = {gebruiker_id: email for gebruiker_id, email in resultaat.all()}
    return Bronnen(
        created_at=rij.created_at,
        status=rij.status,
        betaald_op=rij.betaald_op,
        audits=audits,
        tickets=tickets,
        berichten=[
            BerichtBron(
                b.id,
                b.kind,
                b.status,
                b.pogingen,
                b.foutreden,
                b.created_at,
                b.verzonden_op,
                b.hitl_ticket_ref,
            )
            for b in berichten
        ],
        namen=namen,
    )
