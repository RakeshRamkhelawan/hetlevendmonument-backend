# orphan:exempt reason: sub-router samengesteld door auth/router.py (ADR-033 Laag 1)
"""Login, token, and account lockout endpoints."""

import os

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from src.core.api.auth.schemas import ErrorResponse, TokenResponse, UserResponse
from src.core.auth import jwt_handler
from src.core.auth.api_deps import get_current_user, is_admin, OAuth2Scope
from src.core.auth.models.account_lockout import AccountLockout
from src.core.auth.oauth2_service import oauth2_service
from src.core.models.rbac_models import Role, RolePermission, User, user_roles
from src.core.security.input_validation import InputValidationError
from .auth_config import auth_limiter
from .dependencies import (
    SecurityEvent,
    adopt_tenant,
    get_db,
    log_security_event,
    pre_auth_lookup,
)

LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION = 900

router = APIRouter(tags=["Authentication"])


# =============================================================================
# ACCOUNT LOCKOUT HELPER FUNCTIONS
# =============================================================================


async def get_or_create_lockout_record(
    db: AsyncSession,
    user_id: int,
    ip_address: str,
    tenant_id: int,
    user_agent: str | None = None,
) -> AccountLockout:
    """Get or create an account lockout record for a user.

    Waarom dit nauw luistert (ADR-036 OP-131): er is GEEN unique constraint op `user_id`.
    Wordt een bestaand record niet gevonden, dan komt er bij elke mislukte poging een
    NIEUWE rij met `failed_attempts=0` bij die naar 1 wordt opgehoogd. De teller komt dan
    nooit boven 1, het account gaat nooit op slot, en de brute-force-beveiliging staat uit
    zonder dat er iets faalt of gelogd wordt.

    **`tenant_id` is sinds OP-154 stap 2 verplicht en expliciet.** Deze functie draaide op
    een `TenantFilterBypass` -- "zie alles" -- terwijl de aanroeper de tenant altijd al
    weet. Met de tenant aangenomen is de opzoeking gewoon afgeschermd tot die ene klant, en
    hoeft er niets omzeild te worden.

    Gemeten 2026-09-15: deze functie had op dat moment GEEN aanroeper in `src/` -- hij wordt
    alleen doorgeexporteerd via `router.py:9`. De signatuur is daarom veilig uitgebreid. Was
    hij zo blijven staan, dan had de eerste aanroeper na de omschakeling naar
    `sanskritisetu_app` een stille storing gekregen: lezen binnen de bypass, schrijven
    erbuiten, nul rijen geraakt.
    """
    async with adopt_tenant(db, tenant_id):
        result = await db.execute(select(AccountLockout).where(AccountLockout.user_id == user_id))
        lockout = result.scalar_one_or_none()

        if not lockout:
            lockout = AccountLockout(
                user_id=user_id,
                failed_attempts=0,
                ip_address=ip_address,
                user_agent=user_agent or "unknown",
            )
            db.add(lockout)
            await db.flush()

        # De commit staat BINNEN het blok. Zonder dit geeft deze functie een levend
        # ORM-object terug aan een aanroeper die buiten elke tenantcontext draait, en de
        # zusterhelper `increment_failed_attempts(db, lockout)` doet dan precies wat daar
        # niet mag: muteren en committen zonder tenant. Gevonden door de Gate 2-review van
        # 2026-09-15; er is vandaag geen aanroeper, maar dat maakte het een val met een
        # strik erom in plaats van geen bevinding.
        await db.commit()

    return lockout


async def is_account_locked(lockout: AccountLockout) -> bool:
    """Check if account is currently locked."""
    if lockout.locked_until is None:
        return False

    is_still_locked = datetime.now(timezone.utc) < lockout.locked_until
    return is_still_locked


async def increment_failed_attempts(db: AsyncSession, lockout: AccountLockout) -> bool:
    """
    Increment failed login attempts and lock account if threshold reached.

    Returns:
        True if account is now locked, False otherwise
    """
    lockout.failed_attempts += 1
    lockout.last_attempt_at = datetime.now(timezone.utc)

    if lockout.failed_attempts >= LOCKOUT_THRESHOLD:
        lockout.locked_until = datetime.now(timezone.utc) + timedelta(seconds=LOCKOUT_DURATION)

    await db.flush()
    return lockout.failed_attempts >= LOCKOUT_THRESHOLD


async def reset_failed_attempts(db: AsyncSession, lockout: AccountLockout) -> None:
    """Reset failed login attempts after successful login."""
    lockout.failed_attempts = 0
    lockout.locked_until = None
    lockout.last_attempt_at = datetime.now(timezone.utc)
    await db.flush()


# =============================================================================
# HELPERS
# =============================================================================


async def _get_user_scopes(user: User) -> list[str]:
    """Helper to map roles to scopes"""
    scopes = [OAuth2Scope.USERS_READ.value]

    if user.roles:
        role_names = [r.name.lower() for r in user.roles]
        if "admin" in role_names:
            # GEEN `ADMIN_ALL` meer op ROLNAAM (ADR-036 OP-186). Hier stond
            # `OAuth2Scope.ADMIN_ALL.value` in deze lijst, waardoor elke rol die toevallig
            # `admin` heet een loper in het token kreeg -- zonder dat de database ooit werd
            # geraadpleegd. Dat is precies het pad waarlangs een zelfgemaakte rol volledige
            # macht gaf (het OP-185-primitief).
            #
            # Endpoints die `admin:*` eisen blijven bereikbaar voor een ECHTE beheerder: die
            # scope wordt afgehandeld door de databasefallback in `scope_validator`, waar
            # een rol met een `*`/`*`-permissierij hem oplevert. Gemeten 2026-09-15: de rol
            # `admin` draagt die rij en heeft de twee bestaande beheerders.
            scopes.extend(
                [
                    OAuth2Scope.USERS_WRITE.value,
                    OAuth2Scope.WORKFLOWS_READ.value,
                    OAuth2Scope.WORKFLOWS_WRITE.value,
                ]
            )
        elif "user" in role_names:
            scopes.extend([OAuth2Scope.WORKFLOWS_READ.value, OAuth2Scope.WORKFLOWS_WRITE.value])

    return list(set(scopes))


# =============================================================================
# LOGIN (OAuth2 Standard)
# =============================================================================


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
    },
    description="OAuth2 Password Flow Login",
)
@router.post(
    "/token",
    response_model=TokenResponse,
    include_in_schema=False,
)
@auth_limiter.limit("5/minute")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Standard OAuth2 Login with Account Lockout Protection.
    """
    # SEC-007: Input validation for login
    from src.core.shared.wachtwoordregels import MAX_LENGTE, MIN_LENGTE
    from src.core.security.input_validation import validate_email

    raw_username = form_data.username.strip()
    if raw_username.lower() == "admin" or "@" not in raw_username:
        lookup_username = "admin@levendmonument.nl" if raw_username.lower() == "admin" else f"{raw_username}@levendmonument.nl"
    else:
        lookup_username = raw_username

    try:
        email = validate_email(lookup_username)
        # Alleen de lengte. Een wachtwoord komt nooit in een query maar wordt gehasht vergeleken; het
        # patroonfilter voor zoekvelden (validate_input) weigerde hier een gekozen `#`, `'`, `--` of
        # `=...;` met "password contains invalid characters" (gemeten 2026-10-16).
        password = form_data.password
        if not MIN_LENGTE <= len(password) <= MAX_LENGTE:
            raise InputValidationError(
                f"password must be between {MIN_LENGTE} and {MAX_LENGTE} characters"
            )
    except InputValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        # ADR-036 OP-154 stap 2. De opzoeking op e-mailadres gebeurt VOOR authenticatie en
        # dus zonder tenantcontext; daarvoor is `pre_auth_lookup`. Zodra de gebruiker is
        # gevonden weten we zijn tenant, en vanaf dat punt draait de REST van deze functie
        # gewoon afgeschermd tot die ene tenant -- er valt dan niets meer te omzeilen.
        #
        # Een ECHT `async with adopt_tenant(...)`-blok en geen `AsyncExitStack`. De eerste
        # versie gebruikte een stack om deze functie niet te hoeven laten inspringen -- een
        # reden van gemak. Gevolg: `test_auth_router_queries_bypass_the_tenant_filter` zag
        # de queries hierbinnen als ONBESCHERMD, omdat ze syntactisch in geen enkel
        # afschermend blok staan. De guard oprekken zodat mijn constructie erdoor past zou
        # hem hol maken; het blok expliciet maken lost het echt op. Daarom is de
        # "niet gevonden"-tak naar voren gehaald en eindigt die met een 401.
        async with pre_auth_lookup(db) as opzoeker:
            gevonden = (
                await opzoeker.execute(
                    select(User.id, User.tenant_id).where(User.email.in_([email, raw_username]))
                )
            ).first()

        if not gevonden:
            # Log failure if user not found
            await log_security_event(
                event_type="LOGIN_FAILED",
                ip_address=client_ip,
                details={"email": email, "reason": "user_not_found"},
                threat_level="medium",
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        async with adopt_tenant(db, gevonden.tenant_id):
            # Nu pas het volledige object laden, op de GEWONE sessie. Het object uit
            # `pre_auth_lookup` hoort bij een andere sessie en mag hier niet gebruikt
            # worden: een wijziging daarop raakt nul rijen zonder foutmelding.
            user = (
                await db.execute(
                    select(User)
                    .where(User.id == gevonden.id)
                    .options(
                        load_only(
                            User.id,
                            User.tenant_id,
                            User.email,
                            User.hashed_password,
                            User.is_active,
                            # `is_superuser` MOET in deze lijst (ADR-036 OP-193). De
                            # beheerdersvlag in de respons gebruikt de superuser-bypass van
                            # `is_admin()`, en een kolom die hier ontbreekt is niet
                            # afwezig maar UITGESTELD: SQLAlchemy probeert hem alsnog te
                            # laden zodra je hem leest, en dat is in een asynchrone sessie
                            # een `MissingGreenlet` -- dus een 500 op het inlogpad, niet
                            # een lege waarde.
                            #
                            # Gemeten 2026-09-19: zonder deze regel gaven
                            # `tests/unit/test_neo_account_lockout.py` twee 500's op een
                            # geldige login. Geen type-checker ziet dit; alleen de
                            # volledige poort.
                            User.is_superuser,
                        ),
                        selectinload(User.roles).load_only(Role.id, Role.name),
                    )
                )
            ).scalar_one_or_none()

            if user is None:
                # De rij kan tussen de twee opzoekingen zijn verdwenen. Luid falen: een
                # inlogpoging die niets vindt mag nooit een 200 opleveren.
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password",
                )

            # De tenant is aangenomen, dus deze opzoeking heeft geen bypass meer nodig:
            # het lockout-record hoort bij deze gebruiker en dus bij deze tenant.
            lockout_result = await db.execute(
                select(AccountLockout).where(AccountLockout.user_id == user.id)
            )
            lockout = lockout_result.scalar_one_or_none()

            if not lockout:
                lockout = AccountLockout(
                    user_id=user.id,
                    failed_attempts=0,
                    last_attempt_at=datetime.now(timezone.utc),
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                db.add(lockout)
                await db.flush()

            # Check if account is locked
            now = datetime.now(timezone.utc)
            if lockout.locked_until is not None:
                # Handle both timezone-aware and naive datetimes (SQLite loses timezone info)
                locked_until = lockout.locked_until
                if locked_until.tzinfo is None:
                    locked_until = locked_until.replace(tzinfo=timezone.utc)

                if now < locked_until:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Account locked due to too many failed login attempts.",
                    )

            # Verify password
            if not await jwt_handler.verify_password(password, user.hashed_password):
                # Increment failed attempts
                lockout.failed_attempts += 1
                lockout.last_attempt_at = datetime.now(timezone.utc)

                if lockout.failed_attempts >= LOCKOUT_THRESHOLD:
                    lockout.locked_until = datetime.now(timezone.utc) + timedelta(
                        seconds=LOCKOUT_DURATION
                    )

                await db.flush()

                await log_security_event(
                    event_type="LOGIN_FAILED",
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    ip_address=client_ip,
                    details={"email": email, "reason": "invalid_password"},
                    threat_level="medium",
                    db=db,
                )

                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password",
                )

            # Geblokkeerd IP (acceptant ronde 3, N3). De SecurityMiddleware laat de loginroute
            # vanaf een geblokkeerd adres door tot HIER en zet dan `ip_blokkade_seconden`. Na
            # een geldig wachtwoord krijgt alleen een ACTIEVE beheerder een token -- anders kon
            # niemand op dat adres ooit deblokkeren. Iedereen anders krijgt dezelfde 403 als
            # elders, VOOR de lockout wordt teruggezet: een aanvaller met een gewoon account
            # komt er dus niet doorheen.
            blokkade = getattr(request.state, "ip_blokkade_seconden", None)
            if blokkade is not None:
                rolnamen_blok = [role.name for role in user.roles] if user.roles else []
                if not (
                    user.is_active
                    and (is_admin(SimpleNamespace(roles=rolnamen_blok)) or is_admin(user))
                ):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="IP blocked",
                        headers={"Retry-After": str(blokkade)},
                    )
                logger.warning(
                    "Beheerder %s logt in vanaf een geblokkeerd adres %s", user.id, client_ip
                )

            # Success! Reset attempts
            lockout.failed_attempts = 0
            lockout.locked_until = None
            lockout.last_attempt_at = datetime.now(timezone.utc)
            await db.flush()

            # Audit Log Success
            await log_security_event(
                event_type=SecurityEvent.LOGIN_SUCCESS,
                user_id=user.id,
                tenant_id=user.tenant_id,
                ip_address=client_ip,
                details={"email": user.email},
                threat_level="low",
                db=db,
            )

            if not user.is_active:
                raise HTTPException(status_code=400, detail="Inactive user")

            # Generate Tokens
            scopes = await _get_user_scopes(user)
            tokens = await oauth2_service.create_tokens(
                user_id=user.id,
                email=user.email,
                role_ids=[r.id for r in user.roles] if user.roles else [],
                scopes=scopes,
                tenant_id=user.tenant_id,
            )

            # Set HttpOnly cookies
            is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
            secure_flag = is_production or request.url.scheme == "https"
            samesite: Literal["lax", "strict"] = "strict" if is_production else "lax"

            response.set_cookie(
                key="access_token",
                value=tokens["access_token"],
                httponly=True,
                secure=secure_flag,
                samesite=samesite,
                max_age=int(tokens["expires_in"]),
                path="/",
            )

            # Refresh token cookie (longer-lived)
            refresh_max_age = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")) * 86400
            response.set_cookie(
                key="refresh_token",
                value=tokens["refresh_token"],
                httponly=True,
                secure=secure_flag,
                samesite=samesite,
                max_age=refresh_max_age,
                # Niet alleen `/refresh`: de cookie moet ook bij `/logout` aankomen, anders kan
                # uitloggen het refresh-token niet intrekken (beveiligingsnazorg 2026-10-14).
                path="/api/v1/auth",
            )

            # Build user response directly from the ORM object so the frontend can
            # hydrate auth state without an extra /me round-trip.
            #
            # `is_admin` MOET hier ook gezet worden, en niet alleen in `get_me` (ADR-036
            # OP-193). De comment hierboven zegt het zelf: de frontend vult zijn store uit
            # DIT object en doet daarna geen `/me`-aanroep. Zonder deze regel krijgt een
            # beheerder die via het formulier inlogt de Pydantic-default `False`, en wordt
            # hij tot de volgende volledige paginaherlading op alle zeven beheerdersroutes
            # naar `/forbidden` gestuurd -- precies de storing die OP-193 oplost, alleen
            # verplaatst naar het inlogpad. Gevonden door de Gate 2-security-review.
            #
            # En let op WAT er wordt doorgegeven. `is_admin()` telt alleen rolnamen die een
            # STRING zijn (`_has_admin_role_name`, dependencies.py:642 filtert op
            # `isinstance(r, str)`). `user` is hier het ORM-object en `user.roles` is een
            # relatie naar `Role`-OBJECTEN, dus `is_admin(user)` zou de rolnaam-helft
            # overslaan en alleen nog superusers herkennen -- stil, met een bool die klopt
            # van vorm en onwaar is van inhoud. Daarom gaan de NAMEN erin, samen met
            # `is_superuser` voor de bypass-helft.
            rolnamen = [role.name for role in user.roles] if user.roles else []
            user_response = UserResponse(
                id=user.id,
                email=user.email,
                is_active=user.is_active,
                tenant_id=user.tenant_id,
                roles=rolnamen,
                role_id=user.roles[0].id if user.roles else None,
                scopes=scopes,
                # Twee aanroepen, en geen enkele eigen leesactie op `is_superuser`.
                #
                # `is_admin()` heeft twee helften en elke helft wil een andere vorm:
                # de rolnaam-helft telt alleen STRINGS (op het ORM-object zijn `user.roles`
                # objecten), de superuser-helft leest `is_superuser` (dat staat WEL op het
                # ORM-object). Door beide vormen langs de centrale functie te halen doet
                # zij al het lezen, en blijft de vlag hier ongelezen.
                #
                # Hier stond eerst `is_superuser=getattr(user, "is_superuser", False)`.
                # Dat werkte, maar het is een eigen besluit op de superuser-as -- precies
                # wat `test_de_superuservlag_heeft_een_definitie.py` verbiedt (ADR-036
                # OP-189). Die guard MISTE het bovendien, want hij herkent alleen
                # `x.is_superuser` en niet de getattr-vorm met een string. Op een blinde
                # vlek van een bewaker leunen is geen oplossing.
                is_admin=is_admin(SimpleNamespace(roles=rolnamen)) or is_admin(user),
                # Dezelfde helper als `get_me`, om dezelfde reden als `is_admin` hierboven: de
                # frontend vult zijn store uit DIT object. Zonder deze regel was de lijst leeg
                # en zag niemand direct na het inloggen een schrijfknop (acceptant ronde 3, N2).
                permissions=await _rechten_van(db, user),
            )

            return TokenResponse(
                access_token=tokens["access_token"],
                token_type="bearer",
                expires_in=int(tokens["expires_in"]),
                refresh_token=tokens["refresh_token"],
                scope=" ".join(scopes),
                user=user_response,
            )

    except HTTPException:
        raise
    except Exception as e:
        # Teruggezet 2026-08-12. Hier stond `logger.exception("Login error: {e}")` -- een f-string
        # zonder de `f`, dus loguru logde letterlijk `Login error: {e}` en de echte foutmelding
        # verdween, samen met het exception-type. Nagemeten met loguru zelf. Dit is precies wat
        # `.claude/rules/backend-patterns.md` regel 10 verbiedt.
        logger.error("Login error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/me",
    response_model=UserResponse,
    description="Get current authenticated user details",
)
async def get_me(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """
    Returns the current authenticated user's details.
    Uses the unified get_current_user dependency.

    **Waarom hier een expliciete constructie staat en geen `return current_user`**
    (ADR-036 OP-193). `current_user` is de gelijknamige klasse uit
    `src/core/auth/auth_service.py:133`, niet het responsemodel van deze route
    (`src/core/api/auth/schemas.py`). FastAPI perst het ene door het andere met
    `from_attributes`, en `is_admin` bestaat niet als attribuut op het bronobject. Een
    kale `return current_user` levert daardoor de DEFAULT op: `false` voor iedereen, ook
    voor een echte beheerder -- stil, en een test die alleen kijkt of het veld bestaat
    gaat daar groen doorheen.

    `is_admin(current_user)` wordt bewust op het BRONobject aangeroepen en niet op het
    responsemodel: `is_admin()` leest naast de rolnamen ook `is_superuser`, en dat veld
    bestaat wel op `auth_service.UserResponse` en niet op het responsemodel hier. Andersom
    zou een platform-superuser zonder beheerdersrolnaam `is_admin=false` te horen krijgen
    terwijl de backend hem wel binnenlaat.
    """
    # `model_validate(..., from_attributes=True)` en NIET veld voor veld met de hand.
    #
    # Dit is precies wat FastAPI zelf deed toen hier `return current_user` stond, dus de
    # serialisatie blijft identiek en er komt alleen `is_admin` bij. Een handmatige
    # constructie is STRENGER dan die coercie, en dat brak een pad: de eerste versie las
    # `current_user.role_id` en `current_user.scopes` rechtstreeks, terwijl het bronobject
    # die velden niet hoeft te hebben -- ze zijn optioneel met een default. In de
    # contracttests levert de `get_current_user`-override een `SimpleNamespace` met alleen
    # id, email, tenant_id, roles en is_superuser, en dan gaf `/auth/me` een AttributeError
    # en dus een 500. Gemeten door de volledige poort
    # (`tests/contracts/test_api_contracts.py::TestAuthAPIContracts::test_auth_me_response_schema`);
    # de gerichte tests met een volledig bronobject gingen er groen doorheen.
    #
    # Les die hier hoort te blijven staan: een responsemodel met de hand opbouwen neemt de
    # tolerantie weg die FastAPI's coercie wel heeft, en die tolerantie was hier gedrag
    # waar iets op leunde -- geen slordigheid.
    return UserResponse.model_validate(current_user, from_attributes=True).model_copy(
        update={
            "is_admin": is_admin(current_user),
            "permissions": await _rechten_van(db, current_user),
        }
    )


async def _rechten_van(db: AsyncSession, gebruiker: object) -> list[str]:
    """De `resource:action`-rechten van de gebruiker, via zijn actieve rollen in zijn tenant.

    Dezelfde bron als `RBACService.user_has_permission` (rollen -> role_permissions), zodat de
    knoppen in de frontend het oordeel van de backend volgen. Zonder id of tenant: een lege
    lijst, dus geen knoppen (fail-closed voor de UI; de backend beslist toch per route).

    In `adopt_tenant`: onder `/api/v1/auth` wist de tenant-middleware de tenantcontext, en de
    fail-secure tenantfilter geeft een query zonder context `WHERE false`
    (tests/architecture/test_auth_router_queries_bypass_the_tenant_filter.py). De gebruiker is
    hier al vastgesteld, dus zijn tenant wordt aangenomen.
    """
    user_id = getattr(gebruiker, "id", None)
    tenant_id = getattr(gebruiker, "tenant_id", None)
    if user_id is None or tenant_id is None:
        return []
    async with adopt_tenant(db, int(tenant_id)):
        rijen = await db.execute(
            select(RolePermission.resource, RolePermission.action)
            .join(Role, Role.id == RolePermission.role_id)
            .join(user_roles, user_roles.c.role_id == Role.id)
            .where(
                user_roles.c.user_id == int(user_id),
                Role.tenant_id == int(tenant_id),
                Role.is_active,
            )
        )
    return sorted({f"{resource}:{action}" for resource, action in rijen.all()})
