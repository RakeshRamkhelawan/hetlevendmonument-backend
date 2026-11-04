"""
HITLTicketRepository -- DB-backed storage for Human-in-the-Loop tickets.

All queries filter on tenant_id per CLAUDE.md repository pattern.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Collection, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import cast, event, func, literal, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.core.tool_broker.models import HITLTicket

logger = logging.getLogger(__name__)

_SLA_HOURS = 4  # HIGH risk tickets expire after 4 hours

#: Hoe lang een GEGEVEN goedkeuring verzilverbaar blijft (ADR-036 OP-83).
#:
#: `approve` eist dat het ticket nog niet verlopen is, maar `redeem` kende geen tijdsgrens: een
#: actie die maanden geleden is goedgekeurd bleef uitvoerbaar tot de retentie de rij verwijdert.
#: Menselijk toezicht gaat over een beslissing op een MOMENT, met de context van dat moment.
#:
#: Ruimer dan de SLA op het openstaande ticket (4 uur): daar wacht een mens, hier moet een
#: geplande uitvoering nog kunnen aflopen. Een etmaal is genoeg voor een normale keten en kort
#: genoeg dat de context nog klopt.
_APPROVAL_VALID_HOURS = 24

#: De payloadsleutels die een beslissing OVERLEVEN (ADR-036 OP-47).
#:
#: `payload` is `{**action_params, "_decision_id", "_reason", "_requested_by", "_requested_at"}`
#: (zie `create_hitl_request`), plus op het `/hitl/request`-pad `_agent_id` en `_task_id`. De
#: metadata die bewaard moet blijven zit dus in DEZELFDE dict als de modeloutput -- wholesale
#: leegmaken gooit het besluit weg.
#:
#: Deze drie zijn de ENIGE sleutels die `create_hitl_request` zelf zet, en wel NA de spreiding van
#: `action_params`. Alles wat daarvoor komt is rauwe modeluitvoer.
#:
#: `_agent_id` en `_task_id` stonden hier eerder bij, met als reden dat ze "uit de request-body van
#: de aanroeper" zouden komen. Dat gold voor `POST /hitl/request` -- en die route is niet gemount.
#: Op het live pad (`copilot/service.py` -> `create_hitl_request`) zet niets ze, dus wat het model
#: onder die namen schreef bleef permanent staan en werd getoond op /hitl/pending, /hitl/audit en
#: over de tenant-brede websocket. Twee blinde reviews vonden dat onafhankelijk (ADR-036 OP-65).
#: Het is dezelfde fout als de `ALWAYS_PUBLISHABLE`-naamlijst uit ronde 2: een naam kan niet
#: onderscheiden WIE een sleutel schreef, wiring wel.
#:
#: `_reason` staat er met opzet NIET bij: dat is `decision.explanation_for_user` en dus modeltekst.
#:
#: `_executing_identity` (ADR-036 OP-163) staat er BEWUST ook niet bij, en dat is een bewuste,
#: nog openstaande afweging en geen omissie: hij wordt gelezen VOOR de wipe (`hitl_router.py`
#: leest hem uit `ticket.payload` voordat `approve()` de payload vervangt), dus de
#: functionele behoefte -- dezelfde identiteit toetsen bij aanmaken als uitvoeren -- is voldaan
#: zonder dat hij hoeft te overleven. Zou hij hier bij komen, dan verschijnt hij ook in
#: `hitl_store._ticket_to_dict()` en de `_AUDIT_FIELDS`-toelaatlijst in `hitl_router.py` zou
#: moeten meegroeien voor een AI-Act-art.-12(2)-achtig "wie voerde dit uit"-spoor na resolutie --
#: dat raakt de audit-oppervlakte en het API-contract van /hitl/audit, en is een eigen
#: beslissing, geen 1-bestand-wijziging. Genoteerd voor een latere sprint, niet stilzwijgend
#: vergeten: zie de Dag 2-final-approver-brief van ADR-036 OP-163.
_BLIJFT: tuple[str, ...] = (
    "_decision_id",
    "_requested_by",
    "_requested_at",
)

#: Onder deze sleutel komt de keyed digest van wat er is weggegooid, zodat narekenbaar blijft WAT
#: er is goedgekeurd zonder het persoonsgegeven te bewaren.
_DIGEST_KEY = "_redacted_payload"

#: Onder deze sleutel staat de binding die een goedkeuring aan EEN tool met EEN parameterset
#: koppelt (ADR-036 OP-63). Hij overleeft de opruiming met opzet: zonder hem kan de poort bij
#: uitvoering niet vaststellen dat de aangeboden aanroep dezelfde is als de goedgekeurde.
_BINDING_KEY = "_approval_binding"

#: De DEFAULT-identiteit die een goedgekeurde actie uitvoert (ADR-036 OP-90).
#:
#: `copilot/service.py` voert uit met `agent_id="copilot"`, en `hitl_router` doet dat sinds
#: OP-89 ook bij goedkeuren -- vandaar de default. Sinds ADR-036 OP-163 is dit niet langer de
#: ENIGE aanroeper: het ALS-skillpad (`specialist_base.py::_council_rejection`) roept aan met
#: zijn eigen `agent_id` (bv. "skillsgaptraining"), want `copilot` en de piloot-skill hebben in
#: `config/tool_permissions.yml` grotendeels afwijkende toolprofielen (ze delen alleen
#: NIETS sinds 2026-09-21; `send_notification` stond in beide en is uit het piloot-manifest
#: gehaald omdat er geen broker-tool voor bestaat) -- de permissiecheck zou anders altijd
#: falen voor een piloot-specifieke
#: tool, ongeacht wat er wordt goedgekeurd.
#:
#: De identiteit die `create_hitl_request` bij het AANMAKEN toetst, wordt in de payload bewaard
#: (`_executing_identity`) en is dezelfde die `hitl_router.py` bij VERZILVEREN gebruikt -- anders
#: vraagt de controle iets anders dan wat er gebeurt (de oorspronkelijke OP-90-eis, nu generiek
#: gemaakt in plaats van hardcoded).
_UITVOERENDE_IDENTITEIT = "copilot"



def redacted_payload_digest(
    payload: dict[str, object] | None, tool_name: str | None, tenant_id: int
) -> dict[str, object] | None:
    """Een keyed digest van wat er bij een beslissing wordt weggegooid (ADR-036 OP-47).

    Waarom dit bestaat: na het opruimen is er anders nergens meer bewijs van WAT er is goedgekeurd.
    `notes` en `reason` uit de API worden namelijk nooit opgeslagen (`HITLTicket` heeft die kolommen
    niet) en de ADR-019-auditketen is op dit pad niet gewired. Wat overblijft zou zijn: "gebruiker
    42 heeft om 14:03 iets goedgekeurd".

    Een keyed digest houdt het log forensisch narekenbaar door wie de waarde kent, en houdt
    herhaling zichtbaar, zonder het persoonsgegeven te bewaren -- dezelfde afweging als OP-27.

    Geeft `None` als er niets weg te gooien valt; dan blijft de payload een kale besluitprojectie.
    """
    from src.core.tool_broker.redaction import redact_for_publication

    discarded = {k: v for k, v in (payload or {}).items() if k not in _BLIJFT}
    if not discarded:
        return None
    return redact_for_publication(
        tool_name or "unknown",
        discarded,
        tenant_id=tenant_id,
        broker_keys=frozenset(),
    )


#: Sleutel in `Session.info` voor de tickets die deze transactie aanmaakt en nog niet gemeld zijn.
_NOG_TE_MELDEN = "hitl_nieuwe_tickets"

#: Lopende meldtaken; een losse taak zonder verwijzing kan halverwege door de GC worden opgeruimd.
_LOPENDE_MELDINGEN: set[asyncio.Task[None]] = set()


def _meld_na_commit(db: AsyncSession, ticket_ref: str, tenant_id: int) -> None:
    """Meld een nieuw ticket live aan de eigen tenant, zodra de transactie is vastgelegd.

    **Waarom hier, bij het aanmaken (meetlat-scenario 5, 2026-10-05).** De melding zat alleen in
    `tool_broker/router.py` (`POST /hitl/request`). Een ticket uit het agentpad -- de
    debiteurenagent via `create_hitl_request`, de ToolBroker via `HITLStore.create_ticket` --
    kwam daardoor niet live binnen. Elk pad maakt zijn ticket via `create()`, dus een melding
    hier geldt voor elk pad, ook een volgend.

    **Waarom pas NA de commit.** Bij `create()` is het ticket alleen geflusht. Een melding op dat
    moment laat de client `/hitl/pending` ophalen voordat het ticket zichtbaar is, en meldt een
    ticket dat bij een rollback nooit bestaan heeft. Een rollback wist daarom de wachtrij.

    **Nooit ten koste van het aanmaken.** Lukt het aanhaken niet, dan blijft het bij een
    waarschuwing; de melding zelf loopt in `best_effort`.
    """
    try:
        sync_session = db.sync_session
        # Een keer per sessie aanhaken. Niet afhaken in de luisteraar zelf: dat wijzigt de lijst
        # luisteraars terwijl SQLAlchemy erover loopt ("deque mutated during iteration").
        if not event.contains(sync_session, "after_commit", _na_commit):
            event.listen(sync_session, "after_commit", _na_commit)
            event.listen(sync_session, "after_rollback", _na_rollback)
        sync_session.info.setdefault(_NOG_TE_MELDEN, []).append((ticket_ref, tenant_id))
    except (SQLAlchemyError, AttributeError, TypeError) as exc:
        logger.warning(
            "hitl_repository.live_melding_niet_aangehaakt: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )


def _na_rollback(session: Session) -> None:
    session.info.pop(_NOG_TE_MELDEN, None)


def _na_commit(session: Session) -> None:
    wachtrij = session.info.pop(_NOG_TE_MELDEN, None)
    if not isinstance(wachtrij, list) or not wachtrij:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("hitl_repository.live_melding_zonder_event_loop", extra={"aantal": len(wachtrij)})
        return
    for ticket_ref, tenant_id in wachtrij:
        taak = loop.create_task(_meld(ticket_ref, tenant_id))
        _LOPENDE_MELDINGEN.add(taak)
        taak.add_done_callback(_LOPENDE_MELDINGEN.discard)


async def _meld(ticket_ref: str, tenant_id: int) -> None:
    from src.core.tool_broker.hitl_notifier import broadcast_new_ticket
    from src.core.utils.best_effort import best_effort

    async with best_effort("live melding nieuw HITL-ticket"):
        await broadcast_new_ticket(ticket_ref, tenant_id)


class HITLTicketRepository:
    """Tenant-isolated repository for HITL tickets."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        ticket_ref: str,
        tenant_id: int,
        tool_name: str,
        payload: dict[str, object],
        risk_level: str,
    ) -> HITLTicket:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=_SLA_HOURS)
        ticket = HITLTicket(
            ticket_ref=ticket_ref,
            tenant_id=tenant_id,
            status="pending",
            tool_name=tool_name,
            payload=payload,
            risk_level=risk_level,
            expires_at=expires_at,
        )
        self._db.add(ticket)
        await self._db.flush()
        _meld_na_commit(self._db, ticket_ref, tenant_id)
        logger.info(
            "hitl_repository.created",
            extra={"ticket_ref": ticket_ref, "tenant_id": tenant_id, "tool_name": tool_name},
        )
        return ticket

    async def get(self, ticket_ref: str, tenant_id: int) -> HITLTicket | None:
        """Fetch a ticket by ref, enforcing tenant isolation."""
        result = await self._db.execute(
            select(HITLTicket).where(
                HITLTicket.ticket_ref == ticket_ref,
                HITLTicket.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_unchecked(self, ticket_ref: str) -> HITLTicket | None:
        """Fetch by ref without tenant check -- only for internal validation in service layer."""
        result = await self._db.execute(
            select(HITLTicket).where(HITLTicket.ticket_ref == ticket_ref)
        )
        return result.scalar_one_or_none()

    async def get_by_tenant(
        self,
        tenant_id: int,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        tool_names: Collection[str] | None = None,
        statuses: Collection[str] | None = None,
        nieuwste_besluit_eerst: bool = False,
    ) -> list[HITLTicket]:
        """Een pagina tickets, gefilterd en gesorteerd DOOR DE DATABASE (ADR-036 OP-68).

        `statuses`: alleen tickets met een van deze statussen (naast of in plaats van `status`); een lege collectie geeft
        niets terug. `nieuwste_besluit_eerst`: sorteer op het moment van besluiten, nieuwste eerst (voor de lijst van
        besloten tickets); anders de wachtrijvolgorde hieronder.

        `tool_names`: alleen tickets van deze tools (ADR-039: een beslisser ziet alleen wat hij mag
        beslissen); een lege collectie geeft niets terug.

        De aanroepers haalden hier eerder 2000 rijen op om er in Python op status te filteren, te
        hersorteren en te pagineren. Gevolg: `offset` boven 2000 gaf stil een lege pagina terug
        terwijl er wel data was, en `total` was afgetopt op 2000.

        Oplopend op `created_at`, want dat is de volgorde waarin een goedkeurder een wachtrij
        afwerkt: het oudste verzoek eerst.
        """
        query = select(HITLTicket).where(HITLTicket.tenant_id == tenant_id)
        if status is not None:
            query = query.where(HITLTicket.status == status)
        if statuses is not None:
            query = query.where(HITLTicket.status.in_(list(statuses)))
        if tool_names is not None:
            query = query.where(HITLTicket.tool_name.in_(list(tool_names)))
        volgorde = (
            (HITLTicket.resolved_at.desc().nulls_last(), HITLTicket.id.desc())
            if nieuwste_besluit_eerst
            else (HITLTicket.created_at.asc(),)
        )
        result = await self._db.execute(query.order_by(*volgorde).limit(limit).offset(offset))
        return list(result.scalars().all())

    async def count_by_tenant(
        self,
        tenant_id: int,
        status: str | None = None,
        tool_names: Collection[str] | None = None,
        statuses: Collection[str] | None = None,
    ) -> int:
        """Het ECHTE aantal, niet de lengte van de opgehaalde pagina.

        `total` werd eerder berekend als `len(tickets)` op een lijst die op 2000 was afgetopt. Een
        client die daarop pagineert stopt dus bij 2000, ook als er een miljoen rijen zijn.
        """
        query = select(func.count()).select_from(HITLTicket).where(HITLTicket.tenant_id == tenant_id)
        if status is not None:
            query = query.where(HITLTicket.status == status)
        if statuses is not None:
            query = query.where(HITLTicket.status.in_(list(statuses)))
        if tool_names is not None:
            query = query.where(HITLTicket.tool_name.in_(list(tool_names)))
        result = await self._db.execute(query)
        return int(result.scalar_one())

    def _resolution_payload(
        self, redacted: dict[str, object] | None, binding: str | None = None
    ) -> Any:  # TODO(TYPE): replace Any with concrete type -- samengestelde JSONB-expressie
        """De payload die na een beslissing overblijft: het BESLUIT plus een digest van de rest.

        **Waarom hier iets weg moet (ADR-036 OP-47).** `hitl_tickets.payload` is het enige LIVE pad
        waar door een taalmodel geschreven tekst onbewerkt en onuitwisbaar op schijf komt:
        `copilot/service.py:528` geeft `dict(proposal.action_params)` ongefilterd door. Zolang het
        ticket PENDING is moet dat leesbaar blijven -- wie goedkeurt moet zien wat hij goedkeurt
        (AI Act art. 14). Daarna niet meer. Besluit Rakesh 2026-08-05: dan blijft alleen het besluit.

        **Wat blijft, en waarom precies dit.** `_BLIJFT` bevat de drie sleutels die
        `create_hitl_request` zelf zet, NA de spreiding van `action_params`: `_decision_id`,
        `_requested_by` en `_requested_at`. Dat is het besluit.

        Er stonden er eerder vijf in. `_agent_id` en `_task_id` zijn eruit gehaald (ADR-036 OP-65):
        die werden vertrouwd om hun naam, terwijl niets op het live pad ze schrijft. `agent_id` valt
        na een beslissing dus terug op `"unknown"` en `task_id` op `None` -- dat is het juiste
        gedrag, want een waarde die van het model kwam is geen herkomstbewijs.

        `_reason` gaat WEL weg: dat is `decision.explanation_for_user` en dus zelf modeltekst.

        **Waarom een digest en niet alleen wissen.** Zonder digest is er na de beslissing nergens
        meer bewijs van WAT er is goedgekeurd -- `notes` en `reason` uit de API worden namelijk
        nooit opgeslagen (`HITLTicket` heeft die kolommen niet), en de ADR-019-auditketen is op dit
        pad niet gewired. Dan blijft over: "gebruiker 42 heeft om 14:03 iets goedgekeurd". Met een
        keyed digest via `redact_for_publication` blijft het log forensisch narekenbaar door wie de
        waarde kent, zonder het persoonsgegeven te bewaren -- dezelfde afweging als OP-27.

        **Waarom de digest wordt MEEGEGEVEN en niet hier opgehaald.** Een digest berekenen vraagt de
        payload, en die heeft de aanroeper al: `hitl_router` laadt het ticket met `repo.get()` om de
        status te controleren voordat hij `approve()` aanroept. Hier opnieuw lezen zou een tweede
        query per beslissing kosten en elke bestaande test dwingen een extra query te modelleren.
        `redacted_payload_digest()` hieronder maakt de berekening herbruikbaar, en
        `tests/unit/api/test_tool_broker_hitl_route_is_served.py` borgt dat de router hem meegeeft.

        Zonder digest (parameter `None`) blijft alleen het besluit over. Dat is het juiste gedrag
        voor `cleanup_expired`: een verlopen ticket is nooit beoordeeld, dus er is geen beslissing
        waarvan de inhoud navolgbaar hoeft te zijn.
        """
        kept: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for key in _BLIJFT:
            kept.extend([literal(key), HITLTicket.payload[key]])
        rebuilt: Any = func.jsonb_strip_nulls(func.jsonb_build_object(*kept))  # TODO(TYPE): replace Any with concrete type

        if binding is not None:
            # De binding blijft bewust staan: zonder hem kan `redeem` bij uitvoering niet
            # vaststellen dat de aangeboden aanroep dezelfde is als de goedgekeurde (OP-63).
            rebuilt = func.jsonb_build_object(literal(_BINDING_KEY), literal(binding)).op("||")(
                rebuilt
            )

        if not redacted:
            return rebuilt

        # `jsonb_strip_nulls` staat hier NIET omheen, en dat is een correctie. Die functie werkt
        # recursief: een argument met waarde `None` in de digest verdween er stil uit, terwijl
        # `redact_for_publication` `None` juist bewaart voor beoordeelde parameters. Dan klopt het
        # antwoord op "hoeveel argumenten had de aanroep" niet meer -- precies wat de digest moet
        # dragen. `rebuilt` is al gestript; de digest hoort dat niet te zijn.
        return func.jsonb_build_object(literal(_DIGEST_KEY), cast(redacted, JSONB)).op("||")(
            rebuilt
        )

    async def approve(
        self,
        ticket_ref: str,
        tenant_id: int,
        user_id: int,
        redacted_payload: dict[str, object] | None = None,
        binding: str | None = None,
        note: str | None = None,
    ) -> bool:
        """Keur een openstaand ticket goed dat nog niet is verlopen. True als er iets is bijgewerkt.

        **Waarom `expires_at` hier in de WHERE staat (ADR-036 OP-64).** De SLA van 4 uur werd
        uitsluitend gehandhaafd door `cleanup_expired`, en die actor werd door geen enkel
        gedeployed proces gestart (gemeten 2026-08-06: `start_scheduler` had nul aanroepers buiten
        zijn eigen `__main__`, en geen compose-opstelling draaide een scheduler). Een ticket van een
        jaar oud was daardoor nog steeds goed te keuren. Een vervaltermijn die alleen bestaat als een
        achtergrondtaak toevallig draait, is geen vervaltermijn.

        **Bijgewerkt 2026-10-27 (crediteuren nazorg, taak 0): dat is niet meer zo, en de filter blijft nodig.** De scheduler staat nu
        wel in de uitrol: `docker-compose.yml:287-293`, `docker-compose.prod.yml:198-201`, `docker-compose.dev.yml:138` (entrypoint
        `python -m src.workers.scheduler`), en in `cd-production.yml` (`scheduler-prod`) en `cd-staging.yml` (`scheduler-staging`);
        de job `hitl_ticket_cleanup` loopt elk uur op :15 (`scheduler.py`). Gemeten met
        `grep -rn scheduler docker-compose*.yml .github/workflows/*.yml`. NIET gemeten: of die containers NU draaien. Tot een uur
        kan een ticket dus voorbij zijn termijn nog `pending` zijn; daarom blijft `expires_at` hier in de WHERE staan en telt een ticket
        bij het LEZEN al als verlopen (`hitl_store._ticket_to_dict`).

        `reject` filtert bewust NIET op verval: een verlopen aanvraag moet afgewezen kunnen worden,
        anders blijft hij `pending` met zijn inhoud erin en is er geen weg om hem op te ruimen.
        """
        now = datetime.now(timezone.utc)
        resolution_payload = self._resolution_payload(redacted_payload, binding)
        result = await self._db.execute(
            update(HITLTicket)
            .where(
                HITLTicket.ticket_ref == ticket_ref,
                HITLTicket.tenant_id == tenant_id,
                HITLTicket.status == "pending",
                HITLTicket.expires_at > now,
            )
            .values(
                status="approved",
                resolved_at=now,
                resolved_by=user_id,
                payload=resolution_payload,
                resolution_note=note,
            )
        )
        # SQLAlchemy async stubs type execute() as Result[Any] even for DML.
        # CursorResult.rowcount is valid at runtime -- stubs gap, not a code bug.
        updated: bool = bool(result.rowcount > 0)  # type: ignore[attr-defined]
        if updated:
            logger.info(
                "hitl_repository.approved",
                extra={"ticket_ref": ticket_ref, "tenant_id": tenant_id, "user_id": user_id},
            )
        return updated

    async def redeem(
        self,
        ticket_ref: str,
        *,
        tenant_id: int,
        tool_name: str,
        payload: Mapping[str, object],
    ) -> bool:
        """Verzilver een goedkeuring voor precies EEN aanroep. True als het mocht (ADR-036 OP-63).

        **Wat hiervoor stond.** De poort in `service.py` las de status van het ticket en toetste
        `status == "approved"`. Verder niets. Er was geen vergelijking met de tool die werd
        uitgevoerd, geen vergelijking van de parameters, en de status bleef daarna op `approved`
        staan. `ToolRiskClassifier` zet onbekende tools standaard op HIGH, dus dit gold voor elke
        niet-geregistreerde tool. Wie een onschuldige HIGH-actie liet goedkeuren en de
        ticketverwijzing onthield, had een permanente volmacht voor de hele tenant.

        **Waarom alles in EEN statement staat.** Lezen, controleren en dan bijwerken laat een gat
        tussen de controle en de mutatie: twee gelijktijdige aanroepen lezen allebei `approved` en
        voeren allebei uit. Door de vier voorwaarden in de WHERE te zetten en op `rowcount` te
        oordelen, beslist de database. Nul rijen betekent geweigerd -- en dat is de veilige uitkomst
        bij elke twijfel: verkeerde tool, andere parameters, al verbruikt, of niet goedgekeurd.

        **Waarom de status naar `consumed` en niet naar `approved` blijft.** Een goedkeuring is een
        eenmalige handeling van een mens. `status` is `String(32)` zonder CHECK-constraint, dus deze
        waarde vraagt geen migratie.
        """
        from src.core.tool_broker.redaction import approval_binding

        binding = approval_binding(tool_name, payload, tenant_id=tenant_id)
        result = await self._db.execute(
            update(HITLTicket)
            .where(
                HITLTicket.ticket_ref == ticket_ref,
                HITLTicket.tenant_id == tenant_id,
                HITLTicket.status == "approved",
                HITLTicket.tool_name == tool_name,
                HITLTicket.payload[_BINDING_KEY].astext == binding,
                HITLTicket.resolved_at > datetime.now(timezone.utc) - timedelta(
                    hours=_APPROVAL_VALID_HOURS
                ),
            )
            .values(status="consumed")
        )
        redeemed: bool = bool(result.rowcount > 0)  # type: ignore[attr-defined]  # SQLAlchemy async stubs gap
        if not redeemed:
            logger.warning(
                "hitl_repository.redeem_denied",
                extra={
                    "ticket_ref": ticket_ref,
                    "tenant_id": tenant_id,
                    "tool_name": tool_name,
                },
            )
        return redeemed

    async def reject(
        self,
        ticket_ref: str,
        tenant_id: int,
        user_id: int,
        redacted_payload: dict[str, object] | None = None,
        note: str | None = None,
    ) -> bool:
        """Wijs een openstaand ticket af. True als er iets is bijgewerkt.

        `note` is hier de door de mens opgegeven REDEN, en die is in het schema verplicht
        (`min_length=10`). Hij werd tot 2026-08-06 gevalideerd en weggegooid (ADR-036 OP-69).
        """
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            update(HITLTicket)
            .where(
                HITLTicket.ticket_ref == ticket_ref,
                HITLTicket.tenant_id == tenant_id,
                HITLTicket.status == "pending",
            )
            .values(
                status="rejected",
                resolved_at=now,
                resolved_by=user_id,
                payload=self._resolution_payload(redacted_payload),
                resolution_note=note,
            )
        )
        updated: bool = bool(result.rowcount > 0)  # type: ignore[attr-defined]  # SQLAlchemy async stubs gap
        if updated:
            logger.info(
                "hitl_repository.rejected",
                extra={"ticket_ref": ticket_ref, "tenant_id": tenant_id, "user_id": user_id},
            )
        return updated

    async def cleanup_expired(self, tenant_id: int) -> int:
        """Mark past-SLA pending tickets as expired for a specific tenant.

        Returns the number of tickets updated. ADR-005: tenant_id filter is mandatory.
        Called by the cleanup_expired_hitl_tickets actor which loops over all tenants
        inside a TenantFilterBypass context.
        """
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            update(HITLTicket)
            .where(
                HITLTicket.tenant_id == tenant_id,
                HITLTicket.status == "pending",
                HITLTicket.expires_at < now,
            )
            .values(
                status="expired",
                resolved_at=now,
                # Geen digest: een verlopen ticket is nooit door een mens bekeken, dus er is
                # geen goedkeuring waarvan de inhoud navolgbaar hoeft te zijn. Alleen het
                # besluit blijft staan (ADR-036 OP-47).
                payload=self._resolution_payload(None),
            )
        )
        count: int = result.rowcount  # type: ignore[attr-defined]  # SQLAlchemy async stubs gap
        if count:
            logger.info(
                "hitl_repository.cleanup_expired",
                extra={"count": count, "tenant_id": tenant_id},
            )
        return count

    async def create_hitl_request(
        self,
        *,
        tenant_id: int,
        user_id: int,
        decision_id: str,
        reason: str,
        action_type: str,
        action_params: dict[str, object],
        executing_identity: str = _UITVOERENDE_IDENTITEIT,
        requester_kind: Literal["user", "agent"] = "user",
    ) -> str:
        """Maak een HITL-ticket uit een HITL_REQUIRED-verdict van de raad. Geeft de ticketref.

        **`requester_kind` (ADR-039, Agent2Agent).** `agent` als een agent het verzoek deed in
        plaats van een mens; dan mag de aanvrager het ticket nooit zelf beslissen
        (`hitl_router._refuse_self_approval`). De waarde wordt NA de modelparameters gezet, net
        als `_requested_by`, zodat een model hem niet kan kiezen. Vandaag geeft geen enkele
        aanroeper `agent` mee; de regel staat klaar voor het eerste agent-tot-agentpad.

        **Weigert een ticket dat toch nooit uitgevoerd kan worden (ADR-036 OP-90).** Gemeten met
        `ToolPermissionManager`: de identiteit die deze acties uitvoert (default `copilot`) mag wel
        `create_task` en `delete_task`, maar NIET `local__send_email` en NIET `query_hr_database`.
        Zonder deze controle vraag je een mens om goedkeuring voor iets dat daarna op de
        permissiecheck stukloopt -- de verkeerde volgorde: je hoort niemand te laten beslissen over
        iets dat sowieso niet kan.

        Dezelfde laag-2-gedachte als OP-78: weiger bij de grens, luid, in plaats van stil een
        doodlopend spoor aan te maken. Hergebruikt de bestaande `is_tool_allowed`, geen tweede lijst.

        **`executing_identity` (ADR-036 OP-163).** Wie deze permissiecheck moet doorstaan is NIET
        altijd `copilot`: het ALS-skillpad roept aan met zijn eigen `agent_id` (bv.
        "skillsgaptraining"), en dat profiel heeft in `config/tool_permissions.yml` een
        grotendeels afwijkende toolset van `copilot` (sinds 2026-09-21 delen ze NIETS meer:
        `send_notification` stond in beide en is uit het piloot-manifest gehaald).
        Zonder deze parameter zou elk ticket voor een piloot-specifieke tool (bv.
        `query_hr_database`, uitsluitend bij de piloot) hier onvoorwaardelijk op de
        permissiecheck stuklopen, ook al mag de piloot de tool wel degelijk
        uitvoeren. De waarde wordt in de payload bewaard (`_executing_identity`) zodat
        `hitl_router.py` bij VERZILVEREN dezelfde identiteit gebruikt als hier is getoetst --
        anders vraagt de controle bij aanmaken iets anders dan wat er bij uitvoeren gebeurt.
        """
        from src.core.tool_broker.permission_manager import ToolPermissionManager
        from src.core.tool_broker.service import is_known_tool

        tool = action_type or "unknown"
        if not is_known_tool(tool):
            raise ValueError(
                f"Geen uitvoerder voor tool {tool!r}; een goedkeuringsticket hiervoor zou nooit "
                "uitgevoerd kunnen worden."
            )
        if not ToolPermissionManager().is_tool_allowed(executing_identity, tool):
            raise PermissionError(
                f"{executing_identity!r} mag {tool!r} niet uitvoeren; een mens om goedkeuring "
                "vragen voor een actie die daarna op de permissiecheck stukloopt is de verkeerde "
                "volgorde."
            )

        ticket_ref = generate_ticket_ref()
        payload: dict[str, object] = {
            **action_params,
            "_decision_id": decision_id,
            "_reason": reason,
            "_requested_by": str(user_id),
            "_requested_at": datetime.now(timezone.utc).isoformat(),
            "_executing_identity": executing_identity,
            "_requester_kind": requester_kind,
        }
        await self.create(
            ticket_ref=ticket_ref,
            tenant_id=tenant_id,
            tool_name=action_type or "unknown",
            payload=payload,
            risk_level="HIGH",
        )
        return ticket_ref


def generate_ticket_ref() -> str:
    """Generate a unique ticket reference."""
    return f"hitl_{uuid.uuid4().hex[:16]}"
