"""
Authentication Service - Production Implementation
Database operaties voor user authenticatie zoals gespecificeerd in FASE 1 STAP 1.2
"""

from datetime import datetime, timezone

from loguru import logger
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.auth.jwt_handler import jwt_handler
from src.core.shared.wachtwoordregels import controleer_gekozen_wachtwoord
from src.core.models.rbac_models import Role, User, user_roles
from src.core.governance.services.audit_service import log_security_event

#: De enige rolnaam die een publieke aanmelding krijgt. Server-side gezet, nooit uit
#: een request-body -- zie RegistrationRequest en ADR-036 OP-184.
DEFAULT_ROLE_NAME = "user"


class _Aanmeldgegevens(BaseModel):
    """E-mail plus wachtwoord, met de wachtwoordcontrole op een plek.

    Bestaat sinds 2026-09-11 (ADR-036 OP-184) om het PUBLIEKE verzoek en het INTERNE
    aanmaakmodel te kunnen scheiden zonder de wachtwoordcontrole te dupliceren. Een
    tweede kopie van die controle zou uit elkaar gaan lopen, en dat is precies de
    fout die dit bestand al een keer heeft gemaakt met vier klassen die UserCreate
    heten.
    """

    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Enforce strong password requirements

        Requirements:
        - Min 8 characters
        - At least 1 uppercase letter
        - At least 1 lowercase letter
        - At least 1 digit
        - ASCII-only characters

        De regels staan op EEN plek (`wachtwoordregels.py`), samen met herstellen en wijzigen.
        """
        return controleer_gekozen_wachtwoord(v)


class RegistrationRequest(_Aanmeldgegevens):
    """Het PUBLIEKE registratieverzoek: e-mail en wachtwoord, en niets anders.

    ADR-036 OP-184. Tot 2026-09-11 bond POST /api/v1/auth/register het interne
    `UserCreate`, dat een veld `role_name` heeft. Gemeten: een willekeurige aanmelder
    kon daar `system_admin` in zetten, waarna het primitief in `create_user` die rol
    AANMAAKTE en toekende (OP-185), en de rolnaam bij inloggen de scope ADMIN_ALL
    opleverde (OP-186).

    `extra="forbid"` is hier het punt en niet een detail: de guard hangt aan het
    GEDRAG en niet aan de veldnaam. Een verbodslijst met "role_name" erin is te
    omzeilen door het veld `initial_profile` te noemen -- dat staat letterlijk zo in
    de rij van OP-184. Dit schema weigert daarom ELK veld dat het niet kent.
    """

    model_config = ConfigDict(extra="forbid")

    #: Weergavenaam uit het bestaande registratieformulier. MOET hier staan, ook al doet
    #: create_user er vandaag niets mee: `extra="forbid"` weigert anders het veld dat de
    #: frontend al jaren meestuurt (frontend/src/lib/api/client.ts:367 post
    #: {name, email, password}) en dan geeft /register een 422 in plaats van een 201.
    #: Gemeten door de Gate-2-reviewer op 2026-09-11; de eerste versie van dit schema had
    #: dit veld niet en brak daarmee de levende registratieflow. `full_name` staat erbij
    #: omdat src/scripts/manual_register.py dat gebruikt, en `username` voor bestaande
    #: aanroepers (zoals tests/integration/test_auth_integration_old.py).
    #: LET OP: dit zijn WEERGAVEvelden. Een rolveld hoort hier NIET bij te komen -- dat is
    #: precies wat ADR-036 OP-184 dichtzet.
    name: str | None = None
    full_name: str | None = None
    username: str | None = None


class UserCreate(_Aanmeldgegevens):
    """Het INTERNE aanmaakmodel. De rolnaam hoort hier uitsluitend SERVER-SIDE in.

    Wie dit model bouwt uit een request-body moet de rolnaam eerst valideren tegen de
    BESTAANDE rollen van de tenant -- zie het beheerderspad in
    src/core/api/v1/admin/users_router.py.
    """

    role_name: str = DEFAULT_ROLE_NAME


def get_primary_role_id(user: User) -> int | None:
    """
    Get user's primary role ID from modern many-to-many relationship.

    Args:
        user: User model instance with roles relationship

    Returns:
        Primary role ID or None
    """
    # Priority 1: Direct foreign key (role_id)
    if hasattr(user, "role_id") and user.role_id is not None:
        return int(user.role_id)

    # Priority 2: Modern many-to-many via roles relationship (user_roles junction table)
    if hasattr(user, "roles") and user.roles:
        return int(user.roles[0].id)

    # Priority 3: Legacy single role relationship
    if hasattr(user, "role") and user.role is not None:
        return int(user.role.id)

    return None


class UserResponse(BaseModel):
    """User response model"""

    id: int
    email: str
    tenant_id: int
    roles: list[str] = []  # Modern: list of role names from user_roles junction table
    role_id: int | None = None  # Legacy: for backward compatibility, populated from first role
    scopes: list[str] = []  # Added for RBAC compatibility with ToolBroker
    is_superuser: bool = False
    # Uitgeschakeld is uitgeschakeld: beide opzoekingen hieronder zetten dit expliciet uit de
    # databaserij. De default is alleen voor code die zelf een UserResponse bouwt (testdata,
    # tokenuitgifte na een geslaagde login), nooit voor een opzoeking op een token.
    is_active: bool = True

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Token response model"""

    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class AuthService:
    """
    Production-grade authentication service
    """

    def create_access_token(self, user: UserResponse) -> TokenResponse:
        """Create a TokenResponse for a user response payload."""
        primary_role = user.roles[0] if user.roles else "user"
        token = jwt_handler.create_access_token(
            data={
                "sub": user.email,
                "user_id": user.id,
                "role": primary_role,
                "tenant_id": user.tenant_id,
            }
        )
        return TokenResponse(access_token=token, user=user)

    async def create_user(
        self,
        db: AsyncSession,
        user_data: UserCreate,
        client_ip: str = "unknown",
        *,
        tenant_id: int,
        request_path: str,
        event_type: str = "USER_CREATION_FAILED",
    ) -> UserResponse | None:
        """
        Create een nieuwe gebruiker met audit logging

        `tenant_id` is VERPLICHT (ADR-036 OP-235d): hier stond een default van 1, dus een
        aanroeper die de tenant vergat resolveerde rollen in tenant 1. Gemeten 2026-09-15:
        alle vier de aanroepers gaven hem al expliciet mee, dus niemand leunde erop.

        `request_path` en `event_type` komen van de AANROEPER (ADR-036 OP-235a). Ze stonden
        hardgecodeerd op het registratiepad, op TWEE plekken in deze methode -- ook wanneer
        de aanroep van het beheerderspad kwam. Het beveiligingslogboek gaf daardoor altijd
        hetzelfde antwoord op de vraag waar een poging vandaan kwam.

        Args:
            db: Database sessie
            user_data: User data om aan te maken
            client_ip: Client IP address voor audit logging
            tenant_id: Tenant ID (default=1 for backwards compatibility)

        Returns:
            UserResponse als succesvol, anders None
        """
        try:
            # Check if user already exists in this tenant
            result = await db.execute(
                select(User).where(User.email == user_data.email).where(User.tenant_id == tenant_id)
            )
            existing_user = result.scalar_one_or_none()

            if existing_user:
                # Log failed registration (user enumeration prevention)
                # Log failed registration (user enumeration prevention)
                await log_security_event(
                    event_type=event_type,
                    user_id=None,
                    tenant_id=tenant_id,
                    request_path=request_path,
                    request_method="POST",
                    ip_address=client_ip,
                    details={
                        "reason": "email_already_exists",
                        "email": user_data.email,
                    },
                    description=f"Registration attempt with existing email: {user_data.email}",
                    threat_level="low",
                    db=db,
                )
                return None

            # Get role for this tenant (safe access to role_name)
            requested_role = getattr(user_data, "role_name", DEFAULT_ROLE_NAME)
            role_result = await db.execute(
                select(Role).where(Role.name == requested_role).where(Role.tenant_id == tenant_id)
            )
            role = role_result.scalar_one_or_none()
            if not role:
                # ADR-036 OP-185. Tot 2026-09-11 stond hier `role = Role(name=requested_role,
                # tenant_id=tenant_id); db.add(role)` -- een onbekende rolnaam werd dus
                # AANGEMAAKT en daarna toegekend. Daarmee was elk pad dat hier een
                # tekenreeks in kreeg een escalatiepad, en het publieke registratiepad was
                # zo'n pad (OP-184). Gemeten in de eigen database op 2026-09-11: er stond
                # een rol `system_admin` met nul permissierijen, een naam die NIET in
                # ensure_default_roles staat -- dit pad is dus echt gelopen.
                #
                # Nu: resolveren tegen bestaande rollen en anders WEIGEREN. Fail-secure bij
                # een vereist veld zonder correcte waarde. Aanmaken van rollen hoort bij
                # rbac_service.ensure_default_roles en bij een expliciete beheerdersactie,
                # niet bij het aanmaken van een gebruiker.
                await log_security_event(
                    event_type=event_type,
                    user_id=None,
                    tenant_id=tenant_id,
                    request_path=request_path,
                    request_method="POST",
                    ip_address=client_ip,
                    details={
                        "reason": "unknown_role_requested",
                        "requested_role": requested_role,
                        "email": user_data.email,
                    },
                    description=(
                        f"Registration refused: role '{requested_role}' does not exist in "
                        f"tenant {tenant_id}"
                    ),
                    threat_level="medium",
                    db=db,
                )
                return None

            # Hash password asynchronously (CPU-intensive bcrypt operation)
            hashed_password = await jwt_handler.hash_password(user_data.password)

            # Create user with bcrypt hashing
            # NOTE: role_id column removed from User model - roles assigned via user_roles junction table
            user = User(
                email=user_data.email,
                hashed_password=hashed_password,
                tenant_id=tenant_id,
                is_active=True,
            )

            db.add(user)
            await db.flush()  # Get user.id without committing

            # CRITICAL: Insert into user_roles junction table for RBAC
            # This is required for RBACService.has_permission() to work
            await db.execute(
                user_roles.insert().values(
                    user_id=user.id, role_id=role.id, tenant_id=user.tenant_id
                )
            )

            await db.commit()
            await db.refresh(user)

            # Refresh user to load roles relationship
            try:
                await db.refresh(user, ["roles"])
            except (KeyError, ValueError):
                # Fallback for legacy model which uses 'role' (singular)
                await db.refresh(user, ["role"])

            user_id = user.id
            user_email = user.email
            user_tenant_id = user.tenant_id
            primary_role_id = get_primary_role_id(user)

            # Log successful registration
            # Log successful registration
            await log_security_event(
                event_type="REGISTRATION_SUCCESS",
                user_id=user_id,
                tenant_id=user_tenant_id,
                request_path="/api/v1/auth/register",
                request_method="POST",
                ip_address=client_ip,
                details={
                    "user_id": user_id,
                    "email": user_email,
                    "role_id": primary_role_id,
                },
                description=f"New user registered: {user_email}",
                threat_level="low",
                db=db,
            )

            return UserResponse(
                id=user_id,
                email=user_email,
                role_id=primary_role_id,
                tenant_id=user_tenant_id,  # Always present now
                scopes=self._get_role_scopes(role.name) if role else ["user:read"],
            )

        except Exception:
            await db.rollback()
            logger.exception("User registration failed")
            raise

    async def authenticate_user(
        self, db: AsyncSession, email: str, password: str, client_ip: str = "unknown"
    ) -> UserResponse | None:
        """
        Authenticeer een gebruiker met email en wachtwoord met audit logging

        Args:
            db: Database sessie
            email: User email
            password: Plain text wachtwoord
            client_ip: Client IP address voor audit logging

        Returns:
            UserResponse als authenticatie succesvol, anders None
        """
        from sqlalchemy.orm import selectinload

        from src.core.database.bypass_session import adopt_tenant, pre_auth_lookup

        try:
            # ADR-036 OP-154 stap 2. De opzoeking op e-mailadres gebeurt VOOR authenticatie
            # en dus zonder tenantcontext; daarvoor is `pre_auth_lookup`. Er worden alleen
            # `id` en `tenant_id` afgelezen: bij een ingerichte aparte verbinding hoort het
            # object bij een ANDERE sessie, en `user.last_login = ...` + `commit()` verderop
            # zou daar nul rijen raken zonder foutmelding (gemeten 2026-09-15).
            async with pre_auth_lookup(db) as opzoeker:
                gevonden = (
                    await opzoeker.execute(
                        select(User.id, User.tenant_id).where(User.email == email)
                    )
                ).one_or_none()

            if not gevonden:
                # Log failed login (user not found)
                # Log failed login (user not found)
                await log_security_event(
                    event_type="LOGIN_FAILED",
                    user_id=None,
                    tenant_id=None,
                    request_path="/api/v1/auth/token",
                    request_method="POST",
                    ip_address=client_ip,
                    details={"reason": "user_not_found", "email": email},
                    description=f"Failed login attempt for email: {email}",
                    threat_level="medium",
                    db=db,
                )
                return None

            # Vanaf hier is de tenant bekend en valt er niets meer te omzeilen: laden,
            # controleren, bijwerken en opslaan gebeuren op de GEWONE sessie, afgeschermd
            # tot die ene tenant. Daardoor hoeft de bypass-rol nooit schrijfrechten.
            async with adopt_tenant(db, gevonden.tenant_id):
                user = (
                    await db.execute(
                        select(User)
                        .where(User.id == gevonden.id)
                        .options(selectinload(User.roles))
                    )
                ).scalar_one_or_none()
                if user is None:
                    # Verdwenen tussen de twee opzoekingen. Geen aanmelding toestaan.
                    return None

                return await self._voltooi_authenticatie(
                    db=db, user=user, password=password, client_ip=client_ip
                )

        except Exception:
            # Dekt het HELE pad, ook `adopt_tenant.__aenter__`. Een eerdere versie dekte
            # alleen het opzoekingsdeel; de Gate 2-review van 2026-09-15 heeft aangetoond
            # dat een fout bij het aannemen van de tenant (bijvoorbeeld een ongeldige
            # `tenant_id`, die `set_tenant_id` terecht weigert) dan ZONDER rollback en
            # zonder log naar buiten kwam.
            #
            # Een kapotte aparte verbinding werpt hier `BypassNietBeschikbaar`: luid, en dat
            # hoort zo -- stil terugvallen zou nul rijen geven en dus "wachtwoord onjuist".
            await db.rollback()
            logger.exception("User login failed")
            raise

    async def _voltooi_authenticatie(
        self,
        db: "AsyncSession",
        user: "User",
        password: str,
        client_ip: str | None,
    ) -> "UserResponse | None":
        """Het deel van `authenticate_user` NA het vaststellen van de gebruiker.

        Apart gezet bij ADR-036 OP-154 stap 2. De reden is niet cosmetisch: dit deel draait
        binnen `adopt_tenant(...)`, en door het in een eigen functie te zetten hoefde de
        bestaande code niet honderd regels op te schuiven. Een inspringing van die omvang
        maakt een diff onreviewbaar, en dat is in dit project eerder misgegaan.
        """
        try:
            # Verify password asynchronously (CPU-intensive bcrypt operation)
            try:
                is_valid = await jwt_handler.verify_password(password, user.hashed_password)
            except Exception as e:
                logger.error(f"Password verification exception for {user.email}: {e}")
                is_valid = False

            if not is_valid:
                # Log failed login (wrong password)
                # Log failed login (wrong password)
                await log_security_event(
                    event_type="LOGIN_FAILED",
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    request_path="/api/v1/auth/token",
                    request_method="POST",
                    ip_address=client_ip,
                    details={"reason": "invalid_password", "user_id": user.id},
                    description=f"Failed login attempt (wrong password): {user.email}",
                    threat_level="medium",
                    db=db,
                )
                return None

            # Check if account is active
            if not user.is_active:
                # Log inactive account login attempt
                # Log inactive account login attempt
                await log_security_event(
                    event_type="LOGIN_FAILED",
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    request_path="/api/v1/auth/token",
                    request_method="POST",
                    ip_address=client_ip,
                    details={"reason": "account_inactive", "user_id": user.id},
                    description=f"Login attempt for inactive account: {user.email}",
                    threat_level="medium",
                    db=db,
                )

                return None

            # Update last_login timestamp
            user.last_login = datetime.now(timezone.utc)
            await db.commit()

            # Geen `TenantFilterBypass` meer nodig (ADR-036 OP-154 stap 2): deze functie
            # draait binnen `adopt_tenant(...)`, dus de tenant staat gezet en de refresh is
            # gewoon afgeschermd tot die ene tenant. Dat is strikter dan de bypass die hier
            # eerder stond -- "zie precies een tenant" in plaats van "zie alles".
            # De rollen zijn al eager-geladen; de refresh werkt alleen de attributen bij.
            await db.refresh(user, ["roles"])

            user_id = user.id
            user_email = user.email
            user_tenant_id = user.tenant_id
            primary_role_id = get_primary_role_id(user)

            # Extract role names for UserResponse
            role_names = [role.name for role in user.roles] if user.roles else []

            # Log successful login
            # Log successful login
            await log_security_event(
                event_type="LOGIN_SUCCESS",
                user_id=user_id,
                tenant_id=user_tenant_id,
                request_path="/api/v1/auth/token",
                request_method="POST",
                ip_address=client_ip,
                details={
                    "user_id": user_id,
                    "email": user_email,
                    "role_id": primary_role_id,
                },
                description=f"Successful login: {user_email}",
                threat_level="low",
                db=db,
            )

            return UserResponse(
                id=user_id,
                email=user_email,
                roles=role_names,  # Include role names
                tenant_id=user_tenant_id,  # Always present now
                scopes=self._get_role_scopes(user.roles[0].name) if user.roles else ["user:read"],
            )

        except Exception:
            # Bewust GEEN eigen rollback/log: `authenticate_user` dekt het hele pad en doet
            # dat al. Deed deze dat ook, dan leverde elke inlogfout TWEE rollbacks en TWEE
            # identieke stacktraces op -- gevonden door de Gate 2-review van 2026-09-15.
            # Het `except` blijft staan zodat de bedoeling expliciet is en niemand hier per
            # ongeluk een tweede handler bij zet.
            raise

    async def get_user_by_id(self, db: AsyncSession, user_id: int) -> UserResponse | None:
        """
        Haal gebruiker op uit database op basis van ID

        Args:
            db: Database sessie
            user_id: User ID

        Returns:
            UserResponse als gevonden, anders None
        """
        from src.core.database.bypass_session import adopt_tenant, pre_auth_lookup

        # Opzoeken via de aparte verbinding, daarna de klant AANNEMEN (OP-154 stap 2b).
        #
        # Hier stond `TenantFilterBypass`, met als reden dat er bij tokenverificatie nog
        # geen klant bekend is. Die reden klopt, maar de oplossing werkt alleen zolang de
        # applicatie als tabeleigenaar verbindt: `TenantFilterBypass` zet de ORM-hook uit
        # en PostgreSQL trekt zich daar niets van aan. Onder `sanskritisetu_app` geeft deze
        # SELECT nul rijen en levert deze functie stil `None` op -- wat elke aanroeper leest
        # als "gebruiker bestaat niet".
        #
        # De opzoeking leest alleen `id` en `tenant_id`. Pas daarna wordt de klant
        # aangenomen en wordt de rij inclusief rollen op de gewone sessie geladen. De omzeilrol
        # houdt zo leesrecht op vier tabellen en krijgt nooit schrijfrechten, en het laden
        # van de rollen gebeurt AFGESCHERMD tot die ene klant.
        async with pre_auth_lookup(db) as opzoeker:
            gevonden = (
                await opzoeker.execute(select(User.id, User.tenant_id).where(User.id == user_id))
            ).one_or_none()

        if not gevonden:
            return None

        async with adopt_tenant(db, gevonden.tenant_id):
            user = (
                await db.execute(
                    select(User).where(User.id == gevonden.id).options(selectinload(User.roles))
                )
            ).scalar_one_or_none()

        if not user:
            return None

        return UserResponse(
            id=user.id,
            email=user.email,
            tenant_id=user.tenant_id,
            roles=[role.name for role in user.roles] if user.roles else [],
            scopes=self._get_role_scopes(user.roles[0].name) if user.roles else ["user:read"],
            is_superuser=user.is_superuser,
            is_active=bool(user.is_active),
        )

    async def get_user_by_email(self, db: AsyncSession, email: str) -> UserResponse | None:
        """
        Haal gebruiker op uit database op basis van email

        Args:
            db: Database sessie
            email: User email

        Returns:
            UserResponse als gevonden, anders None
        """
        from src.core.database.bypass_session import adopt_tenant, pre_auth_lookup

        # Opzoeken via de aparte verbinding, daarna de klant AANNEMEN (OP-154 stap 2b).
        #
        # Hier stond `TenantFilterBypass`, met als reden dat er bij tokenverificatie nog
        # geen klant bekend is. Die reden klopt, maar de oplossing werkt alleen zolang de
        # applicatie als tabeleigenaar verbindt: `TenantFilterBypass` zet de ORM-hook uit
        # en PostgreSQL trekt zich daar niets van aan. Onder `sanskritisetu_app` geeft deze
        # SELECT nul rijen en levert deze functie stil `None` op -- wat elke aanroeper leest
        # als "gebruiker bestaat niet".
        #
        # De opzoeking leest alleen `id` en `tenant_id`. Pas daarna wordt de klant
        # aangenomen en wordt de rij inclusief rollen op de gewone sessie geladen. De omzeilrol
        # houdt zo leesrecht op vier tabellen en krijgt nooit schrijfrechten, en het laden
        # van de rollen gebeurt AFGESCHERMD tot die ene klant.
        # `.one_or_none()` en NADRUKKELIJK niet `.first()`.
        #
        # `users.email` is alleen uniek PER KLANT (`rbac_models.py:348`,
        # `idx_user_tenant_email`); een globale unieke index bestaat niet. Deze opzoeking
        # gaat over alle klanten heen, dus bij hetzelfde adres bij twee klanten is er geen
        # goed antwoord: welke van de twee bedoelt de aanvrager? `.first()` zou er stil een
        # kiezen, en dat is precies hoe je iemand in de verkeerde klant laat landen.
        # `.one_or_none()` werpt dan `MultipleResultsFound` -- luid, en de aanroeper kan
        # niet per ongeluk doorgaan.
        #
        # Deze keuze is eerder in deze iteratie al een keer gemaakt op het inlogpad
        # (`.first()` teruggedraaid naar `.one_or_none()`); zij hoort hier hetzelfde te
        # zijn, anders verschilt het gedrag per route.
        async with pre_auth_lookup(db) as opzoeker:
            gevonden = (
                await opzoeker.execute(select(User.id, User.tenant_id).where(User.email == email))
            ).one_or_none()

        if not gevonden:
            return None

        async with adopt_tenant(db, gevonden.tenant_id):
            # PERFORMANCE FIX: Eager load roles to avoid N+1 query
            user = (
                await db.execute(
                    select(User).where(User.id == gevonden.id).options(selectinload(User.roles))
                )
            ).scalar_one_or_none()

        if not user:
            return None

        return UserResponse(
            id=user.id,
            email=user.email,
            tenant_id=user.tenant_id,
            roles=[role.name for role in user.roles] if user.roles else [],
            scopes=self._get_role_scopes(user.roles[0].name) if user.roles else ["user:read"],
            is_superuser=user.is_superuser,
            is_active=bool(user.is_active),
        )

    async def account_is_active(self, db: AsyncSession, subject: str, tenant_id: int) -> bool:
        """Is dit account (nog) ingeschakeld? Onbekend of uitgezet is `False`.

        Voor ingangen die alleen de claims van een token hebben en geen `UserResponse`
        opbouwen (de WebSocket-authenticator). `subject` is de `sub`-claim: een gebruikers-id,
        of een e-mailadres; `tenant_id` komt uit dezelfde geverifieerde token en maakt een
        e-mailadres eenduidig (`users.email` is alleen per klant uniek).
        """
        from src.core.database.bypass_session import pre_auth_lookup

        # Een echt id of e-mailadres is nooit langer: geen ValueError en geen int64-overloop.
        if len(subject) > 320 or (subject.isdigit() and len(subject) > 9):
            return False
        if subject.isascii() and subject.isdigit():
            voorwaarde = User.id == int(subject)
        else:
            voorwaarde = User.email == subject
        async with pre_auth_lookup(db) as opzoeker:
            actief = (
                await opzoeker.execute(
                    select(User.is_active).where(voorwaarde, User.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()
        return bool(actief)

    def _get_role_scopes(self, role_name: str) -> list[str]:
        """
        Map role name to default scopes (permissions).

        This is a temporary solution until the permissions table is fully implemented.
        Production systems should use database-backed permission management.

        Args:
            role_name: Name of the role (e.g., 'admin', 'user')

        Returns: List[Any] of OAuth2 scopes (resource:action format)  # TODO(TYPE): replace Any with concrete type
        """
        # Default scope mappings per role
        ROLE_SCOPES = {
            "admin": [
                # `admin:*` is hier WEGGEHAALD (ADR-036 OP-186): het is een loper die op
                # rolnaam werd uitgedeeld. De concrete scopes hieronder blijven; wat een
                # beheerder daarbovenop mag, komt uit de database via de fallback in
                # `scope_validator` en niet uit de naam van zijn rol.
                "agents:read",
                "agents:write",
                "workflows:read",
                "workflows:write",
                "audit:read",
                "users:read",
                "users:write",
                "roles:read",
                "roles:write",
                "compliance:export",
                "prana:read",
                "prana:manage",
                "governance:read",
                "trace:read",
                "twin:read",
            ],
            "user": [
                "agents:read",
                "workflows:read",
                "workflows:write",
                "prana:read",
                "governance:read",
                "trace:read",
                "twin:read",
            ],
            "viewer": [
                "agents:read",
                "workflows:read",
                "prana:read",
            ],
            "developer": [
                "agents:read",
                "agents:write",
                "workflows:read",
                "workflows:write",
                "prana:read",
                "prana:manage",
                "governance:read",
                "trace:read",
                "twin:read",
            ],
        }

        return ROLE_SCOPES.get(role_name.lower(), ["agents:read", "workflows:read"])


# Global instance
auth_service = AuthService()
