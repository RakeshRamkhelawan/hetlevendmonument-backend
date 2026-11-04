"""Gatekeeper HITL router -- approve / reject endpoints."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.api.v1.gatekeeper.dependencies import (
    GatekeeperRepository,
    GovernanceContractRepository,
    HITLRequestModel,
)
from src.core.api.v1.gatekeeper.schemas import (
    ErrorResponse,
    HITLApprovalRequest,
    HITLRejectionRequest,
    HITLResponse,
)
from src.core.api.auth.dependencies import validate_csrf_token
from src.core.auth.approval_rights import (
    require_any_approval_right,
    require_approval_right_for_agent,
)
from src.core.auth.runtime_deps import UserResponse, get_current_user
from src.core.middleware.tenant_context import get_tenant_id

logger = logging.getLogger("gatekeeper_api")

router = APIRouter(prefix="/api/v1/gatekeeper", tags=["Gatekeeper"])


async def _require_approver(
    current_user: UserResponse, db: AsyncSession, agent_id: str | None = None, *, specific: bool = False
) -> str:
    """De identiteit van de goedkeurder, of 403 (ADR-036 OP-43, ADR-039 F1/F2/F7).

    **Sinds 2026-10-09 een PROCESRECHT en geen beheerdersrol (besluit Rakesh, ADR-039).** Zonder
    `specific` volstaat een willekeurig goedkeurrecht (poort voor de body); met `specific` het recht
    dat bij de agent van het ticket hoort (`approval_rights.RECHT_PER_AGENT`, onbekende agent
    = weigeren). De beheerder (`*:*`) en de platform-superuser hebben het niet vanzelf. De uitleg over
    het admin-vocabulaire hieronder is HISTORIE: `is_tenant_admin` speelt hier niet meer mee.

    Twee dingen die hier tot 2026-08-04 misgingen, in de ENIGE HITL-route die de app daadwerkelijk
    serveert (`tool_broker/router.py` heeft nul importeurs -- OP-37):

    1. Er was geen rolcheck. Alleen de tenant kwam uit de ADR-003 ContextVar, dus elke gebruiker
       met een geldig tenant-token kon elk openstaand ticket goedkeuren. Daarmee is de HITL-gate
       uit ADR-015 zelf-goedkeurend: de tool-broker weigert een HIGH-risk actie zonder goedgekeurd
       ticket, en de aanvrager keurt zijn eigen ticket goed.
    2. De naam van de goedkeurder kwam uit `request_body.approved_by` en ging zo in
       `GovernanceContract.record_hitl_approval()` -- het veld dat OP-28 registreert als de kern
       van het art.-14-toezicht. Bewijs dat de aanvrager zelf mag invullen, bewijst niets.

    Het body-veld blijft in het schema bestaan maar wordt GENEGEERD. Dat is hetzelfde
    "context wint"-patroon dat `tool_broker/service.py:162` al voor `payload["tenant_id"]`
    gebruikt: geen API-breuk voor bestaande aanroepers, en de waarde kan niet meer bepalen wat er
    wordt vastgelegd.

    **Welk admin-begrip hier geldt (bijgewerkt 2026-09-01, ADR-036 OP-40).** Deze route gebruikte
    `is_tenant_admin` toen dat nog een EIGEN, smal vocabulaire had: `{admin, tenantadmin}` plus
    superuser, waardoor een `system_admin` hier werd geweigerd terwijl hij in het hele
    `admin/`-domein wel beheerder was. Die splitsing is opgeheven: `is_tenant_admin` delegeert nu
    naar `is_admin`, en dat accepteert `{admin, system_admin, tenantadmin}` plus superuser,
    hoofdletter-ongevoelig.

    **Gevolg voor deze route, expliciet omdat het de AI Act art.-14-poort is:** een `system_admin`
    kan sinds die wijziging HITL-tickets goedkeuren. Dat is een uitbreiding van wie het menselijk
    toezicht mag uitoefenen, doorgevoerd op expliciet besluit van Rakesh. Het vocabulaire staat
    vastgepind in `TestTheChosenAdminVocabularyIsPinned` in
    `tests/unit/api/test_gatekeeper_hitl_requires_an_approver.py`, zodat een volgende
    verschuiving opnieuw een zichtbare testwijziging is.

    **Bijgewerkt 2026-09-09 (ADR-036 OP-81, GESLOTEN).** Deze rolcheck was tot dan de ENIGE
    controle op deze route -- `hitl_requests` had geen veld voor de menselijke aanvrager, dus een
    functiescheidingscheck zoals OP-70 op het broker-pad kon hier niet bestaan. Sinds OP-81 draagt
    `HITLRequestModel.requested_by_user_id` die identiteit, en `approve_hitl`/`reject_hitl` roepen
    na deze functie ook `_require_traceable_requester()` + `_refuse_self_approval()` aan (fail-closed
    op approve; bewust fail-open op reject, want `save_hitl_request` heeft vandaag geen productie-
    aanroeper, zie OP-221). Deze functie blijft uitsluitend de ROL controleren; de aanvrager-check
    zit in die twee aanroepen, niet hier.
    """
    if specific:
        await require_approval_right_for_agent(db, current_user, agent_id)
    else:
        await require_any_approval_right(db, current_user)
    # Het gebruikersNUMMER en niet `current_user.email` (ADR-036 OP-55, ronde 7).
    #
    # OP-43 haalde deze waarde uit `request_body` en verving hem door het adres uit het token.
    # Daarmee kan de AANVRAGER hem niet meer kiezen, maar de GOEDKEURDER wel: `PUT
    # /api/v1/users/me` (`api/v1/users/me_router.py:70-79`) laat elke geauthenticeerde gebruiker
    # zijn eigen adres op elk nog vrij adres zetten -- geen verificatielus, geen
    # `can_manage_users`-check, alleen uniciteit. Een beheerder kon dus `ceo@klant.nl` worden,
    # goedkeuren, en terugzetten.
    #
    # Dat weegt hier zwaarder dan bij een gewoon logveld: dit is wat OP-28 registreert als de kern
    # van het art.-14-toezicht, en het valt buiten `compute_audit_hash` -- zelfgekozen EN niet
    # manipulatiebestendig.
    #
    # De `user:`-prefix staat er zodat niemand de waarde later voor een weergavenaam aanziet; een
    # kaal getal in een tekstkolom die eerder adressen bevatte vraagt om die verwarring. De
    # weergavenaam hoort bij het LEZEN opgelost te worden uit `users.id`, want die kan legitiem
    # veranderen terwijl het bewijs dat niet mag.
    return f"user:{current_user.id}"


async def _require_an_approval_right(
    db: AsyncSession = Depends(get_db), current_user: UserResponse = Depends(get_current_user)
) -> None:
    """Dependency: 403 voordat de body gevalideerd wordt voor wie nergens mag goedkeuren."""
    await require_any_approval_right(db, current_user)


def _refuse_self_approval(hitl: HITLRequestModel, current_user: UserResponse) -> None:
    """403 als de beslisser dezelfde mens is als de aanvrager (ADR-036 OP-81).

    **Waarom deze grens hier ontbrak.** `_require_approver` toetst een ROL, geen RELATIE. Een
    tenantbeheerder kon dus een agent namens zichzelf een HIGH-risk actie laten voorstellen en het
    resulterende ticket zelf goedkeuren -- precies bij de groep met de meeste rechten was het
    vierogenprincipe uit ADR-015 daarmee een formaliteit. Het zusteroppervlak
    `api/v1/tool_broker/hitl_router.py` sloot dat gat in OP-70; hier bleef het open omdat
    `HITLRequestModel` geen veld had voor de aanvragende mens. Dat veld is er nu (OP-81).

    **Waarom op de MENS en niet op de agent.** OWASP ASVS 5.0 8.3.3: neem het autorisatiebesluit
    op de permissies van het OORSPRONKELIJKE subject, niet van een tussenliggende service die
    namens hem handelt. `hitl.agent_id` is die tussenliggende service; een agent is geen tweede
    paar ogen en kan geen verantwoording dragen. Toetsen op `agent_id` zou bovendien elk ticket van
    dezelfde agent aan elkaar knopen en niets zeggen over de mens die erachter zat.

    De waarde is server-geschreven (`Gatekeeper._create_hitl_request` uit de server-side context,
    ASVS 8.3.1) -- de aanvrager kan hem niet kiezen, net zomin als de goedkeurder zijn eigen
    `approved_by` kan kiezen sinds OP-43.

    Deze functie toetst alleen de RELATIE. Of er uberhaupt een herleidbare aanvrager IS, is een
    aparte vraag met een ander antwoord per route: zie `_require_traceable_requester`, die alleen
    op de goedkeurroute hangt.
    """
    # Rechtstreeks en NIET via `getattr(..., None)`: een vangnet met een default maakt van een
    # hernoemde of verdwenen kolom een stille fail-open, en dat is precies de holle-guard-vorm die
    # .claude/rules/quality-gates.md verbiedt. Verdwijnt het veld, dan hoort dit luid te breken.
    requester = hitl.requested_by_user_id
    if requester is not None and requester == current_user.id:
        raise HTTPException(
            status_code=403,
            detail=(
                "SELF_APPROVAL_FORBIDDEN: you cannot approve or reject a HITL request that "
                "was submitted on your own behalf"
            ),
        )


def _require_traceable_requester(hitl: HITLRequestModel) -> None:
    """403 als niet vast te stellen is NAMENS WELKE MENS het verzoek is gedaan (ADR-036 OP-81).

    **Alleen op GOEDKEUREN, met opzet.** Een goedkeuring is het bewijs waarop het menselijk
    toezicht uit AI Act art. 14 rust. Kan niemand vaststellen wie erom vroeg, dan is niet vast te
    stellen dat aanvrager en beslisser twee verschillende mensen zijn -- en dan bewijst de
    goedkeuring niet wat ze hoort te bewijzen. Een sentinel of een gok verzinnen is geen optie
    (huisregel: bij een vereist veld zonder correcte waarde blokkeren, niet omheen bouwen).

    **Waarom dit hier fail-CLOSED mag terwijl het broker-pad fail-OPEN is.** Het broker-pad
    beargumenteert zijn fail-open met "onbeoordeelbaar maken zou de wachtrij vastzetten". Dat
    argument gaat hier niet op, om twee gemeten redenen:

    1. Er zijn geen rijen om vast te laten lopen. `GatekeeperRepository.save_hitl_request` is de
       enige schrijver van `hitl_requests` en heeft NUL aanroepers in `src/` (gemeten 2026-09-01);
       de zeven overige schrijfplekken staan allemaal in `tests/`.
    2. AFWIJZEN blijft bewust open (zie `reject_hitl`). Daarmee heeft elk ticket altijd een
       uitweg: het kan de wachtrij verlaten zonder dat er ooit een onbewijsbare goedkeuring
       ontstaat. Dat is fail-secure ZONDER de vastgelopen wachtrij.

    Het broker-pad heeft op dit punt dus een gat en is hier geen precedent. Dat is geregistreerd
    als bevinding, niet gekopieerd.

    Eigen foutcode, en niet dezelfde tekst als een echte zelf-goedkeuring: een beheerder die dit
    ziet moet kunnen onderscheiden tussen "jij mag dit specifieke ticket niet" en "dit ticket mist
    het bewijs dat een goedkeuring uberhaupt geldig maakt". Dat leidt tot twee heel verschillende
    vervolgacties.
    """
    if hitl.requested_by_user_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "REQUESTER_NOT_TRACEABLE: this HITL request has no traceable human requester, "
                "so it cannot be approved; it can still be rejected"
            ),
        )


@router.post(
    "/hitl/approve",
    response_model=HITLResponse,
    # De rolcontrole als dependency: 403 voordat de body gevalideerd wordt (plan nazorg,
    # punt d). `_require_approver` in de handler blijft: die levert de identiteit van de
    # beslisser en weigert dezelfde groep (`is_tenant_admin` -> `is_admin`).
    dependencies=[Depends(_require_an_approval_right)],
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def approve_hitl(
    request_body: HITLApprovalRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    # CSRF op beide routes die STAAT WIJZIGEN (ADR-036 OP-80). `get_current_user` accepteert
    # het `access_token`-cookie, dus zonder deze controle is een cross-site POST alleen door
    # `SameSite` afgedekt -- een eigenschap van de browser, geen controle van ons. Het
    # zusteroppervlak `tool_broker/hitl_router.py` kreeg hem in OP-72; deze twee waren de
    # uitzondering gebleven terwijl ze even geserveerd en even ingrijpend zijn.
    _csrf: None = Depends(validate_csrf_token),
) -> HITLResponse:
    """Approve a pending HITL request (tenant administrators only)."""
    approver = await _require_approver(current_user, db)
    tenant_id = get_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant context required")
    repo = GatekeeperRepository(db, tenant_id)

    hitl = await repo.get_hitl_by_ticket(request_body.ticket_ref)
    if not hitl:
        raise HTTPException(status_code=404, detail="HITL request not found")

    if hitl.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this HITL request")

    await _require_approver(current_user, db, hitl.agent_id, specific=True)

    if hitl.status != "pending":
        raise HTTPException(status_code=400, detail=f"HITL request already {hitl.status}")

    # Herleidbaarheid EERST: dat is een voorwaarde voor een geldige goedkeuring, en pas als er
    # een aanvrager IS heeft de vraag "ben jij het zelf" betekenis (ADR-036 OP-81).
    _require_traceable_requester(hitl)
    _refuse_self_approval(hitl, current_user)

    # `approver` en niet `request_body.approved_by`: zie `_require_approver`.
    await repo.update_hitl_status(
        hitl,
        status="approved",
        approved_by=approver,
    )

    if hitl.agent_id:
        contract_repo = GovernanceContractRepository(db, tenant_id)
        contract = await contract_repo.load_or_create(hitl.agent_id)
        contract.record_hitl_approval(
            approved_by=approver,
            action=hitl.task_id,
        )
        await contract_repo.save(contract)

    logger.info(
        "hitl_approved",
        extra={
            "tenant_id": tenant_id,
            "ticket_ref": request_body.ticket_ref,
            "approved_by": approver,
            "agent_id": hitl.agent_id,
        },
    )

    return HITLResponse(
        status="approved",
        ticket_ref=request_body.ticket_ref,
        message="HITL request approved successfully",
    )


@router.post(
    "/hitl/reject",
    response_model=HITLResponse,
    # De rolcontrole als dependency: 403 voordat de body gevalideerd wordt (plan nazorg,
    # punt d). `_require_approver` in de handler blijft: die levert de identiteit van de
    # beslisser en weigert dezelfde groep (`is_tenant_admin` -> `is_admin`).
    dependencies=[Depends(_require_an_approval_right)],
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def reject_hitl(
    request_body: HITLRejectionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    # CSRF op beide routes die STAAT WIJZIGEN (ADR-036 OP-80). `get_current_user` accepteert
    # het `access_token`-cookie, dus zonder deze controle is een cross-site POST alleen door
    # `SameSite` afgedekt -- een eigenschap van de browser, geen controle van ons. Het
    # zusteroppervlak `tool_broker/hitl_router.py` kreeg hem in OP-72; deze twee waren de
    # uitzondering gebleven terwijl ze even geserveerd en even ingrijpend zijn.
    _csrf: None = Depends(validate_csrf_token),
) -> HITLResponse:
    """Reject a pending HITL request (tenant administrators only)."""
    # Afwijzen is net zo goed een governance-besluit als goedkeuren: het legt vast dat een mens
    # de actie heeft TEGENGEHOUDEN, en dat is even zwaar bewijs.
    rejecter = await _require_approver(current_user, db)
    tenant_id = get_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant context required")
    repo = GatekeeperRepository(db, tenant_id)

    hitl = await repo.get_hitl_by_ticket(request_body.ticket_ref)
    if not hitl:
        raise HTTPException(status_code=404, detail="HITL request not found")

    if hitl.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this HITL request")

    await _require_approver(current_user, db, hitl.agent_id, specific=True)

    if hitl.status != "pending":
        raise HTTPException(status_code=400, detail=f"HITL request already {hitl.status}")

    # Ook bij AFWIJZEN: anders haalt de aanvrager zijn eigen aanvraag uit de wachtrij voordat een
    # ander mens hem heeft gezien, en verdwijnt het toezichtsspoor dat art. 14 juist eist.
    _refuse_self_approval(hitl, current_user)

    # BEWUST GEEN `_require_traceable_requester` hier, en dat is geen omissie (ADR-036 OP-81).
    #
    # DIT is de uitweg die de wachtrij niet laat vastlopen, en juist het bestaan van deze uitweg
    # is de reden dat GOEDKEUREN wel dicht mag. Een ticket waarvan niemand de aanvrager kan
    # herleiden kan nooit een geldige goedkeuring opleveren -- maar het moet de wachtrij wel
    # kunnen verlaten. Zou afwijzen hier ook blokkeren, dan was zo'n ticket permanent
    # onbeoordeelbaar en stond er niets meer tegenover: geen goedkeuring EN geen afwijzing is
    # geen menselijk toezicht, alleen stilstand.
    #
    # Afwijzen kan die kant op veilig openstaan omdat het de MINST bevoorrechte uitkomst is: het
    # verleent geen enkel recht en laat de HIGH-risk actie juist NIET gebeuren. Het bewijs dat
    # art. 14 vraagt (een mens heeft tegengehouden) blijft intact, want `rejected_by` komt nog
    # steeds uit het token.

    await repo.update_hitl_status(
        hitl,
        status="rejected",
        rejected_by=rejecter,
        rejection_reason=request_body.reason,
    )

    logger.info(
        "hitl_rejected",
        extra={
            "tenant_id": tenant_id,
            "ticket_ref": request_body.ticket_ref,
            "rejected_by": rejecter,
        },
    )

    return HITLResponse(
        status="rejected",
        ticket_ref=request_body.ticket_ref,
        message="HITL request rejected",
    )
