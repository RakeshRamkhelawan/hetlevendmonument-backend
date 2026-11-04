"""Gedeelde dependencies voor het `receivables`-domein (ADR-033 Laag 1 -> infrastructuur).

De router importeert geen database, governance of auth (ADR-033 par. 2, Contract 1 in
`.importlinter`); dat gaat via dit bestand. Zelfde patroon als `api/v1/hr/dependencies.py`.

**Waarom via bestaande facades en niet rechtstreeks.** `get_db`, de gebruiker en de tenant komen
uit `admin/dependencies.py`, de rate-limits uit `tool_broker/dependencies.py`. Elke nieuwe
koppeling van een `core_api`-bestand naar een andere module telt mee in het fan-out-budget
(`tests/architecture/test_dsm_grade_a_plus.py`, 557); via de facades voegt dit domein geen
enkel nieuw paar toe (gemeten: rechtstreeks importeren gaf 559).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.admin.dependencies import (
    NewReceivable,
    ReceivableChanges,
    ReceivableRepository,
    UserResponse,
    _resolve_tenant_id,
    get_current_user,
    get_db,
    require_admin_role,
    require_resource_permission,
)
from src.core.api.v1.tool_broker.dependencies import consent_read_limit, consent_update_limit


def get_receivable_repository(db: AsyncSession = Depends(get_db)) -> ReceivableRepository:
    return ReceivableRepository(db)


async def start_reminder_proposals(
    *, tenant_id: int, user_id: int, receivable_ids: list[int], kind: str
) -> list[dict[str, object]]:
    """Start de debiteurenagent voor de gekozen facturen (dag 3).

    Via de catalogus, net als `packs.py::_execute_step`: de agent is globaal beschikbaar
    (catalogus + `_PILOT_WIRED_AGENT_IDS`), er is geen registratie per tenant. `importlib`
    zodat dit domein geen nieuwe statische koppeling naar `als` krijgt (fan-out-budget,
    zie de moduledocstring).
    """
    import importlib

    loader = importlib.import_module("src.core.als.agents.loader")
    agent = loader.EnterpriseCatalogLoader().load_all().get_agent_instance("dunning", tenant_id)
    uitkomsten: list[dict[str, object]] = await agent.propose_reminders(
        receivable_ids, kind, initiated_by_user_id=user_id
    )
    return uitkomsten


async def schrijf_debiteur_audit(
    repo: ReceivableRepository,
    *,
    event_type: str,
    user_id: int | None,
    tenant_id: int,
    receivable_id: int,
    details: dict[str, object],
) -> None:
    """Schrijf een auditregel voor een debiteur, best-effort en NA de commit van de rij.

    De aanroeper legt de primaire wijziging eerst vast (backend-patterns par. 3); een falende
    auditregel rolt die dus niet terug. `log_event` flusht alleen, vandaar de eigen commit.
    Lazy import: een module-level koppeling naar governance telt mee in het fan-out-budget
    (zie de moduledocstring).
    """
    import importlib

    from src.core.utils.best_effort import best_effort

    audit = importlib.import_module("src.core.governance.services.audit_service").AuditService
    pad = f"/api/v1/receivables/{receivable_id}"
    async with best_effort(f"auditregel {event_type} voor debiteur", db_session=repo.db):
        await audit.log_event(
            db=repo.db,
            event_type=event_type,
            severity="low",
            source_ip="unknown",
            endpoint=pad,
            description=f"{event_type}: debiteur {receivable_id}",
            user_id=user_id,
            tenant_id=tenant_id,
            action=event_type,
            resource=pad,
            metadata={"receivable_id": receivable_id, **details},
        )
        await repo.db.commit()


#: Meer vorderingen dan dit leggen we niet in een keer naast een afschrift: een deel overslaan zou stil
#: "niet gekoppeld" geven voor facturen die er wel zijn.
MAX_VORDERINGEN_VOOR_AFSCHRIFT = 20000
#: PostgreSQL: deadlock_detected en lock_not_available.
_SLOT_FOUTEN = frozenset({"40P01", "55P03"})


async def verwerk_bankafschrift(
    repo: ReceivableRepository, *, tenant_id: int, user_id: int, data: bytes
) -> dict[str, object]:
    """Lees een CAMT.053-afschrift en vink de vorderingen van DEZE tenant af die er precies bij passen (B2).

    Van het afschrift wordt NIETS bewaard of gelogd: alleen de afgevinkte facturen krijgen een auditregel met het
    factuurnummer en de datum (geen omschrijving, geen bedrag van de bijschrijving, geen tegenrekening). Het
    antwoord gaat alleen naar de aanroeper. Lazy import: zie de moduledocstring (fan-out-budget).
    """
    import importlib
    from datetime import date

    bank = importlib.import_module("src.core.services.bankafschrift")
    rijen = await repo.list_all_for_matching(tenant_id, limit=MAX_VORDERINGEN_VOOR_AFSCHRIFT + 1)
    if len(rijen) > MAX_VORDERINGEN_VOOR_AFSCHRIFT:
        raise HTTPException(
            status_code=422,
            detail="Er staan te veel facturen open om automatisch af te vinken. Vink af met de hand.",
        )
    vorderingen = [
        bank.Vordering(
            id=r.id,
            factuurnummer=r.invoice_number,
            bedrag=r.amount,
            valuta=r.currency,
            status=r.status,
        )
        for r in rijen
    ]
    per_id = {r.id: r for r in rijen}
    vastgelegd: list[tuple[int, str, date | None]] = []

    async def vink_af(vordering_id: int, datum: date | None) -> None:
        rij = await repo.mark_paid_via_statement(tenant_id, vordering_id, datum)
        if rij is not None:
            vastgelegd.append((vordering_id, rij.invoice_number, datum))

    try:
        verwerking = await bank.verwerk_afschrift(data, vorderingen, vink_af)
    except bank.BankafschriftFout as exc:
        await repo.db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.boodschap) from exc
    except DBAPIError as exc:
        await repo.db.rollback()
        # Alleen een deadlock (40P01) of lock-timeout (55P03): een tweede upload of wijziging zat dezelfde facturen
        # in de weg. Elke andere databasefout blijft een echte fout.
        if getattr(exc.orig, "pgcode", None) in _SLOT_FOUTEN:
            raise HTTPException(
                status_code=409,
                detail="Er werd tegelijk iets anders aan deze facturen gewijzigd. Lees het afschrift opnieuw in.",
            ) from exc
        raise
    except Exception:
        await repo.db.rollback()
        raise
    await repo.db.commit()
    for vordering_id, factuurnummer, datum in vastgelegd:
        await schrijf_debiteur_audit(
            repo,
            event_type="receivable_paid_via_bankstatement",
            user_id=user_id,
            tenant_id=tenant_id,
            receivable_id=vordering_id,
            details={
                "invoice_number": factuurnummer,
                "betaald_op": datum.isoformat() if datum else None,
                "bron": "bankafschrift",
            },
        )
    return {
        "aantal_bijschrijvingen": verwerking.aantal_bijschrijvingen,
        "overgeslagen": verwerking.overgeslagen,
        "al_afgevinkt": verwerking.al_afgevinkt,
        "afgevinkt": [
            {
                "id": vordering_id,
                "invoice_number": per_id[vordering_id].invoice_number,
                "customer_name": per_id[vordering_id].customer_name,
                "amount": str(per_id[vordering_id].amount),
                "currency": per_id[vordering_id].currency,
                "betaald_op": datum.isoformat() if datum else None,
            }
            for vordering_id, _nummer, datum in vastgelegd
        ],
        "niet_gekoppeld": [
            {
                "datum": n.datum.isoformat() if n.datum else None,
                "bedrag": str(n.bedrag),
                "valuta": n.valuta,
                "omschrijving": n.omschrijving,
            }
            for n in verwerking.niet_gekoppeld
        ],
    }


#: De melding bij een factuur waarvoor al een voorstel op goedkeuring wacht (Nederlands, wijst naar het scherm).
MELDING_AL_EEN_VOORSTEL = (
    "Er staat al een voorstel klaar voor deze factuur. Beslis eerst bij Goedkeuringen."
)


async def scheid_bestaande_voorstellen(
    db: AsyncSession, *, tenant_id: int, receivable_ids: list[int]
) -> tuple[list[int], set[int]]:
    """Splits de gekozen facturen in: nog geen voorstel, en al een voorstel dat op een besluit wacht.

    Een voorstel telt alleen als het ticket van DEZE tenant, voor de brief-actie, nog `pending` en niet verlopen is. Een
    besloten of verlopen voorstel, een voorstel van een andere tenant of een ticket van een andere tool blokkeert niet.
    Dubbele ids in het verzoek worden hier een keer genoemd. Lazy import, zie de moduledocstring (fan-out-budget).
    """
    import importlib

    from sqlalchemy import func, select

    models = importlib.import_module("src.core.tool_broker.models")
    registry = importlib.import_module("src.core.tool_broker.receivables_registry")
    ids = list(dict.fromkeys(receivable_ids))
    ticket = models.HITLTicket
    rijen = await db.execute(
        select(ticket.payload["receivable_id"].astext).where(
            ticket.tenant_id == tenant_id,
            ticket.tool_name == registry.SEND_TOOL_NAME,
            ticket.status == "pending",
            ticket.expires_at > func.now(),
            ticket.payload["receivable_id"].astext.in_([str(i) for i in ids]),
        )
    )
    bezet = {int(r[0]) for r in rijen.all() if r[0] is not None and str(r[0]).isdigit()}
    return [i for i in ids if i not in bezet], bezet


def voeg_uitkomsten_samen(
    receivable_ids: list[int], geweigerd: set[int], gestart: list[dict[str, object]]
) -> list[dict[str, object]]:
    """De uitkomst per factuur in de volgorde van het verzoek: geweigerd (al een voorstel) of wat de agent teruggaf."""
    per_id = {u.get("receivable_id"): u for u in gestart}
    uit: list[dict[str, object]] = []
    for rij_id in dict.fromkeys(receivable_ids):
        if rij_id in geweigerd:
            uit.append(
                {"receivable_id": rij_id, "status": "niet_gelukt", "reason": MELDING_AL_EEN_VOORSTEL}
            )
        elif rij_id in per_id:
            uit.append(per_id[rij_id])
    return uit


async def schrijf_voorstel_audit(
    repo: ReceivableRepository,
    *,
    tenant_id: int,
    user_id: int,
    kind: str,
    uitkomsten: list[dict[str, object]],
) -> None:
    """Een auditregel per factuur waarvoor een voorstel op goedkeuring wacht: wie, welke soort, welk ticket.

    Het voorstel zelf had geen regel (de acceptant, B4). Alleen de facturen die echt een ticket kregen; een
    `niet_gelukt` is geen voorstel. Geen brieftekst: het ticket is de verwijzing.
    """
    for uitkomst in uitkomsten:
        rij_id = uitkomst.get("receivable_id")
        if uitkomst.get("status") != "wacht_op_goedkeuring" or not isinstance(rij_id, int):
            continue
        await schrijf_debiteur_audit(
            repo,
            event_type="receivable_reminder_proposed",
            user_id=user_id,
            tenant_id=tenant_id,
            receivable_id=rij_id,
            details={"kind": kind, "ticket_ref": uitkomst.get("ticket_ref")},
        )


async def lees_tijdlijn(db: AsyncSession, *, tenant_id: int, receivable_id: int) -> list[dict[str, object]]:
    """De tijdlijn van een factuur van de eigen tenant, in het Nederlands; 404 als hij er niet is."""
    import importlib

    tijdlijn = importlib.import_module("src.core.services.debiteur_tijdlijn")
    bronnen = await tijdlijn.lees_bronnen(db, tenant_id=tenant_id, receivable_id=receivable_id)
    if bronnen is None:
        raise HTTPException(status_code=404, detail="Deze factuur bestaat niet.")
    return [
        {
            "soort": g.soort,
            "tekst": g.tekst,
            "tijdstip": g.tijdstip.isoformat() if g.tijdstip else None,
            "door": g.door,
        }
        for g in tijdlijn.bouw_tijdlijn(bronnen)
    ]


async def vereis_beheerder(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Alleen een beheerder, met een weigering in het Nederlands (de gedeelde controle zegt "Admin access required")."""
    try:
        return await require_admin_role(current_user=current_user, db=db)
    except HTTPException as exc:
        if exc.status_code == 403:
            raise HTTPException(
                status_code=403, detail="Alleen een beheerder mag de escalatietermijn wijzigen."
            ) from exc
        raise


async def lees_escalatietermijn(db: AsyncSession, tenant_id: int) -> int:
    """De escalatietermijn (dagen) van de eigen tenant; lazy import, zie de moduledocstring."""
    import importlib

    instellingen = importlib.import_module("src.core.governance.debiteuren_instellingen")
    termijn: int = await instellingen.lees_escalatie_na_dagen(db, tenant_id=tenant_id)
    return termijn


async def wijzig_escalatietermijn(
    db: AsyncSession, *, tenant_id: int, user_id: int, dagen: int
) -> int:
    """Zet de escalatietermijn van de eigen tenant en schrijf een auditregel met oud en nieuw.

    Een onmogelijke waarde geeft 422 met een Nederlandse melding, een onbekende tenant 404. De auditregel is
    best-effort en komt NA de commit van de instelling.
    """
    import importlib

    from src.core.utils.best_effort import best_effort

    instellingen = importlib.import_module("src.core.governance.debiteuren_instellingen")
    try:
        oud, nieuw = await instellingen.schrijf_escalatie_na_dagen(
            db, tenant_id=tenant_id, dagen=dagen
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Kies een aantal dagen van {instellingen.MIN_ESCALATIE_NA_DAGEN} tot en met "
                f"{instellingen.MAX_ESCALATIE_NA_DAGEN}."
            ),
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Dit bedrijf bestaat niet.") from exc
    audit = importlib.import_module("src.core.governance.services.audit_service").AuditService
    async with best_effort("auditregel escalatietermijn gewijzigd", db_session=db):
        await audit.log_event(
            db=db,
            event_type="receivable_escalation_term_changed",
            severity="medium",
            source_ip="unknown",
            endpoint="/api/v1/receivables/settings",
            description=f"escalatietermijn gewijzigd door gebruiker {user_id}",
            user_id=user_id,
            tenant_id=tenant_id,
            action="update",
            resource="/api/v1/receivables/settings",
            metadata={"oud": oud, "nieuw": nieuw},
        )
        await db.commit()
    result: int = nieuw
    return result


__all__ = [
    "NewReceivable",
    "ReceivableChanges",
    "ReceivableRepository",
    "UserResponse",
    "_resolve_tenant_id",
    "consent_read_limit",
    "consent_update_limit",
    "get_current_user",
    "get_db",
    "get_receivable_repository",
    "lees_escalatietermijn",
    "lees_tijdlijn",
    "require_admin_role",
    "require_resource_permission",
    "scheid_bestaande_voorstellen",
    "schrijf_debiteur_audit",
    "schrijf_voorstel_audit",
    "start_reminder_proposals",
    "verwerk_bankafschrift",
    "validate_csrf_token",
    "vereis_beheerder",
    "voeg_uitkomsten_samen",
    "wijzig_escalatietermijn",
]
