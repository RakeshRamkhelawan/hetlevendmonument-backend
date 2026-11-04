# orphan:exempt reason: sub-router samengesteld door auth/router.py (ADR-033 Laag 1)
"""Password management endpoints (change, forgot, reset)."""

import secrets
from datetime import datetime, timezone
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    PasswordResetConfirm,
    UserResponse,
)
from src.core.auth.api_deps import jwt_handler, get_current_user
from src.core.config.frontend_url import frontend_url
from src.core.auth.oauth2_service import oauth2_service
from src.core.models.rbac_models import User
from .auth_config import auth_limiter
from .dependencies import (
    SecurityEvent,
    adopt_tenant,
    get_db,
    pre_auth_lookup,
    get_redis_client,
    log_security_event,
    send_password_reset_email,
)

RESET_TOKEN_EXPIRY = 3600
RESET_TOKEN_PREFIX = "password_reset:"
#: Per gebruiker het ENIGE actieve token (waarde: het token). Een nieuwe uitgifte trekt het vorige in.
RESET_USER_PREFIX = "password_reset_user:"


class _TokenOpslag(Protocol):
    """Wat de tokenhelpers van de Redis-client gebruiken (de echte client voldoet daaraan)."""

    async def get(self, name: str) -> object: ...

    async def setex(self, name: str, time: int, value: str) -> object: ...

    async def delete(self, *names: str) -> object: ...


def _als_tekst(waarde: object) -> str:
    return waarde.decode() if isinstance(waarde, bytes) else str(waarde)


async def geef_resettoken_uit(
    redis_client: _TokenOpslag, user_id: int, geldig_seconden: int
) -> str:
    """Een nieuw token voor deze gebruiker; een eerder, nog geldig token van hem wordt ongeldig.

    Een uitnodiging werkt 48 uur: een oud token dat naast een nieuw blijft werken is een lang open
    venster voor wie een doorgestuurde of gedeelde mail heeft (Gate 2 security, 2026-10-15). Daarom
    staat per gebruiker een sleutel met zijn actieve token; een nieuwe uitgifte verwijdert het vorige.
    """
    token = secrets.token_urlsafe(32)
    sleutel = f"{RESET_USER_PREFIX}{user_id}"
    vorig = await redis_client.get(sleutel)
    if vorig:
        await redis_client.delete(f"{RESET_TOKEN_PREFIX}{_als_tekst(vorig)}")
    await redis_client.setex(f"{RESET_TOKEN_PREFIX}{token}", geldig_seconden, str(user_id))
    await redis_client.setex(sleutel, geldig_seconden, token)
    return token


async def trek_resettokens_in(redis_client: _TokenOpslag, user_id: int) -> None:
    """Na een geslaagd wachtwoord: ook het actieve token van deze gebruiker is op."""
    sleutel = f"{RESET_USER_PREFIX}{user_id}"
    actief = await redis_client.get(sleutel)
    if actief:
        await redis_client.delete(f"{RESET_TOKEN_PREFIX}{_als_tekst(actief)}")
    await redis_client.delete(sleutel)


def _reset_url(reset_token: str) -> str:
    """De link in de herstelmail. Buiten een zachte omgeving geen stille terugval op localhost (zie `frontend_url`)."""
    return f"{frontend_url()}/reset-password?token={reset_token}"


async def _verstuur_herstelmail(email: str, reset_url: str) -> None:
    """De herstelmail op de achtergrond, zonder dat een mislukking stil verdwijnt.

    De route antwoordt altijd neutraal (geen enumeratie), maar een taak waarvan het resultaat wordt
    weggegooid liet een mislukte mail voor niemand zichtbaar (gemeten 2026-10-15). Het log krijgt een
    ERROR zonder adres of link.
    """
    try:
        gelukt = await send_password_reset_email(email, reset_url)
    except Exception as exc:
        # loguru: accolades, geen `%s` (dat zou letterlijk in het log komen).
        logger.opt(exception=True).error(
            "password_reset_email_failed: {}: {}", type(exc).__name__, exc
        )
        return
    if not gelukt:
        logger.error("password_reset_email_not_sent: dispatch_attempted=true")


router = APIRouter(tags=["Authentication"])

# De meldingen bij wachtwoord wijzigen en herstellen (studio deel 2): vaste Nederlandse teksten, geen ruwe servertekst.
GEBRUIKER_NIET_GEVONDEN = "Gebruiker niet gevonden"
HUIDIG_WACHTWOORD_FOUT = "Het huidige wachtwoord klopt niet"
WACHTWOORD_GEWIJZIGD = {"message": "Uw wachtwoord is gewijzigd"}
# Een ander antwoord per geval zou verraden of een token nooit bestond, verlopen is, of bij een verdwenen gebruiker hoort.
HERSTELLINK_ONGELDIG = "Deze herstellink is ongeldig of verlopen"
WACHTWOORD_HERSTELD = {"message": "Uw wachtwoord is hersteld"}
HERSTEL_MISLUKT = "Het wachtwoord kon niet worden hersteld. Probeer het opnieuw."

# Een antwoord voor elk geval (bestaand adres, onbekend adres, fout): een verschil zou verraden welke adressen bestaan.
HERSTEL_ANTWOORD: dict[str, str] = {
    "message": "Als dit adres bij ons bekend is, hebt u een e-mail met een herstellink ontvangen."
}


# =============================================================================
# PASSWORD MANAGEMENT ENDPOINTS
# =============================================================================


@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
    description="Change password for authenticated user",
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Change password for authenticated user.
    Requires current password verification.
    """
    # Fetch full User model from database (UserResponse doesn't have hashed_password)
    #
    # De opzoeking moet buiten de tenantfilter om (ADR-036 OP-131, OP-154 stap 2). Dit
    # endpoint valt onder `/api/v1/auth` en dat pad gaat door de PUBLIEKE DOORLAAT van de
    # tenant-middleware, die de tenantcontext juist WIST (`tenant_middleware.py:344`). Er is
    # dus geen tenant in de ContextVar, en de fail-secure tenantfilter plakt `WHERE false`
    # aan deze SELECT -- een ingelogde gebruiker vindt dan zijn eigen record niet en dit
    # endpoint geeft altijd 404.
    #
    # Hier stond dat `/api/v1/auth` in `EXCLUDED_PREFIXES` staat. Dat is ONWAAR en is
    # nagemeten op 2026-09-15: er zijn twee zulke lijsten in `src/`
    # (`tenant_middleware.py:98` en `rate_limit_middleware.py:219`) en in geen van beide
    # staat een auth-pad. De conclusie klopte, het genoemde mechanisme niet.
    #
    # Het id komt uit een geverifieerde JWT, niet uit invoer, dus dit opent geen deur die de
    # authenticatie niet al heeft geopend.
    async with pre_auth_lookup(db) as opzoeker:
        gevonden = (
            await opzoeker.execute(
                select(User.id, User.tenant_id).where(User.id == current_user.id)
            )
        ).one_or_none()
    if not gevonden:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GEBRUIKER_NIET_GEVONDEN)

    gebruiker_id, tenant_id = gevonden

    # Vanaf hier is de tenant bekend en is er niets meer te omzeilen: laden, controleren en
    # opslaan gebeuren op de gewone sessie, afgeschermd tot die ene tenant.
    async with adopt_tenant(db, tenant_id):
        db_user = (
            await db.execute(select(User).where(User.id == gebruiker_id))
        ).scalar_one_or_none()
        if not db_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GEBRUIKER_NIET_GEVONDEN)

        # Verify current password
        is_valid = await jwt_handler.verify_password(data.current_password, db_user.hashed_password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=HUIDIG_WACHTWOORD_FOUT,
            )

        # Hash new password
        new_hashed = await jwt_handler.hash_password(data.new_password)

        # Update user
        db_user.hashed_password = new_hashed
        # Alle eerder uitgegeven toegangs- en verversingstokens vervallen, in dezelfde transactie als het nieuwe
        # wachtwoord: ook het token waarmee dit verzoek binnenkwam. De frontend moet dus opnieuw inloggen.
        await oauth2_service.trek_alle_tokens_in(gebruiker_id, db, reason="password_change")
        await db.commit()
        await log_security_event(
            event_type="PASSWORD_CHANGED",
            user_id=gebruiker_id,
            tenant_id=tenant_id,
            request_path="/api/v1/auth/change-password",
            request_method="POST",
            details={"sessions_revoked": True},
            threat_level="low",
            db=db,
        )

    logger.info("password_change_success: user_id=%s", gebruiker_id)
    return WACHTWOORD_GEWIJZIGD


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    description="Initiate password reset flow",
)
@auth_limiter.limit("3/minute")
async def forgot_password(
    data: ForgotPasswordRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Request password reset for email address.
    Always returns 200 to prevent email enumeration.

    SECURITY FIX: Now properly generates and stores reset token in Redis.
    """
    try:
        # Opzoeken via de aparte verbinding, daarna de klant AANNEMEN (OP-154 stap 2b).
        #
        # Hier stond `TenantFilterBypass`, met als reden dat dit endpoint publiek is en er
        # geen klant is om op te filteren (OP-131). Die reden klopt, maar de oplossing werkt
        # alleen zolang de applicatie als tabeleigenaar verbindt: `TenantFilterBypass` zet
        # de ORM-hook uit, en PostgreSQL trekt zich daar niets van aan. Onder
        # `sanskritisetu_app` geeft deze SELECT nul rijen -- en deze route geeft PER ONTWERP
        # altijd 200, dus niemand merkt dat wachtwoordherstel stuk is. Het stilste faalpad
        # van de zeven.
        #
        # Er wordt alleen `id` en `tenant_id` gelezen; al het andere gebeurt daarna op de
        # gewone sessie binnen de aangenomen klant. Zo houdt de omzeilrol leesrecht op vier
        # tabellen en krijgt hij nooit schrijfrechten.
        #
        # `.one_or_none()`, en dat laat een bestaand gat BEWUST open staan.
        #
        # `users.email` is alleen uniek PER KLANT (`rbac_models.py:348`,
        # `idx_user_tenant_email`). Deze opzoeking gaat over alle klanten heen, dus bij
        # hetzelfde adres bij twee klanten werpt dit `MultipleResultsFound`. Dat wordt
        # opgevangen door de `except Exception` hieronder en de route geeft dan de neutrale
        # melding zonder een token te versturen: wachtwoordherstel werkt voor die
        # gebruikers niet, en dat is vandaag ook al zo.
        #
        # Een eerdere versie van deze regel gebruikte `.first()` om dat op te lossen. Dat
        # is FOUT en is dezelfde dag teruggedraaid: `.first()` kiest stil een willekeurige
        # klant en stuurt dus een hersteltoken voor een account dat de aanvrager mogelijk
        # niet bedoelt. Bij een dubbel adres is er geen goed antwoord af te leiden; dan is
        # niets doen de veilige uitkomst. Het echte antwoord is een aparte beslissing --
        # bijvoorbeeld de klant meegeven bij het herstelverzoek -- en hoort niet in deze
        # omzetting thuis.
        async with pre_auth_lookup(db) as opzoeker:
            gevonden = (
                await opzoeker.execute(
                    select(User.id, User.tenant_id).where(User.email == data.email)
                )
            ).one_or_none()

        if gevonden:
            gebruiker_id, tenant_id = gevonden
            # Een veilig token, in Redis met een einddatum; een eerder token van deze gebruiker vervalt.
            redis_client = await get_redis_client()
            reset_token = await geef_resettoken_uit(redis_client, gebruiker_id, RESET_TOKEN_EXPIRY)

            reset_url = _reset_url(reset_token)
            # Fire-and-forget to normalize response time (prevents enumeration)
            import asyncio

            asyncio.create_task(_verstuur_herstelmail(data.email, reset_url))
            logger.info("password_reset_requested: dispatch_attempted=true")

            # Log security event
            # De auditregel BINNEN de aangenomen klant. `log_security_event` komt uit bij
            # `AuditService.log_event`, en die neemt een advisory lock op de klant; dan
            # hoort die klant ook de context van de transactie te zijn.
            async with adopt_tenant(db, tenant_id):
                await log_security_event(
                    event_type=SecurityEvent.PASSWORD_RESET_REQUESTED,
                    user_id=gebruiker_id,
                    tenant_id=tenant_id,
                    request_path="/api/v1/auth/forgot-password",
                    request_method="POST",
                    details={},
                    threat_level="low",
                    db=db,
                )

        # Always return success to prevent email enumeration
        return HERSTEL_ANTWOORD

    except Exception as exc:
        logger.error("forgot_password_error: %s", exc)
        # Still return success to prevent enumeration
        return HERSTEL_ANTWOORD


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    description="Reset password with valid reset token",
)
@auth_limiter.limit("5/minute")
async def reset_password(
    data: PasswordResetConfirm,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Reset password using a valid reset token.

    SECURITY FIX: Now properly validates token via Redis lookup and updates password.
    """
    try:
        # Validate token via Redis
        redis_client = await get_redis_client()
        user_id = await redis_client.get(f"{RESET_TOKEN_PREFIX}{data.token}")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=HERSTELLINK_ONGELDIG,
            )

        # Opzoeking VOOR authenticatie (ADR-036 OP-131, OP-154 stap 2). Dit endpoint is
        # publiek en er is geen tenantcontext; het id komt uit Redis, gezet door
        # `forgot_password` bij het uitgeven van het token -- niet uit de invoer van de
        # aanroeper.
        #
        # Alleen `id` en `tenant_id` worden hier afgelezen. Het object zelf gaat NIET mee
        # naar buiten dit blok: bij een ingerichte bypass hoort het bij een andere sessie,
        # en een wijziging daarop raakt nul rijen zonder foutmelding. Gemeten 2026-09-15:
        # `UPDATE ... -> 0 rijen`, commit slaagt, wachtwoord ongewijzigd, HTTP 200.
        async with pre_auth_lookup(db) as opzoeker:
            gevonden = (
                await opzoeker.execute(
                    select(User.id, User.tenant_id).where(User.id == int(user_id))
                )
            ).one_or_none()

        if not gevonden:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=HERSTELLINK_ONGELDIG,
            )

        gebruiker_id, tenant_id = gevonden

        # Vanaf hier weten we bij welke tenant deze gebruiker hoort, dus is er niets meer te
        # omzeilen: het laden EN het opslaan gebeuren op de gewone sessie, netjes binnen de
        # grenzen van die ene tenant. Daardoor hoeft de bypass-rol nooit schrijfrechten.
        async with adopt_tenant(db, tenant_id):
            user = (
                await db.execute(select(User).where(User.id == gebruiker_id))
            ).scalar_one_or_none()
            if not user:
                # Kan alleen als de rij tussen beide opzoekingen is verdwenen. Luid falen,
                # niet stil doorgaan: een herstel dat niets opslaat mag geen 200 geven.
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=HERSTELLINK_ONGELDIG,
                )

            from src.core.security.crypto_utils import hash_password_sync

            user.hashed_password = hash_password_sync(data.new_password)
            user.updated_at = datetime.now(timezone.utc)

            # Invalidate token, en elk ander actief token van deze gebruiker
            await redis_client.delete(f"{RESET_TOKEN_PREFIX}{data.token}")
            await trek_resettokens_in(redis_client, gebruiker_id)
            # Alle eerder uitgegeven toegangs- en verversingstokens vervallen, in dezelfde transactie als het nieuwe
            # wachtwoord: wie het account had (ook een aanvaller met een gestolen sessie) valt eruit.
            await oauth2_service.trek_alle_tokens_in(gebruiker_id, db, reason="password_reset")

            # Commit changes
            await db.commit()

            # De auditschrijf staat BINNEN het aangenomen venster, en dat is geen detail.
            # Stond hij erbuiten (zoals voorheen), dan begint hij een NIEUWE transactie
            # waarin de listener de herstelde -- lege -- tenant zet. Onder
            # `sanskritisetu_app` is dat straks een INSERT zonder tenantcontext op
            # `audit_logs`, die `best_effort` stil inslikt: `PASSWORD_RESET_COMPLETED`
            # verdwijnt dan uit het auditspoor van precies de handeling waar dat het meest
            # telt. Gevonden door de Gate 2-review van 2026-09-15.
            await log_security_event(
                event_type=SecurityEvent.PASSWORD_RESET_COMPLETED,
                user_id=user.id,
                tenant_id=user.tenant_id,
                request_path="/api/v1/auth/reset-password",
                request_method="POST",
                details={"sessions_revoked": True},
                threat_level="low",
                db=db,
            )

        logger.info("password_reset_completed: user_id=%s", user.id)
        return WACHTWOORD_HERSTELD

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("reset_password_error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=HERSTEL_MISLUKT,
        )
