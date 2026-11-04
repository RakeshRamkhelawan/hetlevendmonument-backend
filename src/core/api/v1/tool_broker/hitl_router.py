"""De HITL-goedkeuringsroutes van de tool-broker (ADR-036 OP-37, OP-56).

**Een EIGEN bestand, en dat is de hele bevinding van deze dag.** Deze vier endpoints stonden in
`src/core/tool_broker/router.py`, een bestand met 11 routes dat nergens werd geincludeerd. De
copilot maakt via `copilot/service.py:528` wel tickets aan in `hitl_tickets`, en de poort in
`tool_broker/service.py:227` leest juist die tabel voordat een HIGH-risk actie mag lopen. Dus:
ticket wordt gemaakt, kan via de API nooit worden goedgekeurd, actie blijft permanent geblokkeerd,
en de onbewerkte inhoud blijft staan. ADR-015 was op dit pad fail-closed maar onbruikbaar.

**Waarom niet simpelweg dat bestand mounten.** Gemeten in de Taak 2-review: dat had 11 routes
aangeboden in plaats van 4. Een daarvan is `POST /v1/tools/auth/token`, dat het wachtwoord NIET
tegen de database controleert -- de enige eis is `len(password) >= 8` -- en het opgegeven
e-mailadres in het token zet. `auth/dependencies.py:101-122` lost de gebruiker vervolgens uit
precies die claim op en geeft de ECHTE databasegebruiker terug, met zijn rollen en tenant. Dat is
een volledige authenticatie-omzeiling, en de guard ernaast vergelijkt `environment == "production"`
exact zonder `.lower()`, dus op staging staat hij open. Twee andere paden (`POST /v1/tools/execute`,
`GET /v1/tools/`) zouden bovendien de bestaande, geharde handlers schaduwen -- welke wint is
afhankelijk van de registratievolgorde.

Door alleen deze vier hier te zetten is de aangeboden oppervlakte gelijk aan de bedoelde
oppervlakte. `POST /hitl/request` hoort er met opzet NIET bij: de live aanvrager is
`copilot/service.py`, en dat endpoint mounten zou een nieuw rauw schrijfpad openen dat de
sink-guard niet ziet.

`_require_approver` staat hier en niet in het oude bestand, want dit is de enige plek waar hij nog
gebruikt wordt.
"""

# BEWUST GEEN `from __future__ import annotations` (valkuil, gemeten 2026-08-06).
# De rate-limit-decorators hieronder gebruiken `functools.wraps`. In combinatie met uitgestelde
# annotaties kan FastAPI het Pydantic-body-model van approve/reject niet meer oplossen en geeft
# elke aanroep 422. Dat is hier daadwerkelijk gebeurd: 5 tests sloegen om op `assert 422 == 200`.

import asyncio
import importlib
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.tool_broker.dependencies import get_tool_broker_service
from src.core.auth.approval_rights import (
    require_any_approval_right,
    require_approval_right_for_tool,
    tools_the_user_may_decide,
)
from src.core.auth.dependencies import get_current_user
from src.core.api.v1.tool_broker.dependencies import (
    AuditService,
    build_resource,
    consent_read_limit,
    consent_update_limit,
    get_db,
    is_four_eyes_required,
    redact_free_text,
)
from src.core.tool_broker.hitl_notifier import notify_ticket_approved, notify_ticket_rejected
from src.core.tool_broker.models import HITLTicket
from src.core.tool_broker.hitl_repository import (
    _UITVOERENDE_IDENTITEIT,
    HITLTicketRepository,
    redacted_payload_digest,
)
from src.core.tool_broker.redaction import approval_binding
from src.core.tool_broker.schemas import ErrorResponse, ToolHITLApproval, ToolHITLRejection
from src.core.tool_broker.uitvoerredenen import zin_voor

logger = logging.getLogger(__name__)

#: De ENIGE velden die `/hitl/audit` teruggeeft (ADR-036 OP-31/OP-67).
#:
#: **Waarom een toelaatlijst en geen uitsluiting.** Hier stond eerst "alles behalve `tool_input`",
#: met als argument dat een uitsluiting bewaakt door een architectuurtest eerlijker zou zijn dan
#: een toelaatlijst die stil achterloopt. Een blinde review op 2026-08-06 heeft dat argument
#: weerlegd door te meten wat er nog doorheen kwam: `reason` is `payload["_reason"]`, oftewel
#: `decision.explanation_for_user` -- door het model geschreven proza dat de HIGH-risk handeling
#: beschrijft en in de praktijk de parameters navertelt. Dit endpoint beloofde in zijn eigen
#: docstring te tonen DAT er iets is gevraagd en niet WAT; met `reason` erin klopte dat niet.
#: De guard toetste alleen op `tool_input` en kon dat niet zien.
#:
#: Wat er WEL in staat, en waarom: de identiteiten (`requested_by`, `approved_by`, `rejected_by`)
#: zijn juist de kern van het art.-14-toezicht -- dit endpoint is beheerder-only, dus daar horen
#: ze. Wat eruit blijft is alles wat een taalmodel heeft geschreven.
_AUDIT_FIELDS = frozenset(
    {
        "ticket_ref",
        "tenant_id",
        "status",
        "tool_name",
        "risk_level",
        "created_at",
        "expires_at",
        "requested_by",
        "requested_by_email",
        "requested_at",
        "approved_by",
        "approved_at",
        "rejected_by",
        "rejected_at",
        # `resolution_note` hoort hier: dat is wat de MENS erbij schreef, en dit is het endpoint
        # waarvan de hele rechtvaardiging aantoonbaar menselijk toezicht is (OP-69/OP-82).
        "resolution_note",
    }
)

#: Wat een goedkeurder te zien krijgt van een BESLOTEN ticket (`GET /decided`): de projectie van `/audit` plus de velden die
#: de kaart nodig heeft. Er zit geen invoer van de actie in (`tool_input` is altijd leeg) en geen modeltekst: na een besluit
#: blijft alleen het besluit over (OP-47), en `reason` en `agent_id` zijn dan weg. `notes` en `rejection_reason` zijn wat de
#: MENS erbij schreef.
_DECIDED_FIELDS = _AUDIT_FIELDS | {"agent_id", "notes", "rejection_reason"}

#: De statussen van een ticket waarover besloten is (`consumed` is een goedgekeurd ticket waarvan de actie is uitgevoerd).
_BESLOTEN_STATUSSEN = ("approved", "consumed", "rejected")

router = APIRouter(prefix="/api/v1/tools/hitl", tags=["Tool Broker HITL"])


async def _require_approver(
    current_user: UserResponse, db: AsyncSession, tool_name: str | None = None
) -> None:
    """403 tenzij de gebruiker het goedkeurrecht van het PROCES heeft (ADR-039 F1/F2/F7).

    **Wat hier tot 2026-10-09 stond en waarom het weg is.** Deze functie vroeg `is_tenant_admin`.
    Dat maakte de beheerder tot goedkeurder van elk proces, en dat is niet wat een klant wil:
    "een beheerder heeft niets te maken met een proces dat geaccordeerd moet worden" (Rakesh,
    2026-10-09). De poort tegen zelfgoedkeuring (OP-56) blijft: een ticket beslist alleen wie een
    recht heeft dat bij de ACTIE van het ticket hoort (`approval_rights.RECHT_PER_TOOL`),
    en dat recht staat in `role_permissions`. De beheerder-wildcard `*:*` geeft het niet, een
    platform-superuser evenmin; een klein bedrijf wijst de rol `goedkeurder` aan dezelfde persoon
    toe als die ook beheerder is.

    Zonder `tool_name` (de lijst met openstaande tickets, waar nog geen ticket is) volstaat een
    willekeurig goedkeurrecht: de lijst geeft het ONBEWERKTE `tool_input` terug (OP-56), dus wie
    nergens mag goedkeuren heeft die waarden niet nodig. Met `tool_name`: precies het recht dat
    bij die actie hoort; een onbekende actie wordt geweigerd. Zelfgoedkeuring en vier ogen staan
    in `_refuse_self_approval` hieronder en zijn niet veranderd.
    """
    if tool_name is None:
        await require_any_approval_right(db, current_user)
    else:
        await require_approval_right_for_tool(db, current_user, tool_name)


def _is_requester(requester: object, current_user: UserResponse) -> bool:
    """Is `current_user` de aanvrager in `_requested_by`?

    Vergelijkt op het user-id. Tickets die het ToolBroker-pad (`tool_broker/router.py`)
    aanmaakte voor 2026-10-08 hebben daar het e-mailadres in staan; die blijven tot hun SLA
    verloopt in de tabel. Daarom telt een gelijk e-mailadres (hoofdletterongevoelig) ook. Een
    e-mailadres is per gebruiker uniek, dus dit maakt de controle niet ruimer voor een ander.
    """
    if requester is None:
        return False
    text = str(requester)
    if text == str(current_user.id):
        return True
    email = current_user.email or ""
    return "@" in text and text.strip().lower() == email.strip().lower()


#: Tools waarvan het ticket ZELF zegt dat vier ogen nodig is (`vier_ogen_vereist`), los van de instelling van de tenant. Het
#: betaalvoorstel doet dat boven het drempelbedrag per factuur (crediteuren dag 3): dan geldt vier ogen ook bij een tenant die het
#: voor deze actie niet aanzette. Alleen deze namen: een ander tool kan de vlag niet gebruiken om het gedrag te veranderen.
_VIER_OGEN_VANUIT_TICKET = frozenset({"propose_payment_run"})


async def _ticket_eist_vier_ogen(db: AsyncSession, ticket: HITLTicket) -> bool:
    """Vier ogen voor een betaalvoorstel, beslist uit de DATABASE (bedragen en drempel) en niet uit de vlag in het ticket.

    De vlag `vier_ogen_vereist` in het ticket is alleen voor het scherm: een gebruiker kan via `POST /hitl/request` een eigen ticket
    met een eigen vlag maken. `importlib`: een statische import naar `tool_broker` zou een nieuw (bestand, module)-paar zijn.
    """
    if ticket.tool_name not in _VIER_OGEN_VANUIT_TICKET:
        return False
    payload = ticket.payload if isinstance(ticket.payload, dict) else {}
    registry = importlib.import_module("src.core.tool_broker.payment_run_registry")
    return bool(await registry.vier_ogen_nodig(db, ticket.tenant_id, payload.get("regels")))


def _refuse_self_approval(
    ticket: HITLTicket, current_user: UserResponse, *, four_eyes: bool
) -> None:
    """403 als de aanvrager zijn eigen verzoek beslist terwijl dat niet mag (ADR-039).

    **Besluit Rakesh, 2026-10-04 (ADR-039).** Tot die datum weigerde deze functie ELKE
    zelfgoedkeuring (ADR-036 OP-70). Het besluit: mens-in-de-lus staat altijd aan, en wie de
    agent startte mag die actie zelf beslissen -- de applicatie ondersteunt de werkwijze van de
    gebruiker en legt er geen op. Zelf beslissen wordt alleen geweigerd als:

    - **vier ogen aan staat** voor deze actie in deze tenant (`four_eyes`, gelezen uit
      `tenants.settings` door de aanroeper), of
    - **de aanvrager een agent is** (`_requester_kind == "agent"`): een agent keurt nooit zijn
      eigen verzoek goed (Agent2Agent, ADR-039 punt 3). LET OP: vandaag zet geen enkel pad
      `agent`; een ticket dat een taalmodel voorstelt namens een mens geldt als verzoek van die
      mens. Deze tak beschermt dus pas zodra er een agent-tot-agentpad is (security-review dag 2).

    Wat NIET verandert en niet hier staat: de tenantgrens (`repo.get(..., tenant_id=...)`), het
    recht om te beslissen (`_require_approver`) en de auditregel per beslissing.

    De vergelijking loopt via `_requested_by` en `_requester_kind`; beide zet
    `create_hitl_request` NA de modelparameters, dus het model kan ze niet vullen. Ontbreekt
    `_requested_by` (oudere tickets), dan blokkeert deze controle niets; de rolcheck staat er nog.
    """
    payload = ticket.payload if isinstance(ticket.payload, dict) else {}
    if not _is_requester(payload.get("_requested_by"), current_user):
        return
    if payload.get("_requester_kind") == "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A request made by an agent must be resolved by someone else",
        )
    if four_eyes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Four-eyes is enabled for this action: someone other than the requester must "
                "resolve it"
            ),
        )


async def _refuse_self_approval_audited(
    db: AsyncSession, http_request: Request, current_user: UserResponse, ticket: HITLTicket
) -> None:
    """`_refuse_self_approval`, plus een auditregel als hij weigert (acceptant scenario 5).

    Een poging om een eigen verzoek te beslissen terwijl dat niet mag, is wat het toezicht moet
    kunnen terugzien; gemeten op 2026-10-05 stond er na de 403 niets in `audit_logs`. De regel
    gaat via `_write_audit_entry`, dus in `best_effort`: een falende auditregel verandert de 403
    niet. De weigering zelf blijft ongewijzigd.
    """
    try:
        _refuse_self_approval(
            ticket,
            current_user,
            four_eyes=await _ticket_eist_vier_ogen(db, ticket)
            or await is_four_eyes_required(
                db, tenant_id=current_user.tenant_id, action=ticket.tool_name
            ),
        )
    except HTTPException:
        payload = ticket.payload if isinstance(ticket.payload, dict) else {}
        reden = (
            "refused_agent_request"
            if payload.get("_requester_kind") == "agent"
            else "refused_four_eyes"
        )
        await _write_audit_entry(
            db,
            http_request,
            current_user,
            ticket_ref=ticket.ticket_ref,
            tool_name=ticket.tool_name,
            decision=reden,
            binding=None,
        )
        raise


def _safe_tool_name(tool_name: str, tenant_id: int) -> str:
    """De toolnaam zoals hij in de ONUITWISBARE keten mag staan (ADR-036 OP-78).

    **Waarom deze laag bestaat naast de validatie stroomopwaarts.** `CopilotAction.action` heeft nu
    een vorm-eis en `copilot/service.py` weigert een onbekende tool voordat er een ticket ontstaat.
    Dat zijn twee preventielagen, en beide kunnen door een latere wijziging stilvallen -- deze
    sprint heeft daar genoeg voorbeelden van opgeleverd. De ADR-019-keten is de ene plek waar dat
    niet mag: een regel corrigeren breekt de hashketen, dus wat er eenmaal in staat blijft staan.

    Daarom vertrouwt deze functie de waarde NIET, ongeacht wat er stroomopwaarts gebeurt. Een
    bekende tool gaat leesbaar mee -- dat heeft het toezicht nodig. Al het andere wordt een marker
    plus een keyed digest, zodat narekenbaar blijft WELKE waarde er stond voor wie de sleutel
    heeft, zonder dat er ooit vrije tekst in de keten komt.
    """
    from src.core.tool_broker.redaction import value_digest
    from src.core.tool_broker.service import is_known_tool

    if is_known_tool(tool_name):
        return tool_name

    logger.warning(
        "HITL-beslissing op een tool die geen uitvoerder heeft; naam gepseudonimiseerd voor de "
        "auditketen",
        extra={"tenant_id": tenant_id},
    )
    return f"<onbekende-tool:{value_digest(tool_name, tenant_id=tenant_id)}>"


async def _write_audit_entry(
    db: AsyncSession,
    http_request: Request,
    current_user: UserResponse,
    ticket_ref: str,
    tool_name: str,
    decision: str,
    binding: str | None,
    reason: str | None = None,
) -> None:
    """Een onuitwisbare ketenregel bij elke beslissing (ADR-036 OP-71, ADR-019).

    Wat hiervoor overbleef van een HIGH-risk goedkeuring: een `logger.info` en een JSONB-kolom die
    elke latere UPDATE kan herschrijven. Voor een toezichtsrecord waarvan de hele rechtvaardiging
    is dat een mens aantoonbaar heeft besloten, is dat te weinig.

    NA de primaire commit en in `best_effort` (backend-patterns par. 3): een falende auditregel mag
    een reeds genomen beslissing niet terugdraaien. Het falen wordt gelogd, niet weggeslikt.

    De metadata bevat bewust GEEN payload -- die is door een taalmodel geschreven. Wel de binding,
    zodat narekenbaar blijft WELKE aanroep is besloten zonder de inhoud te bewaren.
    """
    from src.core.utils.best_effort import best_effort

    client_host = http_request.client.host if http_request.client else "unknown"

    # De naam zoals hij wordt OPGESLAGEN, en die zelfde waarde gaat in de digest (ADR-036 H-2).
    # Niet de rauwe `tool_name`: voor een onbekende tool bewaart de auditregel een pseudoniem,
    # en een digest over iets dat nergens in de rij staat is door niemand na te rekenen.
    veilige_toolnaam = _safe_tool_name(tool_name, current_user.tenant_id)

    # De afkeurreden is door een MENS geschreven en is wat het toezicht moet kunnen terugzien
    # (acceptant scenario 5: `details` was `{}`). Hij gaat door dezelfde PII-opschoning als tekst
    # richting een taalmodel, zodat er geen adres of IBAN in het auditlog blijft staan.
    details: dict[str, object] = {}

    async with best_effort("ADR-019 auditregel voor een HITL-beslissing", db_session=db):
        if reason:
            details["reason"] = redact_free_text(reason)
        await AuditService.log_event(
            db=db,
            event_type="hitl_decision",
            severity="medium",
            source_ip=client_host,
            endpoint=http_request.url.path,
            description=f"HITL ticket {ticket_ref} {decision} by user {current_user.id}",
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action=decision,
            # `resource` WORDT gehasht, `event_metadata` en `user_id` niet (ADR-036 H-2). Twee
            # regels met een andere toolnaam en een andere goedkeurder leverden daardoor
            # dezelfde hash op: precies het bewijs waarop de art.-14-claim rust was achteraf
            # te wijzigen zonder dat de ketenverificatie brak. De digest bindt die drie velden
            # nu aan de keten zonder `_compute_hash` te veranderen -- dat laatste breekt elke
            # bestaande keten en is een besluit van Rakesh.
            resource=build_resource(
                ticket_ref=ticket_ref,
                tool_name=veilige_toolnaam,
                user_id=current_user.id,
                binding=binding,
            ),
            metadata={
                "ticket_ref": ticket_ref,
                "tool_name": veilige_toolnaam,
                "approval_binding": binding,
            },
            details=details,
        )
        await db.commit()




def _als_gebruikersnummer(waarde: object) -> int | None:
    """`_requested_by` als gebruikersnummer, of `None` (ADR-036 OP-89).

    Het veld is een string in JSONB. `create_hitl_request` zet er `str(user_id)` in, maar het
    niet-gemounte `/hitl/request`-pad zette er ooit een e-mailadres in, en JSONB garandeert niets.
    Fout raden is hier gratis: zonder gebruikersnummer blijft `user_id` simpelweg uit de
    executiecontext, en dan valt de tenant nog steeds goed.
    """
    # `isascii() and isdecimal()` en NIET `isdigit()` (ADR-036 OP-106). `isdigit()` is True voor
    # Arabisch-Indische cijfers (dan wordt "zo'n cijfer" stil gebruiker 3, terwijl
    # `_refuse_self_approval` strings vergelijkt en dus iets anders concludeert) EN voor
    # superscripts, waarop `int()` een ValueError gooit -- ongevangen, dus een 500 NADAT de
    # goedkeuring al is vastgelegd.
    tekst = str(waarde or "").strip()
    return int(tekst) if tekst.isascii() and tekst.isdecimal() else None

#: Hoe lang een goedgekeurde actie mag draaien binnen het goedkeuringsverzoek (ADR-036 OP-89).
#:
#: Uitvoeren binnen het verzoek is een bewuste keuze van Rakesh (2026-08-07): het is de enige
#: volgorde die het wisbesluit uit OP-47 verenigt met een werkende lus, want na het wissen zijn de
#: parameters weg en is uitvoeren per constructie onmogelijk. De prijs is dat een trage tool een
#: trage knop wordt; vandaar een expliciete grens in plaats van een beheerder die blijft wachten.
_UITVOER_TIMEOUT_SECONDEN = 30


async def _voer_goedgekeurde_actie_uit(
    broker: Any,  # TODO(TYPE): replace Any with ToolBrokerService -- concreet typeren vraagt een domain-import (ADR-033)
    *,
    ticket_ref: str,
    tool_name: str,
    parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    tenant_id: int,
    aangevraagd_door: int | None,
    uitvoerende_identiteit: str = _UITVOERENDE_IDENTITEIT,
) -> tuple[bool, str | None]:
    """Voer de goedgekeurde actie uit. Geeft (geslaagd, foutCLASSIFICATIE) terug.

    **Waarom de ticketverwijzing wordt meegegeven.** Dan verzilvert de bestaande poort in
    `execute_tool` het ticket: hij toetst dat de tool klopt, dat de parameters overeenkomen met wat
    is goedgekeurd, en zet de status op `consumed` zodat dezelfde goedkeuring geen tweede keer
    geldt. Dat is precies de machinerie uit OP-63/OP-75, die tot vandaag nooit werd doorlopen omdat
    niets ooit een ticketverwijzing meegaf.

    **Nooit de foutTEKST terug.** Die kan payload-inhoud bevatten -- door een taalmodel geschreven
    parameters, en dat is de hele reden dat deze feature bestaat (OP-29). Alleen het TYPE van de
    fout gaat naar buiten en naar de auditregel.

    **`uitvoerende_identiteit` (ADR-036 OP-163).** Moet dezelfde identiteit zijn als
    `create_hitl_request` bij het AANMAKEN van dit ticket heeft getoetst (`_UITVOERENDE_IDENTITEIT`
    is alleen de DEFAULT daarvoor) -- anders keurt de permissiecheck bij aanmaken iets anders goed
    dan wat hier daadwerkelijk wordt uitgevoerd.
    """
    payload: dict[str, Any] = {**parameters, "_hitl_ticket_ref": ticket_ref}
    context: dict[str, Any] = {"tenant_id": tenant_id}
    if aangevraagd_door is not None:
        context["user_id"] = aangevraagd_door

    try:
        async with asyncio.timeout(_UITVOER_TIMEOUT_SECONDEN):
            resultaat = await broker.execute_tool(
                tool_name=tool_name,
                payload=payload,
                agent_id=uitvoerende_identiteit,
                context=context,
            )
    except TimeoutError:
        logger.error(
            "hitl.uitvoering_timeout",
            extra={"ticket_ref": ticket_ref, "tool_name": tool_name, "tenant_id": tenant_id},
        )
        return False, "timeout"
    except Exception as exc:  # noqa: BLE001 -- de classificatie gaat naar buiten, de tekst nooit
        logger.error(
            "hitl.uitvoering_gefaald: %s",
            type(exc).__name__,
            exc_info=True,
            extra={"ticket_ref": ticket_ref, "tool_name": tool_name, "tenant_id": tenant_id},
        )
        return False, type(exc).__name__

    # EEN UITZONDERING IS NIET DE ENIGE FAALVORM. Het toolcontract (BE-AGT-039 par. 3) schrijft
    # `{"success": false, "error": ...}` voor, en tot 2026-09-21 reisde er over deze route geen
    # enkele tool die die vorm gebruikte -- dus stond hier alleen een `try`. `schedule_training`
    # gebruikt hem op zes takken (onbekend veld, ongeldige status, medewerker of training bestaat
    # niet, ...), en zonder deze controle meldt de API GESLAAGD terwijl het ticket op `consumed`
    # staat en er geen rij is geschreven: succes zonder werk, op het enige toezichtspunt dat dit
    # systeem heeft. Dezelfde fout is op het SKILLpad al onder BE-AGT-044 gerepareerd
    # (`specialist_base.py`); deze route was toen overgeslagen. (Gate 2-review 2026-09-21, HIGH-2.)
    #
    # Alleen de CLASSIFICATIE naar buiten, nooit `result["error"]` -- die tekst kan
    # payload-inhoud bevatten, zie de docstring hierboven.
    if isinstance(resultaat, dict) and resultaat.get("success") is False:
        logger.error(
            "hitl.uitvoering_gefaald: tool_failure",
            extra={"ticket_ref": ticket_ref, "tool_name": tool_name, "tenant_id": tenant_id},
        )
        # Een `reden_code` van de tool is een SLEUTEL in een vaste tabel (`uitvoerredenen`), geen tekst: alleen een bekende code gaat mee
        # en de goedkeurder krijgt de vaste zin erbij (crediteuren nazorg, punt 1). Een onbekende of ontbrekende code blijft `tool_failure`.
        code = resultaat.get("reden_code")
        if zin_voor(code) is not None:
            return False, f"tool_failure:{code}"
        return False, "tool_failure"

    return True, None

@router.post(
    "/approve",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Ticket already resolved"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Ticket not found"},
    },
)
@consent_update_limit
async def approve_hitl_request(
    request: ToolHITLApproval,
    http_request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    # De broker via de pakket-facade, niet met een deep-import: ADR-033 Contract 1 verbiedt een
    # routerbestand om rechtstreeks in het domein te grijpen, en `get_db` gaat hier al zo.
    broker: Any = Depends(  # TODO(TYPE): replace Any with ToolBrokerService -- zie ADR-033 hierboven
        get_tool_broker_service
    ),
    # CSRF op de twee routes die STAAT WIJZIGEN (ADR-036 OP-72). `get_current_user` accepteert
    # het `access_token`-cookie, dus zonder deze controle is een cross-site POST alleen door
    # `SameSite` afgedekt -- en dat is een browsereigenschap, geen controle van ons. Vergelijkbare
    # endpoints (copilot/api/turn_endpoint.py, api/v1/missions/lifecycle_router.py) hebben hem al.
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Approve a pending HITL ticket. approved_by is set from the authenticated user."""
    await _require_approver(current_user, db)
    # NOODSTOP PER KLANT (ADR-036 OP-03): goedkeuren IS uitvoeren (besluit Rakesh 2026-08-07), dus
    # dit is een deur. De controle staat VOOR `repo.approve`: dat wist de parameters, en een
    # goedkeuring die daarna door de broker wordt geweigerd laat een goedgekeurd ticket achter
    # dat nooit meer uit te voeren is. Zo blijft het ticket `pending` tot de stop is opgeheven.
    # De controle komt via de broker-module (die haar zelf als deur gebruikt): een eigen import van
    # `noodstop.guard` zou een nieuw (bestand -> module)-paar in de fan-out van `core_api` zijn
    # (plafond 565, exact bereikt) en dit bestand kent `tool_broker` al.
    from src.core.tool_broker.service import KlantStilgezet, eis_klant_actief

    try:
        await eis_klant_actief(current_user.tenant_id)
    except KlantStilgezet as stop:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=stop.bericht) from stop
    repo = HITLTicketRepository(db)
    ticket = await repo.get(request.ticket_ref, tenant_id=current_user.tenant_id)

    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    await _require_approver(current_user, db, ticket.tool_name)

    if ticket.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket is already {ticket.status}",
        )

    await _refuse_self_approval_audited(db, http_request, current_user, ticket)

    # De digest van wat er wordt weggegooid, berekend HIER omdat het ticket al geladen is
    # (ADR-036 OP-47). Zonder dit blijft er na het opruimen geen enkel spoor van WAT er is
    # goedgekeurd: `notes`/`reason` uit de API worden nooit opgeslagen en de ADR-019-keten is
    # op dit pad niet gewired.
    # De parameters VOOR het wissen vasthouden: `repo.approve` maakt van de payload een kale
    # besluitprojectie, en daarna is uitvoeren per constructie onmogelijk (ADR-036 OP-89).
    # Ook `BROKER_INJECTED_KEYS` eruit (ADR-036 OP-105). Alleen `_`-prefix strippen liet een
    # model-geschreven `user_id` of `tenant_id` in de payload staan. `execute_tool` overschrijft
    # die ALLEEN als de context ze bevat, en `context["user_id"]` wordt alleen gezet als
    # `_requested_by` een zuiver getal is -- ontbreekt dat veld (oudere tickets), dan is de waarde
    # van het model wat de tool krijgt. Deze sleutels tellen sowieso niet mee in de binding, dus
    # weglaten verandert niets aan de verzilvering.
    from src.core.tool_broker.redaction import BROKER_INJECTED_KEYS

    parameters_voor_uitvoering = {
        k: v
        for k, v in dict(ticket.payload).items()
        if not k.startswith("_") and k not in BROKER_INJECTED_KEYS
    }
    aangevraagd_door = ticket.payload.get("_requested_by")
    # Dezelfde identiteit als bij het AANMAKEN (ADR-036 OP-163) -- ontbreekt hij (tickets van
    # voor deze fix), dan blijft de bestaande default (`copilot`) gelden.
    uitvoerende_identiteit = str(
        ticket.payload.get("_executing_identity", _UITVOERENDE_IDENTITEIT)
    )

    redacted = redacted_payload_digest(
        ticket.payload, ticket.tool_name, tenant_id=current_user.tenant_id
    )
    # De binding legt vast WELKE tool met WELKE parameters is goedgekeurd (ADR-036 OP-63). Zonder
    # deze waarde kan de poort bij uitvoering alleen "dit ticket staat op goedgekeurd" vaststellen,
    # en is een goedkeuring bruikbaar voor elke andere HIGH-risk tool met elke andere parameterset.
    # Hier berekend en niet in `approve()`: daar is de oorspronkelijke payload al weg.
    binding = approval_binding(
        ticket.tool_name, ticket.payload, tenant_id=current_user.tenant_id
    )
    success = await repo.approve(
        request.ticket_ref,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        redacted_payload=redacted,
        binding=binding,
        note=request.notes,
    )
    if not success:
        # Ook de weg hierheen als het ticket inmiddels is VERLOPEN: `approve` filtert op
        # `expires_at` (OP-64), dus een aanvraag ouder dan de SLA raakt nul rijen.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to approve ticket (already resolved or expired)",
        )


    await db.commit()
    await db.refresh(ticket)

    # UITVOEREN, na de commit zodat de poort het ticket als goedgekeurd ziet en het kan
    # verzilveren. Besluit Rakesh 2026-08-07: goedkeuren betekent dat het gebeurt.
    geslaagd, foutsoort = await _voer_goedgekeurde_actie_uit(
        broker,
        ticket_ref=request.ticket_ref,
        tool_name=ticket.tool_name,
        parameters=parameters_voor_uitvoering,
        tenant_id=current_user.tenant_id,
        # `_requested_by` is een string uit JSONB en kan alles bevatten -- op het niet-gemounte
        # `/hitl/request`-pad zelfs een e-mailadres. Alleen een zuiver getal telt als gebruiker;
        # al het andere levert `None` en dan blijft `user_id` gewoon uit de context weg.
        aangevraagd_door=_als_gebruikersnummer(aangevraagd_door),
        uitvoerende_identiteit=uitvoerende_identiteit,
    )

    # VASTLEGGEN voordat er iets kan terugrollen (ADR-036 OP-100).
    #
    # De poort verzilvert het ticket (`approved` -> `consumed`) in DEZELFDE sessie, en die UPDATE
    # stond hier nog niet vast. `_write_audit_entry` schrijft binnen `best_effort`, en dat rolt de
    # sessie terug bij een fout -- terecht, want een auditregel mag de primaire handeling nooit
    # blokkeren. Maar daarmee rolde hij ook de verzilvering terug: het ticket sprong terug op
    # `approved`, er was geen auditregel, en de goedkeuring was binnen 24 uur opnieuw te
    # verzilveren door de aanvrager, die de ticketverwijzing in zijn eigen antwoord terugkrijgt.
    #
    # De eenmaligheid uit OP-63/OP-75 hing zo aan iets dat per definitie mag falen. Aangetoond
    # tegen een echte database door de blinde review van 2026-08-08.
    await db.commit()

    # Een mislukte uitvoering draait de goedkeuring NIET terug: een mens heeft besloten, en dat is
    # een feit dat in de keten hoort. De uitkomst gaat mee als classificatie, nooit als fouttekst.
    await _write_audit_entry(
        db,
        http_request,
        current_user,
        request.ticket_ref,
        ticket.tool_name,
        "approved" if geslaagd else f"approved_execution_failed:{foutsoort}",
        binding,
    )

    logger.info(
        "HITL ticket approved",
        extra={
            "ticket_ref": request.ticket_ref,
            # Het gebruikersNUMMER en niet het adres (ADR-036 OP-85). `security.md`:
            # "Never log secrets, tokens, passwords, or PII." `resolved_by` (FK naar
            # users.id) is het bewijs; het adres voegt niets toe dat de auditregel niet
            # al heeft, en een adres is een persoonsgegeven dat in logs blijft hangen.
            "approved_by": current_user.id,
            "tenant_id": current_user.tenant_id,
        },
    )

    # Notify connected clients about approval
    await notify_ticket_approved(
        request.ticket_ref, current_user.tenant_id, f"user:{current_user.id}", db=db
    )

    # Convert to schema dict for return compatibility
    from src.core.tool_broker.hitl_store import get_ticket_async
    updated_ticket_dict = await get_ticket_async(request.ticket_ref, current_user.tenant_id, db)
    # 200 en geen 500 bij een mislukte uitvoering: de goedkeuring IS vastgelegd, en dat
    # terugmelden als serverfout zou de beheerder laten denken dat zijn besluit niet is
    # aangekomen. `executed` maakt het onderscheid expliciet.
    soort, _, reden_code = (foutsoort or "").partition(":")
    return {
        "success": True,
        "data": updated_ticket_dict,
        "executed": geslaagd,
        "execution_error": soort or None,
        # De vaste Nederlandse zin bij een bekende reden (nooit de tekst van de tool); `None` bij succes of een onbekende reden.
        "execution_message": zin_voor(reden_code),
    }


@router.post(
    "/reject",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Ticket already resolved"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Ticket not found"},
    },
)
@consent_update_limit
async def reject_hitl_request(
    request: ToolHITLRejection,
    http_request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    # CSRF op de twee routes die STAAT WIJZIGEN (ADR-036 OP-72). `get_current_user` accepteert
    # het `access_token`-cookie, dus zonder deze controle is een cross-site POST alleen door
    # `SameSite` afgedekt -- en dat is een browsereigenschap, geen controle van ons. Vergelijkbare
    # endpoints (copilot/api/turn_endpoint.py, api/v1/missions/lifecycle_router.py) hebben hem al.
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Reject a pending HITL ticket. rejected_by is set from the authenticated user."""
    await _require_approver(current_user, db)
    repo = HITLTicketRepository(db)
    ticket = await repo.get(request.ticket_ref, tenant_id=current_user.tenant_id)

    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    await _require_approver(current_user, db, ticket.tool_name)

    if ticket.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket is already {ticket.status}",
        )

    await _refuse_self_approval_audited(db, http_request, current_user, ticket)

    # De digest van wat er wordt weggegooid, berekend HIER omdat het ticket al geladen is
    # (ADR-036 OP-47). Zonder dit blijft er na het opruimen geen enkel spoor van WAT er is
    # goedgekeurd: `notes`/`reason` uit de API worden nooit opgeslagen en de ADR-019-keten is
    # op dit pad niet gewired.
    redacted = redacted_payload_digest(
        ticket.payload, ticket.tool_name, tenant_id=current_user.tenant_id
    )
    success = await repo.reject(
        request.ticket_ref,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        redacted_payload=redacted,
        note=request.reason,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to reject ticket")

    await db.commit()
    await db.refresh(ticket)

    await _write_audit_entry(
        db,
        http_request,
        current_user,
        request.ticket_ref,
        ticket.tool_name,
        "rejected",
        None,
        reason=request.reason,
    )

    logger.info(
        "HITL ticket rejected",
        extra={
            "ticket_ref": request.ticket_ref,
            # Het gebruikersNUMMER en niet het adres (ADR-036 OP-85). `security.md`:
            # "Never log secrets, tokens, passwords, or PII." `resolved_by` (FK naar
            # users.id) is het bewijs; het adres voegt niets toe dat de auditregel niet
            # al heeft, en een adres is een persoonsgegeven dat in logs blijft hangen.
            "rejected_by": current_user.id,
            "tenant_id": current_user.tenant_id,
        },
    )

    # Notify connected clients about rejection
    await notify_ticket_rejected(
        request.ticket_ref, current_user.tenant_id, f"user:{current_user.id}", db=db
    )

    # Convert to schema dict for return compatibility
    from src.core.tool_broker.hitl_store import get_ticket_async
    updated_ticket_dict = await get_ticket_async(request.ticket_ref, current_user.tenant_id, db)
    return {"success": True, "data": updated_ticket_dict}


@router.get(
    "/pending",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
)
@consent_read_limit
async def list_pending_hitl_requests(
    http_request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List pending HITL tickets for the authenticated tenant (approvers only)."""
    await _require_approver(current_user, db)
    # Alleen tickets die deze gebruiker mag beslissen (ADR-039).
    beslisbaar = await tools_the_user_may_decide(db, current_user)
    from src.core.tool_broker.hitl_store import (
        count_tickets_by_tenant_async,
        get_tickets_by_tenant_async,
    )

    # Filteren, sorteren, pagineren en tellen doet de DATABASE (ADR-036 OP-68). Hier stond eerder
    # `limit=2000, offset=0` met een comment "grab all to filter and sort locally": dat gaf een
    # stil lege pagina zodra `offset` boven 2000 kwam, en een `total` die op 2000 was afgetopt.
    page = await get_tickets_by_tenant_async(
        tenant_id=current_user.tenant_id,
        db=db,
        limit=limit,
        offset=offset,
        status="pending",
        tool_names=beslisbaar,
    )
    total = await count_tickets_by_tenant_async(
        tenant_id=current_user.tenant_id, db=db, status="pending", tool_names=beslisbaar
    )

    return {"success": True, "data": page, "limit": limit, "offset": offset, "total": total}


@router.get(
    "/decided",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Geen goedkeurrecht"},
    },
)
@consent_read_limit
async def list_decided_hitl_requests(
    http_request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """De BESLOTEN tickets van de eigen tenant voor de tools die deze gebruiker mag beslissen, nieuwste besluit eerst.

    Voor het scherm Goedkeuringen (tabbladen Goedgekeurd en Afgekeurd): `/audit` is beheer en een goedkeurder kreeg daar
    403, waardoor de tabbladen altijd leeg waren (acceptatie 2026-10-21). Zelfde recht en dezelfde toolfilter als
    `/pending`; zonder invoer van de actie (zie `_DECIDED_FIELDS`).
    """
    await _require_approver(current_user, db)
    beslisbaar = await tools_the_user_may_decide(db, current_user)
    from src.core.tool_broker.hitl_store import (
        count_tickets_by_tenant_async,
        get_tickets_by_tenant_async,
    )

    page = await get_tickets_by_tenant_async(
        tenant_id=current_user.tenant_id,
        db=db,
        limit=limit,
        offset=offset,
        statuses=_BESLOTEN_STATUSSEN,
        tool_names=beslisbaar,
        nieuwste_besluit_eerst=True,
    )
    total = await count_tickets_by_tenant_async(
        tenant_id=current_user.tenant_id,
        db=db,
        statuses=_BESLOTEN_STATUSSEN,
        tool_names=beslisbaar,
    )
    projected = [
        {**{k: v for k, v in ticket.items() if k in _DECIDED_FIELDS}, "tool_input": {}}
        for ticket in page
    ]
    return {"success": True, "data": projected, "limit": limit, "offset": offset, "total": total}


@router.get(
    "/audit",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
)
@consent_read_limit
async def list_hitl_audit(
    http_request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List all HITL tickets (any status) for the authenticated tenant -- ADMIN ONLY.

    ADR-036 OP-31. Dit endpoint had als enige dependency `get_current_user`: geen scope, geen
    adminrol. Het leverde voor ELK ticket in de tenant, in elke status en onbeperkt in tijd, het
    ONBEWERKTE `tool_input` uit, plus `requested_by` (het e-mailadres van de aanvrager). Voor de
    tools die een ticket krijgen -- HIGH-risk, dus `local__send_email` --
    is dat de klaartekst van de aanroep.

    AI Act art. 14 rechtvaardigt dat de GOEDKEURDER ziet wat hij goedkeurt, op het moment van
    goedkeuren. Dat is `/hitl/pending`, en daar blijven de waarden staan. Het rechtvaardigt geen
    permanent, tenantbreed klaartekstarchief voor iedere ingelogde gebruiker. Dat maakte de
    pseudonimisering van OP-27 ook omzeilbaar: wat in de auditketen een digest is, stond hier in
    het klare.

    Twee wijzigingen, hetzelfde patroon als `api/v1/tool_audit/router.py` dat het al goed doet:
    een adminrol-check, en een projectie ZONDER `tool_input`.
    """
    from src.core.auth.runtime_deps import is_tenant_admin
    from src.core.tool_broker.hitl_store import (
        count_tickets_by_tenant_async,
        get_tickets_by_tenant_async,
    )

    if not is_tenant_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    page = await get_tickets_by_tenant_async(
        tenant_id=current_user.tenant_id, db=db, limit=limit, offset=offset
    )
    total = await count_tickets_by_tenant_async(tenant_id=current_user.tenant_id, db=db)

    projected = [{k: v for k, v in ticket.items() if k in _AUDIT_FIELDS} for ticket in page]

    return {
        "success": True,
        "data": projected,
        "limit": limit,
        "offset": offset,
        "total": total,
    }
