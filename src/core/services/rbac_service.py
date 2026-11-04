from __future__ import annotations

"""
RBAC Service - Enhanced Role-Based Access Control
Provides advanced permission checking, role management, and resource-level authorization

Features:
- Role-based permissions (check if user has role)
- Dynamic permission evaluation (with conditions)
- Resource-level permissions (e.g., "user can edit their own agents")
- GEEN permissiecache -- bewust verwijderd 2026-09-18, zie de docstring van RBACService
- Audit logging for permission changes
- Tenant-aware operations
"""

import logging
import unicodedata
from typing import Any, Protocol, cast

from fastapi import Depends
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database.database import get_db
from src.core.exceptions import LastAdminError, NotFoundError
from src.core.database.session import get_db_session
from src.core.middleware.tenant_context import get_tenant_id, require_tenant_id
from src.core.models.rbac_models import Role, RolePermission, User, user_roles
from src.core.shared.events.governance_bus import governance_bus
from src.core.shared.events.governance_events import SecurityAuditEvent
from src.core.shared.tenant_beheerders import BEHEERDERSROLNAMEN, actieve_beheerders
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

#: Rolnamen die het platform toebehoren. Consumenten (`is_admin`, `_is_system_admin`) vertrouwen
#: de naam, dus een klant mag hem niet kunnen aanmaken. `admin` en `tenantadmin` zijn tenant-eigen.
RESERVED_ROLE_NAMES: frozenset[str] = frozenset({"system_admin"})


class ReservedRoleNameError(ValueError):
    """Een klant probeert een rol aan te maken met een gereserveerde platformnaam."""


class PlatformRoleNotAllowedError(PermissionError):
    """Iemand die een platformrol zelf niet heeft, probeert hem aan een ander te geven."""


def is_reserved_role_name(name: str) -> bool:
    """Vergelijk zoals de consumenten, maar ruimer: NFKC + casefold + strip.

    `is_admin` vergelijkt strip().lower(); de `_is_system_admin`-functies exact. NFKC voorkomt dat
    een lookalike (bijvoorbeeld breedtetekens) voor een latere, ruimere vergelijking glipt.
    """
    return unicodedata.normalize("NFKC", name).strip().casefold() in RESERVED_ROLE_NAMES


def telt_als_platformbeheerder(is_superuser: bool, rolnamen: list[str]) -> bool:
    """DE definitie van "deze gebruiker is een platformbeheerder", op een plek (brief 2026-10-19).

    Een platformbeheerder is wie de vlag `is_superuser` heeft OF een platformrol houdt, in welke tenant
    de rolrij ook staat en in welke schrijfwijze (`is_reserved_role_name`). Fail-closed: twee aanwijzingen
    en elke is genoeg. Dit beantwoordt de vraag over het DOEL; het GEZAG van de aanvrager blijft de rol
    (`mag_rol_uitdelen`, OP-189).
    """
    return bool(is_superuser) or any(is_reserved_role_name(str(naam)) for naam in rolnamen)


class Permission:
    """Permission constants for RBAC system"""

    # User management
    USER_READ = "user:read"
    USER_CREATE = "user:create"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_MANAGE = "user:manage"  # All user operations

    # Agent management
    AGENT_READ = "agent:read"
    AGENT_CREATE = "agent:create"
    AGENT_UPDATE = "agent:update"
    AGENT_DELETE = "agent:delete"
    AGENT_EXECUTE = "agent:execute"
    AGENT_MANAGE = "agent:manage"  # All agent operations

    # Workflow management
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_UPDATE = "workflow:update"
    WORKFLOW_DELETE = "workflow:delete"
    WORKFLOW_EXECUTE = "workflow:execute"
    WORKFLOW_MANAGE = "workflow:manage"

    # Admin permissions
    ADMIN = "admin"  # Platform admin
    TENANT_ADMIN = "tenant:admin"  # Tenant admin

    # Special permissions
    SUPERUSER = "superuser"  # Bypass all tenant restrictions


#: Acties die nooit via een wildcard (`*:*`, `resource:*`) worden toegekend: alleen een rij met
#: precies die actie telt. Goedkeuren is een procesbevoegdheid (ADR-039), geen beheerdersrecht.
EXPLICIT_ACTIONS = frozenset({"approve"})

#: Resources waar een jokerresource (`*:read`, `*:write`) NIET voor geldt: alleen een rij met
#: precies deze resource, of de volledige beheerdersrij `*:*`. Personeelsgegevens (HR-pilot dag 2,
#: acceptant 2026-10-11): de rol `user` stond in bestaande omgevingen met `*:read`, en kreeg
#: daardoor de kloof per functie te zien terwijl dat een HR-recht hoort te zijn.
#: Inkoopfacturen en leveranciers (crediteuren dag 1, Gate 2 2026-10-24): met `*:read` zag elke medewerker met de rol `user`
#: de IBAN's en alle facturen van de leveranciers; een recht op `payables` is een crediteurenrecht, geen leesrecht voor iedereen.
EXPLICIT_RESOURCES = frozenset({"hr", "payables"})


# De rolnamen die een beheerder van de tenant maken staan in `src.core.shared.tenant_beheerders`
# (BEHEERDERSROLNAMEN, hier geimporteerd): een KOPIE van `src.core.auth.dependencies.ADMIN_ROLE_NAMES`,
# uitgeschreven omdat deze laag geen import uit `auth` mag erbij krijgen (DSM-meting agent_runtime ->
# auth). Gelijkheid met de centrale definitie wordt bewaakt door
# `tests/architecture/test_goedkeurrecht_per_actie.py`.


class RBACServiceProtocol(Protocol):
    """Protocol for RBAC service - enables dependency injection and testing"""

    async def has_permission(
        self, user_id: int, resource: str, action: str, tenant_id: int | None = None
    ) -> bool:
        """Check if user has a specific permission"""
        ...

    async def get_user_roles(self, user_id: int) -> list[Role]:
        """Get all roles for a user"""
        ...


class ResourceOwnershipChecker:
    """Check if user owns/can access a specific resource"""

    @staticmethod
    async def user_owns_agent(db: AsyncSession, user_id: int, agent_id: int) -> bool:
        """Check if user owns the specified agent"""
        from src.core.agents.models import Agent  # Avoid circular import

        result = await db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.user_id == user_id)
        )
        agent = result.scalar_one_or_none()
        return agent is not None

    @staticmethod
    async def user_in_same_tenant(db: AsyncSession, user_id: int, resource_tenant_id: int) -> bool:
        """Check if user belongs to the same tenant as the resource"""
        result = await db.execute(select(User.tenant_id).where(User.id == user_id))
        user_tenant_id = result.scalar_one_or_none()
        return user_tenant_id == resource_tenant_id


class RBACService:
    """
    Enhanced RBAC Service with tenant-aware permissions

    **ER IS BEWUST GEEN PERMISSIECACHE (verwijderd 2026-09-18, ADR-036 OP-254).**

    Tot die dag werd elke autorisatiebeslissing bewaard onder
    `perm:{tenant}:{user}:{permission}:{resource_type}:{resource_id}` met een TTL van
    `config.redis_cache_ttl` (default 3600 seconden), in Redis zodra `REDIS_URL` gezet was.
    Dat is verwijderd, en dat is een besluit met vier metingen eronder -- geen smaak.

    **1. Wat hij opleverde.** Gemeten 2026-09-18 tegen PostgreSQL (60 rondes, cache leeg
    gemaakt per ronde): mediaan 2,18 ms, p95 2,85 ms. Dat zijn twee geindexeerde selects op
    tabellen met tientallen rijen per klant. Een verzoek doet een of twee van deze
    controles; er is geen enkele aanroeper die in een lus vraagt (20 aanroepplekken in
    `src/`, alle een per endpoint).

    **2. Wat hij kostte.** Een beslissing bleef tot een uur staan nadat de grondslag was
    vervallen. Gemeten via de echte methodes: een recht dat met
    `remove_permission_from_role` van een rol werd afgenomen, bleef `True` geven; een rol
    die met `assign_role` werd toegekend, bleef `False` geven. In Redis overleefde dat een
    herstart van elke replica, dus er was geen noodrem behalve handmatig ingrijpen.

    **3. Waarom invalideren hier niet werkt.** Van de plekken die rechten wijzigen deed er
    precies EEN de invalidatie (`revoke_role`), met het commentaar "CRITICAL" erboven --
    de auteur wist dat het moest en deed het op een van de plekken. De andere waren
    `assign_role`, `add_permission_to_role`, `remove_permission_from_role`,
    `ensure_default_roles`, en `api/v1/user_management/crud_router.py:515`, dat de rolset
    met rauwe SQL vervangt en deze klasse nooit aanraakt. Invalidatie bijbouwen betekent
    een blijvende verplichting op elke toekomstige schrijfplek; de meting laat zien dat die
    verplichting nu al vijf van de zes keer is vergeten.

    **4. Waarom geen enkele test dit ving.** `tests/conftest.py:58` zet `TESTING=1` bij
    import en een autouse-fixture zet hem terug; `user_has_permission` sloeg het
    cache-LEESpad over zodra `TESTING=1` of `POSTGRES_DB=test_db`. Geen enkele test in dit
    project kon de cache dus ooit zien. Een bewaker erop zou per constructie hol zijn
    geweest -- precies `valkuil_autouse_fixture_zet_uit_wat_je_meet`.

    Wil iemand hier ooit weer een cache: doe dat dan niet met invalidatie per mutator, maar
    met een generatieteller in de sleutel, en meet eerst dat 2,18 ms per controle te duur
    is. Zolang die meting er niet is, is de goedkoopste veilige cache geen cache.

    Features:
    - Check user permissions
    - Role management (assign/revoke roles)
    - Dynamic permission evaluation
    - Resource-level authorization
    - Audit logging
    """

    def __init__(self, db: AsyncSession) -> None:
        """Er is BEWUST geen permissiecache meer -- zie de klasse-docstring.

        Hier stond een cache (in Redis, of in een dict per instantie) met een TTL van
        `config.redis_cache_ttl`, plus een eigen Redis-client per instantie die nergens
        werd gesloten. Beide zijn op 2026-09-18 verwijderd (ADR-036 OP-254).
        """
        self.db = db

    async def user_has_permission(
        self,
        user_id: int,
        permission: str,
        tenant_id: int | None = None,
        resource_id: int | None = None,
        resource_type: str | None = None,
    ) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user_id: User ID to check
            permission: Permission string (e.g., "agent:read")
            tenant_id: Optional tenant ID (auto-detected from context if not provided)
            resource_id: Optional resource ID for resource-level checks
            resource_type: Optional resource type (e.g., "agent", "workflow")

        Returns:
            True if user has permission, False otherwise
        """
        try:
            # Get tenant context
            if tenant_id is None:
                tenant_id = get_tenant_id()
                if tenant_id is None:
                    logger.warning(
                        f"No tenant context for permission check: user={user_id}, perm={permission}"
                    )
                    return False

            # Get user's roles WITH tenant isolation
            user_roles_result = await self.db.execute(
                select(Role.id)
                .join(user_roles, Role.id == user_roles.c.role_id)
                .where(
                    user_roles.c.user_id == user_id,
                    Role.tenant_id == tenant_id,
                    Role.is_active,
                )
            )
            role_ids = [r[0] for r in user_roles_result.all()]

            if not role_ids:
                logger.debug(f"User {user_id} has no active roles in tenant {tenant_id}")
                return False

            # Check if any role grants the permission
            # Parse permission string (e.g., "agent:read" -> resource="agent", action="read")
            if ":" in permission:
                perm_resource, perm_action = permission.split(":", 1)
            else:
                perm_resource = permission
                perm_action = "*"

            # De actie `approve` is EXPLICIET (ADR-039 F1): alleen een rij met precies deze
            # resource en deze actie telt. Zonder dit gaf `*:*` van de beheerder vanzelf
            # `receivables:approve`, en dat is nu juist wat Rakesh niet wil (2026-10-09).
            if perm_action in EXPLICIT_ACTIONS:
                resource_match = RolePermission.resource == perm_resource
                action_match = RolePermission.action == perm_action
            elif perm_resource in EXPLICIT_RESOURCES:
                resource_match = or_(
                    RolePermission.resource == perm_resource,
                    # Alleen de volledige beheerdersrij; `*:read` telt hier niet.
                    and_(RolePermission.resource == "*", RolePermission.action == "*"),
                )
                action_match = or_(
                    RolePermission.action == perm_action,
                    RolePermission.action == "*",
                )
            else:
                resource_match = or_(
                    RolePermission.resource == perm_resource,
                    RolePermission.resource == "*",  # Wildcard
                )
                action_match = or_(
                    RolePermission.action == perm_action,
                    RolePermission.action == "*",  # Wildcard action
                )
            permission_result = await self.db.execute(
                select(RolePermission).where(
                    RolePermission.role_id.in_(role_ids),
                    resource_match,
                    action_match,
                )
            )
            permissions = permission_result.scalars().all()

            if not permissions:
                logger.debug(
                    f"No permissions found for user {user_id}, permission {permission} in tenant {tenant_id}"
                )
                return False

            # Evaluate conditions (if any)
            for perm in permissions:
                # Check if conditions exist and evaluate them
                if perm.conditions is not None:
                    # Evaluate dynamic conditions (type: ignore for SQLAlchemy JSON column)
                    # SQLAlchemy JSON column returns dict at runtime; cast for mypy
                    conditions_dict: dict[
                        # TODO(TYPE): replace Any with concrete type
                        str,
                        Any,
                    ] = (  # TODO(TYPE): replace Any with concrete type
                        perm.conditions
                    )  # TODO(TYPE): replace Any with concrete type
                    if await self._evaluate_conditions(
                        conditions_dict, user_id, resource_id, resource_type
                    ):
                        return True
                else:
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking permission: {e}", exc_info=True)
            return False

    async def has_permission(
        self, user_id: int, resource: str, action: str, tenant_id: int | None = None
    ) -> bool:
        """
        Protocol-compliant alias for user_has_permission.
        Implements RBACServiceProtocol interface.

        Args:
            user_id: User ID to check
            resource: Resource name (e.g., "agent", "workflow")
            action: Action name (e.g., "read", "write")
            tenant_id: Optional tenant ID (auto-detected from context if not provided)

        Returns:
            True if user has permission, False otherwise
        """
        permission = f"{resource}:{action}"
        return await self.user_has_permission(user_id, permission, tenant_id=tenant_id)

    async def get_user_roles(self, user_id: int) -> list[Role]:
        """
        Protocol-compliant method to get all roles for a user.
        Implements RBACServiceProtocol interface.

        Args:
            user_id: User ID

        Returns: List of Role objects assigned to the user
        """
        from sqlalchemy import select

        try:
            result = await self.db.execute(
                select(Role)
                .join(user_roles, Role.id == user_roles.c.role_id)
                .where(user_roles.c.user_id == user_id)
                .where(Role.is_active)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error getting user roles: {e}", exc_info=True)
            return []

    async def user_has_role(
        self, user_id: int, role_name: str, tenant_id: int | None = None
    ) -> bool:
        """
        Check if user has a specific role.

        Args:
            user_id: User ID
            role_name: Role name (e.g., "admin", "editor")
            tenant_id: Optional tenant ID

        Returns:
            True if user has the role, False otherwise
        """
        if tenant_id is None:
            tenant_id = get_tenant_id()

        result = await self.db.execute(
            select(Role.id)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(
                user_roles.c.user_id == user_id,
                Role.name == role_name,
                Role.tenant_id == tenant_id,
                Role.is_active,
            )
        )
        role = result.scalar_one_or_none()
        return role is not None

    async def _doelgebruiker_in_tenant(self, user_id: int, tenant_id: int, handeling: str) -> bool:
        """Controleer dat de doelgebruiker in de tenant zit waarvoor wordt gehandeld.

        Bij de rbac-endpoints komt user_id ongevalideerd uit de request body
        (api/v1/rbac/assignment_router.py:20), terwijl de tenant uit de middlewarecontext
        komt (assignment_router.py:43). Zonder deze vergelijking kan een beheerder van de
        ene tenant een rol toekennen aan of intrekken van een gebruiker van een andere.
        De ORM-tenantfilter vangt dat niet: user_roles heeft geen tenant_id
        (models/rbac_models.py:36-43) en de filter laat INSERT bewust ongemoeid
        (database/tenant_query_filter.py:230-231).

        Een onbekende gebruiker en een gebruiker uit een andere tenant krijgen hetzelfde
        antwoord, zodat dit pad geen bestaansorakel over tenantgrenzen heen wordt.
        """
        treffer = await self.db.execute(
            select(User.id).where(User.id == user_id, User.tenant_id == tenant_id)
        )
        if treffer.scalar_one_or_none() is not None:
            return True

        logger.warning(
            "Geweigerd: %s voor gebruiker %s valt buiten tenant %s", handeling, user_id, tenant_id
        )
        async with best_effort("cross_tenant_role_change_refused audit"):
            await governance_bus.emit(
                SecurityAuditEvent(
                    tenant_id=tenant_id,
                    event_type="cross_tenant_role_change_refused",
                    action=handeling,
                    entity_id=str(user_id),
                    details={"reason": "target_user_not_in_tenant"},
                    user_id=user_id,
                )
            )
        return False

    async def assign_role(
        self,
        user_id: int,
        role_name: str,
        tenant_id: int | None = None,
        *,
        assigned_by: int | None = None,
    ) -> bool:
        """
        Assign a role to a user.

        Args:
            user_id: User ID
            role_name: Role name
            tenant_id: Optional tenant ID
            assigned_by: Wie de rol gaf (de ingelogde gebruiker); `None` is het systeem (seed).
                Komt in de auditregel: een persoon mag alle rollen hebben, bewust en gelogd.

        Returns:
            True if successful, False otherwise
        """
        try:
            if tenant_id is None:
                tenant_id = require_tenant_id()

            # Het vangnet voor ELKE aanroeper: een platformrol deelt alleen uit wie hem zelf heeft. De routes
            # toetsen dit vooraf voor een nette 403; deze plek dekt wie dat vergeet (Gate 2, 2026-10-16).
            if not await self.mag_rol_uitdelen(assigned_by, role_name, tenant_id):
                raise PlatformRoleNotAllowedError(
                    f"Role '{role_name}' can only be granted by a platform administrator"
                )

            if not await self._doelgebruiker_in_tenant(user_id, tenant_id, "role_assign"):
                return False

            # Get role
            role_result = await self.db.execute(
                select(Role).where(Role.name == role_name, Role.tenant_id == tenant_id)
            )
            role = role_result.scalar_one_or_none()

            if not role:
                logger.error(f"Role '{role_name}' not found for tenant {tenant_id}")
                return False

            # Check if already assigned
            existing = await self.db.execute(
                select(user_roles.c.user_id).where(
                    user_roles.c.user_id == user_id, user_roles.c.role_id == role.id
                )
            )
            if existing.scalar_one_or_none():
                logger.info(f"User {user_id} already has role '{role_name}'")
                return True

            # Assign role
            await self.db.execute(
                user_roles.insert().values(user_id=user_id, role_id=role.id, tenant_id=tenant_id)
            )
            await self.db.commit()

            # Audit log
            async with best_effort("role_assigned audit"):
                await governance_bus.emit(
                    SecurityAuditEvent(
                        tenant_id=tenant_id,
                        event_type="role_assigned",
                        action="role_assigned",
                        entity_id=str(user_id),
                        details={
                            "role_name": role_name,
                            "role_id": role.id,
                            "assigned_by": assigned_by,
                        },
                        # De ACTOR; de doelgebruiker staat in `entity_id`. Systeem (seed): None.
                        user_id=assigned_by,
                    )
                )

            logger.info(f"Assigned role '{role_name}' to user {user_id}")
            return True

        except PlatformRoleNotAllowedError:
            raise
        except Exception as e:
            logger.error(f"Error assigning role: {e}", exc_info=True)
            await self.db.rollback()
            return False

    async def _tenant_admin_ids(self, tenant_id: int) -> set[int]:
        """De actieve beheerders van de tenant: een beheerdersrol, actief, niet verwijderd.

        De platform-superuser telt NIET mee (F7): die beheert het platform, niet deze tenant.
        """
        return await actieve_beheerders(self.db, tenant_id)

    async def begin_admin_check(self, tenant_id: int) -> int:
        """Vergrendel de beheerdersrollen van de tenant en tel de beheerders VOOR de wijziging.

        De rijvergrendeling (`FOR UPDATE` op de rol-rijen) zorgt dat twee beheerders die elkaar
        tegelijk intrekken niet allebei slagen: de tweede wacht tot de eerste klaar is en telt dan
        opnieuw. Aanroepen in dezelfde transactie als de wijziging, en daarna `finish_admin_check`.
        """
        await self.db.execute(
            select(Role.id)
            .where(Role.tenant_id == tenant_id, func.lower(Role.name).in_(BEHEERDERSROLNAMEN))
            .order_by(Role.id)  # vaste slotvolgorde: geen deadlock tussen twee transacties
            .with_for_update()
        )
        return len(await self._tenant_admin_ids(tenant_id))

    async def finish_admin_check(self, tenant_id: int, before: int) -> None:
        """Tel NA de wijziging (zelfde transactie); laat de tenant zonder beheerder: terugdraaien.

        `before == 0`: de tenant had al geen beheerder, dan blokkeert deze wijziging niets.
        """
        await self.db.flush()
        if before > 0 and not await self._tenant_admin_ids(tenant_id):
            await self.db.rollback()
            raise LastAdminError()

    async def revoke_role(
        self,
        user_id: int,
        role_name: str,
        tenant_id: int | None = None,
        *,
        revoked_by: int | None = None,
    ) -> bool:
        """
        Revoke a role from a user.

        Args:
            user_id: User ID
            role_name: Role name
            tenant_id: Optional tenant ID
            revoked_by: Wie de rol afnam (de ingelogde gebruiker); `None` is het systeem. Komt in de
                auditregel, net als `assigned_by` bij `assign_role` (ADR-039).

        Returns:
            True if successful, False otherwise
        """
        try:
            if tenant_id is None:
                tenant_id = require_tenant_id()

            # Dezelfde regel als uitdelen, op deze ene plek: wie een platformrol zelf niet heeft, kan hem ook niet
            # ontnemen. De routes (revoke-role, bulk) erven dit; zij toetsen niet zelf (brief 2026-10-17).
            if not await self.mag_rol_uitdelen(revoked_by, role_name, tenant_id):
                raise PlatformRoleNotAllowedError(
                    f"Role '{role_name}' can only be revoked by a platform administrator"
                )

            if not await self._doelgebruiker_in_tenant(user_id, tenant_id, "role_revoke"):
                return False

            # Een platformbeheerder (rol OF vlag) verliest geen rol door een ander dan een platformbeheerder.
            await self.controleer_rollen_wijzigen(revoked_by, user_id, tenant_id)

            # Get role
            role_result = await self.db.execute(
                select(Role.id).where(Role.name == role_name, Role.tenant_id == tenant_id)
            )
            role_id = role_result.scalar_one_or_none()

            if not role_id:
                logger.error(f"Role '{role_name}' not found")
                return False

            # Een beheerdersrol intrekken mag de tenant nooit zonder beheerder laten (ADR-039).
            bewaak_beheerder = role_name.lower() in BEHEERDERSROLNAMEN
            voor = await self.begin_admin_check(tenant_id) if bewaak_beheerder else 0

            # Revoke role
            resultaat = await self.db.execute(
                user_roles.delete().where(
                    and_(user_roles.c.user_id == user_id, user_roles.c.role_id == role_id)
                )
            )
            # `delete()` geeft een CursorResult; het generieke Result-type kent `rowcount` niet.
            if int(getattr(resultaat, "rowcount", 0) or 0) == 0:
                # De gebruiker had deze rol niet: niets veranderd, dus geen auditregel.
                await self.db.rollback()
                return False
            if bewaak_beheerder:
                await self.finish_admin_check(tenant_id, voor)
            await self.db.commit()

            # Audit log
            async with best_effort("role_revoked audit"):
                await governance_bus.emit(
                    SecurityAuditEvent(
                        tenant_id=tenant_id,
                        event_type="role_revoked",
                        action="role_revoked",
                        entity_id=str(user_id),
                        details={
                            "role_name": role_name,
                            "role_id": role_id,
                            "revoked_by": revoked_by,
                        },
                        # De ACTOR; de doelgebruiker staat in `entity_id`. Systeem: None.
                        user_id=revoked_by,
                    )
                )

            logger.info(f"Revoked role '{role_name}' from user {user_id}")
            return True

        except (LastAdminError, PlatformRoleNotAllowedError):
            raise
        except Exception as e:
            logger.error(f"Error revoking role: {e}", exc_info=True)
            await self.db.rollback()
            return False

    async def get_user_permissions(self, user_id: int, tenant_id: int | None = None) -> list[str]:
        """
        Get all permissions for a user.

        Args:
            user_id: User ID
            tenant_id: Optional tenant ID

        Returns: List of permission strings in "resource:action" format
        """
        if tenant_id is None:
            tenant_id = get_tenant_id()

        # Get user's roles
        roles_result = await self.db.execute(
            select(Role)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(
                user_roles.c.user_id == user_id,
                Role.tenant_id == tenant_id,
                Role.is_active,
            )
            .options(selectinload(Role.permissions))
        )
        roles = roles_result.scalars().all()

        # Collect all permissions
        permissions = set()
        for role in roles:
            for perm in role.permissions:
                perm_str = f"{perm.resource}:{perm.action}"
                permissions.add(perm_str)

        return list(permissions)

    async def create_role(
        self,
        name: str,
        description: str,
        permissions: list[dict[str, str]],
        tenant_id: int | None = None,
    ) -> Role | None:
        """
        Create a new role with permissions.

        Args:
            name: Role name
            description: Role description
            permissions: List of permission dicts [{"resource": "agent", "action": "read"}, ...]
            tenant_id: Optional tenant ID

        Returns:
            Role object if successful, None otherwise

        Raises:
            ReservedRoleNameError: de naam is een platformrol en geen klant mag hem aanmaken.
        """
        # Buiten de try: een weigering mag niet als "mislukt" (None) worden weggeslikt.
        if is_reserved_role_name(name):
            raise ReservedRoleNameError(f"Role name '{name.strip()}' is reserved for the platform")

        try:
            if tenant_id is None:
                tenant_id = require_tenant_id()

            # Create role
            role = Role(tenant_id=tenant_id, name=name, description=description, is_active=True)
            self.db.add(role)
            await self.db.flush()  # Get role.id

            # Add permissions
            for perm_data in permissions:
                perm = RolePermission(
                    role_id=role.id,
                    tenant_id=tenant_id,
                    resource=perm_data.get("resource", "*"),
                    action=perm_data.get("action", "*"),
                    conditions=perm_data.get("conditions"),
                )
                self.db.add(perm)

            await self.db.commit()
            await self.db.refresh(role)

            # Audit log
            async with best_effort("role_created audit"):
                await governance_bus.emit(
                    SecurityAuditEvent(
                        tenant_id=tenant_id,
                        event_type="role_created",
                        action="role_created",
                        entity_id=str(role.id),
                        details={
                            "role_name": name,
                            "role_id": role.id,
                            "permissions_count": len(permissions),
                        },
                    )
                )

            logger.info(f"Created role '{name}' (id={role.id}) with {len(permissions)} permissions")
            return role

        except Exception as e:
            logger.error(f"Error creating role: {e}", exc_info=True)
            await self.db.rollback()
            return None

    # `_user_is_superuser` is op 2026-09-18 VERWIJDERD (ADR-036 OP-189). Hij bevroeg de ROL
    # met de naam "superuser" -- die nergens wordt aangemaakt of geseed, gemeten nul treffers
    # in `database/` en de rolseeder -- en gaf dus altijd False, terwijl zijn eigen comment
    # zei dat hij "in production" de kolom `User.is_superuser` zou moeten lezen. Hij had nul
    # aanroepers. Een tweede, stil altijd-false antwoord op de vraag "mag deze gebruiker de
    # tenant-grens over" is gevaarlijker dan geen antwoord. De vraag hoort bij
    # `src.core.auth.dependencies.is_platform_superuser`.

    async def ensure_platform_role(self, tenant_id: int) -> None:
        """Zorgt dat de platformrol `system_admin` als rij bestaat in deze tenant (de tenant van het platform).

        Alleen voor het zaaien bij het opstarten (systeempad): `create_role` weigert een gereserveerde naam
        voor elke klant. Idempotent; maakt geen rechtenrijen aan, want de gezaaide beheerder behoudt zijn
        rol `admin` voor zijn scopes.
        """
        for naam in sorted(RESERVED_ROLE_NAMES):
            bestaat = await self.db.execute(
                select(Role.id).where(Role.name == naam, Role.tenant_id == tenant_id)
            )
            if bestaat.scalar_one_or_none() is None:
                self.db.add(
                    Role(
                        tenant_id=tenant_id,
                        name=naam,
                        description="Platform administrator",
                        is_active=True,
                    )
                )
        await self.db.flush()

    async def list_roles(self, tenant_id: int | None = None) -> list[Role]:
        """List all roles for a tenant."""
        if tenant_id is None:
            tenant_id = require_tenant_id()
        result = await self.db.execute(select(Role).where(Role.tenant_id == tenant_id))
        return list(result.scalars().all())

    async def mag_rol_uitdelen(self, actor_id: int | None, role_name: str, tenant_id: int) -> bool:
        """Mag deze persoon deze rol aan een ander geven?

        Een platformrol (`RESERVED_ROLE_NAMES`) deelt alleen uit wie hem zelf heeft: een klant mag
        hem niet aanmaken, en mag hem dus ook niet uitdelen waar de rij toevallig bestaat (de tenant
        van het platform). Gemeten 2026-10-16: uitnodigen en `assign-role` controleerden alleen of de
        rol bestond, waarmee een gewone beheerder zich of een ander tot `system_admin` kon maken.
        `actor_id=None` is het systeem (seed).
        """
        if actor_id is None or not is_reserved_role_name(role_name):
            return True
        return await self.user_has_role(actor_id, role_name, tenant_id)

    async def controleer_uitschakelen(
        self, actor_id: int | None, doel_user_id: int, tenant_id: int
    ) -> None:
        """Een gebruiker MET een platformrol zet alleen uit (is_active=false), verwijdert of laat wissen wie
        die rol zelf heeft: dezelfde ontneming als de rol afnemen (`revoke_role`), dezelfde regel
        (`mag_rol_uitdelen`). De routes (PUT, DELETE, AVG-erase) erven dit; zij toetsen niet zelf.

        Weigert met `PlatformRoleNotAllowedError` (Nederlandse tekst) en schrijft een auditregel.
        `actor_id=None` is het systeem (bijvoorbeeld de 30-dagenpurge).
        """
        await self._eis_platformgezag_over(
            actor_id,
            doel_user_id,
            tenant_id,
            "Deze gebruiker heeft een platformrol. Alleen een platformbeheerder kan zo iemand "
            "uitzetten, verwijderen of laten wissen.",
        )

    async def controleer_profiel_wijzigen(
        self, actor_id: int | None, doel_user_id: int, tenant_id: int
    ) -> None:
        """Het e-mailadres of het wachtwoord van een gebruiker MET een platformrol wijzigt alleen wie die rol
        zelf heeft. Anders is dit een accountovername: "wachtwoord vergeten" stuurt de herstellink naar het
        nieuwe adres, en een gezet wachtwoord is meteen een inlog. Dezelfde regel als uitzetten en als de
        rol afnemen; de routes (PUT /users/{id}, PUT /users/{id}/password) erven hem.

        Weigert met `PlatformRoleNotAllowedError` (Nederlandse tekst). `actor_id=None` is het systeem.
        """
        await self._eis_platformgezag_over(
            actor_id,
            doel_user_id,
            tenant_id,
            "Deze gebruiker heeft een platformrol. Alleen een platformbeheerder kan het e-mailadres "
            "of het wachtwoord van zo iemand wijzigen.",
        )

    async def controleer_rollen_wijzigen(
        self, actor_id: int | None, doel_user_id: int, tenant_id: int
    ) -> None:
        """De rollen van een platformbeheerder (rol OF vlag) wijzigt alleen wie zelf de platformrol heeft.

        Gebruikt door `revoke_role` (en dus de bulkroute) en door de vervangende rollenset van
        `PUT /users/{id}`: een tenantbeheerder kan een platformbeheerder geen enkele rol afnemen.
        """
        await self._eis_platformgezag_over(
            actor_id,
            doel_user_id,
            tenant_id,
            "Deze gebruiker is platformbeheerder. Alleen een platformbeheerder kan zijn rollen wijzigen.",
        )

    async def controleer_tenant_wissen(self, actor_id: int | None, tenant_id: int) -> None:
        """Een tenantbrede wissing (delete-all) raakt geen platformbeheerder: bevat de tenant er een (rol OF
        vlag) en heeft de aanvrager zelf de platformrol niet, dan wordt de wissing geweigerd.

        Weigeren en niet overslaan: een harde wissing verwijdert de gebruikers en de tenant samen, dus een
        overgeslagen platformbeheerder houdt de wissing met een vreemde-sleutelfout tegen.
        """
        if actor_id is None or await self.mag_rol_uitdelen(actor_id, "system_admin", tenant_id):
            return
        for rij in await self._gebruikers_met_rolnamen(tenant_id):
            if telt_als_platformbeheerder(rij[1], rij[2]):
                raise PlatformRoleNotAllowedError(
                    "Deze omgeving bevat een platformbeheerder. Alleen een platformbeheerder kan "
                    "alle gegevens van deze omgeving wissen."
                )

    async def is_platformbeheerder(self, user_id: int, tenant_id: int) -> bool:
        """Is deze gebruiker van deze tenant een platformbeheerder? Zie `telt_als_platformbeheerder`.

        Een onbekende gebruiker, of een gebruiker van een andere tenant, is hier False: de routes hebben het
        doel dan al met een 404 afgewezen, en zo is dit geen bestaansorakel over tenantgrenzen heen.
        """
        rijen = await self._gebruikers_met_rolnamen(tenant_id, user_id=user_id)
        return any(telt_als_platformbeheerder(rij[1], rij[2]) for rij in rijen)

    async def _gebruikers_met_rolnamen(
        self, tenant_id: int, *, user_id: int | None = None
    ) -> list[tuple[int, bool, list[str]]]:
        """(id, is_superuser, rolnamen) van een gebruiker of van alle gebruikers van een tenant.

        Altijd binnen `tenant_id`, ook als de tenantfilter dat al doet. Een rij uit `user_roles` kan niet naar
        een rol van een ANDERE tenant wijzen: de samengestelde vreemde sleutels `fk_user_roles_role_tenant` en
        `fk_user_roles_user_tenant` laten dat niet toe (gemeten 2026-10-19), dus de rolnamen van een gebruiker
        zijn altijd die van zijn eigen tenant.
        """
        voorwaarde = User.tenant_id == tenant_id
        if user_id is not None:
            voorwaarde = and_(voorwaarde, User.id == user_id)
        rijen = (
            await self.db.execute(
                select(User.id, User.is_superuser, Role.name)
                .outerjoin(user_roles, user_roles.c.user_id == User.id)
                .outerjoin(Role, Role.id == user_roles.c.role_id)
                .where(voorwaarde)
            )
        ).all()
        per_gebruiker: dict[int, tuple[bool, list[str]]] = {}
        for gebruiker, vlag, naam in rijen:
            _, namen = per_gebruiker.setdefault(int(gebruiker), (bool(vlag), []))
            if naam is not None:
                namen.append(str(naam))
        return [(gid, vlag, namen) for gid, (vlag, namen) in per_gebruiker.items()]

    async def _eis_platformgezag_over(
        self, actor_id: int | None, doel_user_id: int, tenant_id: int, melding: str
    ) -> None:
        """De ene regel achter `controleer_uitschakelen`, `controleer_profiel_wijzigen` en
        `controleer_rollen_wijzigen`: is het DOEL een platformbeheerder (`telt_als_platformbeheerder`) en heeft
        de aanvrager zelf de platformrol niet, dan raakt hij die gebruiker niet aan.

        Wie zichzelf wijzigt, wordt hier niet geweigerd: de regel beschermt een platformbeheerder tegen een
        ANDER (de gezaaide beheerder met alleen de vlag moet zijn eigen adres kunnen wijzigen).
        """
        if actor_id is None or actor_id == doel_user_id:
            return
        if not await self.is_platformbeheerder(doel_user_id, tenant_id):
            return
        if not await self.mag_rol_uitdelen(actor_id, "system_admin", tenant_id):
            raise PlatformRoleNotAllowedError(melding)

    async def platformrollen_die_blijven(
        self, actor_id: int | None, doel_user_id: int, tenant_id: int, gekozen_ids: set[int]
    ) -> list[Role]:
        """De platformrollen die de doelgebruiker heeft, die de aanvrager niet mag wijzigen en die in een
        vervangende set ontbreken. Een PUT die zo'n rol weglaat laat hem dus staan.

        Dezelfde regel als uitdelen en ontnemen (`mag_rol_uitdelen`); dit is de vervang-vorm ervan.
        """
        if actor_id is None:
            return []
        gehouden = (
            await self.db.execute(
                select(Role)
                .join(user_roles, user_roles.c.role_id == Role.id)
                .where(user_roles.c.user_id == doel_user_id, Role.tenant_id == tenant_id)
            )
        ).scalars()
        blijven: list[Role] = []
        for rol in gehouden:
            if int(rol.id) in gekozen_ids or not is_reserved_role_name(str(rol.name)):
                continue
            if not await self.mag_rol_uitdelen(actor_id, str(rol.name), tenant_id):
                blijven.append(rol)
        return blijven

    async def list_roles_voor(self, actor_id: int, tenant_id: int) -> list[Role]:
        """De rollen die deze persoon mag zien en kiezen: platformrollen alleen als hij ze zelf heeft."""
        rollen = await self.list_roles(tenant_id)
        zichtbaar: list[Role] = []
        for rol in rollen:
            if await self.mag_rol_uitdelen(actor_id, rol.name, tenant_id):
                zichtbaar.append(rol)
        return zichtbaar

    async def list_role_permissions(self, role_id: int) -> list[RolePermission]:
        """List all permissions for a role."""
        result = await self.db.execute(
            select(RolePermission).where(RolePermission.role_id == role_id)
        )
        return list(result.scalars().all())

    async def get_role_permissions(self, role_id: int) -> list[RolePermission]:
        """
        Protocol-compliant alias for list_role_permissions.
        Gets all permissions for a specific role.
        """
        return await self.list_role_permissions(role_id)

    async def _rol_van_deze_klant(self, role_id: int, tenant_id: int) -> Role:
        """De rol, maar ALLEEN als hij bij deze klant hoort. Anders 404 (ADR-036 OP-256).

        **Waarom dit een eigen stap is en niet een filter onderweg.** `role_id` komt bij
        beide aanroepers rechtstreeks uit het URL-pad
        (`api/v1/rbac/roles_router.py:154` en `:176`). Die router controleert wel
        `TENANT_ADMIN` op de klant van de AANVRAGER, maar gaf daarna het rauwe nummer door:
        een beheerder van klant A kon een `role_id` van klant B opgeven. De ORM-tenantfilter
        vangt dat niet, want die filtert bewust alleen SELECT/UPDATE/DELETE en geen INSERT,
        en hij kan per sessie worden uitgezet met `TenantFilterBypass`. Een schrijfactie mag
        niet afhangen van een filter op een leesactie.

        **404 en niet 403**, met opzet: een 403 zou bevestigen dat die rol ergens bestaat.
        Voor de aanvrager bestaat een rol van een andere klant niet.
        """
        rol = (
            await self.db.execute(
                select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if rol is None:
            logger.warning(
                "Rol %s is niet van klant %s (of bestaat niet) -- geweigerd", role_id, tenant_id
            )
            raise NotFoundError(resource_type="Role", resource_id=str(role_id))
        return rol

    async def add_permission_to_role(
        self,
        role_id: int,
        resource: str,
        action: str,
        conditions: (
            dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
        ) = None,  # JSON conditions: {"owner_only": bool, "same_tenant": bool}
        tenant_id: int | None = None,
    ) -> bool:
        """Voeg een recht toe aan een rol van DEZE klant.

        **Deze methode kon tot 2026-09-18 nooit slagen (ADR-036 OP-255).** Hij bouwde een
        `RolePermission` zonder `tenant_id`, terwijl die kolom `nullable=False` is zonder
        default (`models/rbac_models.py:242`). Gemeten: `NotNullViolationError`, gevangen
        door de `except` hieronder, en de methode gaf netjes `False` terug -- waarna
        `roles_router.py:154` er een HTTP 400 van maakte. Een rol een recht geven via de API
        was dus onmogelijk, en dat stond maandenlang groen omdat de twee tests die dit pad
        raken precies deze methode wegpatchen met een nepversie die `True` geeft
        (`tests/integration/test_rbac_middleware_coverage.py:502` en `:741`).

        De `tenant_id` komt NIET uit de rol maar van de AANVRAGER, en de rol moet daarbij
        passen -- zie `_rol_van_deze_klant`. De rol als bron nemen zou betekenen dat de
        invoer van de aanvrager bepaalt onder welke klant geschreven wordt.

        Werpt `NotFoundError` als de rol niet van deze klant is; geeft `False` alleen nog
        terug bij een echte databasefout.
        """
        if tenant_id is None:
            tenant_id = require_tenant_id()
        await self._rol_van_deze_klant(role_id, tenant_id)
        try:
            perm = RolePermission(
                role_id=role_id,
                tenant_id=tenant_id,
                resource=resource,
                action=action,
                conditions=conditions,
            )
            self.db.add(perm)
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding permission to role {role_id}: {e}", exc_info=True)
            await self.db.rollback()
            return False

    async def remove_permission_from_role(
        self, role_id: int, resource: str, action: str, tenant_id: int | None = None
    ) -> bool:
        """Neem een recht af van een rol van DEZE klant.

        Dezelfde klantcontrole als bij `add_permission_to_role` (ADR-036 OP-256), en hier
        is hij urgenter: deze kant WAS bereikbaar, want hij faalde niet op de ontbrekende
        `tenant_id`. Werpt `NotFoundError` als de rol niet van deze klant is.
        """
        if tenant_id is None:
            tenant_id = require_tenant_id()
        await self._rol_van_deze_klant(role_id, tenant_id)
        try:
            await self.db.execute(
                RolePermission.__table__.delete().where(
                    and_(
                        RolePermission.role_id == role_id,
                        RolePermission.resource == resource,
                        RolePermission.action == action,
                    )
                )
            )
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error removing permission from role {role_id}: {e}", exc_info=True)
            await self.db.rollback()
            return False

    async def list_users_by_role(self, role_id: int, tenant_id: int | None = None) -> list[User]:
        """List users assigned to a role (tenant-aware)."""
        if tenant_id is None:
            tenant_id = require_tenant_id()
        result = await self.db.execute(
            select(User)
            .join(user_roles, User.id == user_roles.c.user_id)
            .where(user_roles.c.role_id == role_id, User.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def vervang_rollen(self, user_id: int, role_ids: list[int], tenant_id: int) -> list[str]:
        """Vervang de VOLLEDIGE rolset van een gebruiker. Geeft de resulterende rolnamen.

        **Waarom deze methode bestaat (ADR-036 OP-258).** Rollen toewijzen gebeurde op TWEE
        plekken die niets van elkaar wisten: hier, en met rauwe
        `user_roles.delete()` + `insert()` in `api/v1/user_management/crud_router.py`. Die
        tweede deur was geen lek -- hij controleerde per rol `Role.tenant_id` en schreef een
        auditregel -- maar het is precies de vorm waardoor OP-254 kon ontstaan: daar zat de
        cache-invalidatie op EEN van de zes schrijfplekken, omdat de andere vijf niet door
        dezelfde deur gingen. Een handeling hoort een plek te hebben.

        Het gedrag is bewust IDENTIEK aan wat die router deed, zodat deze verplaatsing niets
        stilletjes verandert:

        - de hele set wordt vervangen, niet aangevuld;
        - een `role_id` dat niet bij `tenant_id` hoort wordt OVERGESLAGEN met een
          waarschuwing, niet geweigerd. Dat is discutabel (een beheerder krijgt 200 terwijl
          een gevraagde rol niet is toegekend) maar het is het bestaande gedrag, en het
          veranderen hoort bij een eigen besluit met een eigen registerrij;
        - de aanroeper blijft verantwoordelijk voor de autorisatie en de auditregel.

        `tenant_id` is VERPLICHT en komt van de aanroeper: de rollen worden eraan getoetst.
        """
        await self.db.execute(user_roles.delete().where(user_roles.c.user_id == user_id))

        toegekend: list[str] = []
        for role_id in role_ids:
            rol = (
                await self.db.execute(
                    select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()
            if rol is None:
                logger.warning(
                    "Rol %s niet gevonden of niet van klant %s -- overgeslagen", role_id, tenant_id
                )
                continue
            await self.db.execute(
                user_roles.insert().values(user_id=user_id, role_id=role_id, tenant_id=tenant_id)
            )
            toegekend.append(rol.name)

        await self.db.commit()
        return toegekend

    async def bulk_assign_roles(
        self,
        user_ids: list[int],
        role_name: str,
        tenant_id: int | None = None,
        *,
        assigned_by: int | None = None,
    ) -> list[dict[str, int | bool]]:  # each entry: {"user_id": int, "success": bool}
        """Assign a role to many users, returning per-user success."""
        if tenant_id is None:
            tenant_id = require_tenant_id()
        result: list[dict[str, int | bool]] = []
        for uid in user_ids:
            ok = await self.assign_role(uid, role_name, tenant_id, assigned_by=assigned_by)
            result.append({"user_id": uid, "success": ok})
        return result

    async def bulk_revoke_roles(
        self,
        user_ids: list[int],
        role_name: str,
        tenant_id: int | None = None,
        *,
        revoked_by: int | None = None,
    ) -> list[dict[str, int | bool | str]]:  # {"user_id", "success"[, "error"]}
        """Revoke a role from many users, returning per-user success."""
        if tenant_id is None:
            tenant_id = require_tenant_id()
        # Eerst ALLE doelen toetsen, daarna pas intrekken: `revoke_role` commit per gebruiker, dus een
        # platformbeheerder op plek 2 liet anders gebruiker 1 al ingetrokken achter bij een 403.
        for uid in user_ids:
            await self.controleer_rollen_wijzigen(revoked_by, uid, tenant_id)
        result: list[dict[str, int | bool | str]] = []
        for uid in user_ids:
            try:
                ok = await self.revoke_role(uid, role_name, tenant_id, revoked_by=revoked_by)
            except LastAdminError:
                result.append({"user_id": uid, "success": False, "error": "LAST_ADMIN"})
                continue
            result.append({"user_id": uid, "success": ok})
        return result

    async def ensure_default_roles(self, tenant_id: int) -> None:
        try:
            bestaand = await self.db.execute(select(Role).where(Role.tenant_id == tenant_id))
            rol_per_naam = {r.name: r for r in bestaand.scalars().all()}

            # MEERVOUD, gelijk aan de scopes (ADR-036 OP-191). Hier stond enkelvoud --
            # `agent` en `workflow` -- terwijl endpoints `agents:read` en `workflows:read`
            # EISEN. `scope_validator` splitst die scope naar `resource="agents"` en
            # `user_has_permission` matcht letterlijk op `resource == "agents"` of `"*"`.
            # `"agent"` is niet `"agents"`, dus `editor` en `user` hadden rechten die met
            # geen enkele scope konden matchen; alleen `admin` overleefde, via zijn
            # wildcard.
            #
            # De scopes zijn de contractzijde: endpoints declareren ze, ongeveer 306 keer.
            # De zaailijst hoort die taal te spreken en niet andersom. Normaliseren in de
            # matcher (een `s` afknippen) is verworpen -- dat behandelt `prana`, `audit`,
            # `governance`, `twin` en `compliance` stilzwijgend anders, want die hebben
            # helemaal geen meervoudsvorm.
            defaults = [
                (
                    "admin",
                    "Tenant administrator",
                    [
                        {"resource": "*", "action": "*"},
                        # Expliciet en niet via `*:*` (ADR-039, besluit Rakesh 2026-10-10):
                        # configuratie via serena inrichten is een beheerderstaak.
                        {"resource": "config", "action": "approve"},
                    ],
                ),
                (
                    "editor",
                    "Content editor",
                    [
                        {"resource": "agents", "action": "*"},
                        {"resource": "workflows", "action": "*"},
                        # Een medewerker die workflows bouwt mag via een workflowstap taken aanmaken en wijzigen
                        # (besluit Rakesh 2026-10-23). Smal recht, NIET `tools:write`; `delete_task` blijft beheerder.
                        {"resource": "tasks", "action": "write"},
                        # Een agent mag namens een editor LEZEN (OP-143). Dit is de enige
                        # bewuste verruiming van die wijziging: editor kreeg voor agenten
                        # vroeger NIETS (`MISSING_SCOPE` op elke tool) terwijl hij via de
                        # routes wel `agents:*` had. Geen `tools:write`.
                        {"resource": "tools", "action": "read"},
                        # Een domeinpakket uitvoeren (ADR-036 OP-09, besluit Rakesh 2026-10-09:
                        # "een beheerder zet het pakket aan, een medewerker voert het uit").
                        {"resource": "packs", "action": "execute"},
                        # Bonnen laten lezen (bonlezer dag 3): een medewerker uploadt en bekijkt.
                        {"resource": "receipts", "action": "*"},
                    ],
                ),
                (
                    "user",
                    "Default user",
                    [
                        {"resource": "agents", "action": "read"},
                        {"resource": "workflows", "action": "read"},
                        {"resource": "receivables", "action": "read"},
                        # Leestools via een agent (OP-143); had dat in de oude matrix als `read`.
                        {"resource": "tools", "action": "read"},
                        # Zie `editor`: een medewerker voert een geactiveerd pakket uit (OP-09).
                        {"resource": "packs", "action": "execute"},
                        # Bonnen uploaden en bekijken (bonlezer dag 3); geen `*`, dus geen toekomstig recht erbij.
                        {"resource": "receipts", "action": "read"},
                        {"resource": "receipts", "action": "write"},
                    ],
                ),
                # Rolmodel debiteuren, optie A (docs/plan-van-aanpak-nazorg.md deel II punt 1):
                # registreren en voorstellen, NIET goedkeuren. Goedkeuren is sinds ADR-039 een
                # eigen recht (`receivables:approve`, rol `goedkeurder`) en ook de beheerder heeft
                # het niet vanzelf (`EXPLICIT_ACTIONS`).
                (
                    "debiteuren",
                    "Debiteurenadministrateur",
                    [
                        {"resource": "receivables", "action": "read"},
                        {"resource": "receivables", "action": "write"},
                        # Een brief voorstellen (`/reminder-proposals`); zelfde recht als de
                        # agent-tool `send_payment_reminder` (`receivables:propose`).
                        {"resource": "receivables", "action": "propose"},
                        # Leestools via een agent (OP-143); had dat in de oude matrix als `read`.
                        {"resource": "tools", "action": "read"},
                    ],
                ),
                # Crediteuren dag 1 (Keten F, 2026-10-24): inkoopfacturen en leveranciers vastleggen en tot
                # `gecontroleerd` brengen, en (dag 2) een gelezen factuur door de crediteurenagent laten verwerken
                # (`payables:write`). Smal en los van goedkeuren (ADR-039): een uitzondering van de agent goedkeuren is
                # `payables:approve`, rol `goedkeurder`. Geen `tools:read`: de agent heeft geen leestools.
                (
                    "crediteuren",
                    "Crediteurenadministrateur",
                    [
                        {"resource": "payables", "action": "read"},
                        {"resource": "payables", "action": "write"},
                    ],
                ),
                # Procesbevoegdheid goedkeuren (ADR-039 F1, besluit Rakesh 2026-10-09): de
                # beheerder krijgt deze rol NIET vanzelf; in een klein bedrijf wijst hij hem aan
                # zichzelf toe (een persoon mag alle rollen beslaan).
                (
                    "goedkeurder",
                    "Goedkeurder debiteuren en crediteuren",
                    [
                        {"resource": "receivables", "action": "read"},
                        {"resource": "receivables", "action": "approve"},
                        # Een uitzondering van de crediteurenagent goedkeuren (crediteuren dag 2): ook hier is goedkeuren een
                        # eigen procesrecht, `payables:approve` (expliciet, nooit via `*:*`), met leesrecht om de factuur te zien.
                        {"resource": "payables", "action": "read"},
                        {"resource": "payables", "action": "approve"},
                        # Algemeen goedkeurrecht voor e-mail versturen en documenten of taken
                        # verwijderen (besluit Rakesh 2026-10-10).
                        {"resource": "governance", "action": "approve"},
                        {"resource": "tools", "action": "read"},
                    ],
                ),
                # Een aparte rol per proces (ADR-039): personeel. Goedkeuren is een eigen
                # procesbevoegdheid en geen leesrecht; het ticket zien vraagt alleen dit recht.
                (
                    "goedkeurder_hr",
                    "Goedkeurder personeel",
                    [
                        {"resource": "hr", "action": "approve"},
                        # De goedkeurder moet het voorstel kunnen zien dat hij beslist.
                        {"resource": "hr", "action": "read"},
                        {"resource": "tools", "action": "read"},
                    ],
                ),
                # HR-pilot dag 1 (besluit Rakesh 2026-10-09, ADR-039): wie personeelsgegevens
                # inleest en de kloofanalyse draait, hoeft geen beheerder te zijn. `hr:read` en
                # `hr:write` zijn gewone acties; de beheerder heeft ze via `*:*`. NIET `hr:approve`:
                # een opleiding toewijzen blijft een goedkeuring door `goedkeurder_hr`.
                (
                    "hr_medewerker",
                    "Medewerker personeelszaken",
                    [
                        {"resource": "hr", "action": "read"},
                        {"resource": "hr", "action": "write"},
                        {"resource": "packs", "action": "execute"},
                        {"resource": "tools", "action": "read"},
                    ],
                ),
            ]
            for name, desc, perms in defaults:
                rol = rol_per_naam.get(name)
                bestond_al = rol is not None
                if rol is None:
                    rol = Role(tenant_id=tenant_id, name=name, description=desc, is_active=True)
                    self.db.add(rol)
                    await self.db.flush()

                # ONTBREKENDE rechten worden ook voor een BESTAANDE rol aangemaakt
                # (ADR-036 OP-187). Hier stond `if name not in existing_names:` om de hele
                # tak heen, dus bestond de naam al, dan kreeg die rol nooit zijn
                # permissierijen. Gemeten 2026-09-15 in de live database: `user` bestond
                # met NUL rechten terwijl deze lijst hem er twee belooft.
                #
                # Deze functie heet `ensure_default_roles` -- hij hoort de standaard te
                # GARANDEREN, niet alleen bij een lege tenant. Let op wat dat betekent: hij
                # wijzigt voortaan ook rollen die er al waren. Dat is alleen verantwoord
                # omdat het pad waarlangs een aanvaller zelf een rol kon aanmaken op
                # 2026-09-11 is gesloten (OP-185, zie
                # tests/unit/auth/test_het_rolprimitief_maakt_geen_rollen_aan.py) en de
                # namen in deze lijst vastliggen.
                huidig = await self.db.execute(
                    select(RolePermission.resource, RolePermission.action).where(
                        RolePermission.role_id == rol.id
                    )
                )
                aanwezig = {(r, a) for r, a in huidig.all()}
                aangevuld = []
                for p in perms:
                    sleutel = (p.get("resource", "*"), p.get("action", "*"))
                    if sleutel in aanwezig:
                        continue
                    self.db.add(
                        RolePermission(
                            role_id=rol.id,
                            resource=sleutel[0],
                            action=sleutel[1],
                            tenant_id=tenant_id,
                        )
                    )
                    aangevuld.append(f"{sleutel[0]}:{sleutel[1]}")

                # Zichtbaar maken WAT er wordt aangevuld en voor wie (voorstel van de
                # Gate-2-reviewer bij OP-187). Deze functie draait bij ELKE start voor ELKE
                # tenant. Heeft een beheerder ooit bewust een permissierij VERWIJDERD, dan
                # zet de volgende herstart hem terug. Dat is vandaag onschadelijk -- er is
                # een permissierij in de hele database -- maar het is zelfherstellend gedrag
                # dat niemand heeft aangevraagd. Deze regel haalt het uit de categorie
                # "stil": wie zich afvraagt waarom een recht terug is, vindt het in het log.
                if aangevuld and bestond_al:
                    logger.info(
                        "ensure_default_roles vulde rechten aan voor bestaande rol %r "
                        "in tenant %s: %s",
                        name,
                        tenant_id,
                        ", ".join(sorted(aangevuld)),
                    )
            await self.db.commit()
        except Exception as e:
            logger.error(
                f"Error ensuring default roles for tenant {tenant_id}: {e}",
                exc_info=True,
            )
            await self.db.rollback()

    async def _evaluate_conditions(
        self,
        conditions: dict[
            str, Any  # TODO(TYPE): replace Any with concrete type
        ],  # JSON conditions: {"owner_only": bool, "same_tenant": bool, "max_count": int}
        user_id: int,
        resource_id: int | None,
        resource_type: str | None,
    ) -> bool:
        """
        Evaluate permission conditions.
        Supported keys:
        - owner_only: user must own the resource
        - same_tenant: resource must be in same tenant as user
        - max_count: limit number of resources (not implemented yet)
        """
        try:
            # Owner-only check
            if conditions.get("owner_only") and resource_id and resource_type:
                if resource_type == "agent":
                    return await ResourceOwnershipChecker.user_owns_agent(
                        self.db, user_id, resource_id
                    )
                if resource_type == "workflow":
                    from src.core.workflow.models import C7Workflow as Workflow

                    result = await self.db.execute(
                        select(Workflow.owner_id).where(Workflow.id == resource_id)
                    )
                    owner_id = result.scalar_one_or_none()
                    return cast(bool, owner_id == user_id)

            # Same tenant check
            if conditions.get("same_tenant") and resource_id and resource_type:
                if resource_type == "agent":
                    from src.core.agents.models import Agent

                    result = await self.db.execute(
                        select(Agent.tenant_id).where(Agent.id == resource_id)
                    )
                    resource_tenant_id = result.scalar_one_or_none()
                    if resource_tenant_id is None:
                        return False
                    return await ResourceOwnershipChecker.user_in_same_tenant(
                        self.db, user_id, resource_tenant_id
                    )
                if resource_type == "workflow":
                    from src.core.workflow.models import C7Workflow as Workflow

                    result = await self.db.execute(
                        select(Workflow.tenant_id).where(Workflow.id == resource_id)
                    )
                    wf_tenant_id = result.scalar_one_or_none()
                    if wf_tenant_id is None:
                        return False
                    # Compare user's tenant_id (int) to workflow tenant (str)
                    user_tid_result = await self.db.execute(
                        select(User.tenant_id).where(User.id == user_id)
                    )
                    user_tid = user_tid_result.scalar_one_or_none()
                    return cast(bool, str(user_tid) == wf_tenant_id)

            # Max count check (placeholder)
            if "max_count" in conditions:
                # TODO: Implement resource count checks per type
                pass

            # FAIL-SECURE: een conditie die zijn context NIET kreeg, is NIET vervuld.
            #
            # Hier stond `# Default: conditions met` gevolgd door `return True` (ADR-036
            # OP-257). Gevolg: een permissierij met `owner_only` of `same_tenant` werd
            # ONVOORWAARDELIJK toegekend zodra `resource_id` of `resource_type` ontbrak --
            # de `if`-takken hierboven eisen allebei die twee, dus bij afwezigheid viel
            # alles door naar `True`. Hetzelfde gold voor een `resource_type` die hierboven
            # niet wordt afgehandeld (iets anders dan `agent` of `workflow`).
            #
            # Gemeten 2026-09-18 dat dit VANDAAG onbereikbaar was: geen enkele aanroeper van
            # `user_has_permission` geeft `resource_id`/`resource_type` mee, en er stond nul
            # permissierijen met condities in de database. Het was dus een latente doorval,
            # en precies daarom hoort hij dicht VOORDAT iemand de eerste conditionele rij
            # aanmaakt -- niet erna.
            afdwingbaar = {"owner_only", "same_tenant"}
            gevraagd = {sleutel for sleutel in afdwingbaar if conditions.get(sleutel)}
            if gevraagd:
                logger.warning(
                    "Conditie(s) %s konden niet worden beoordeeld voor gebruiker %s "
                    "(resource_id=%r, resource_type=%r) -- geweigerd",
                    sorted(gevraagd),
                    user_id,
                    resource_id,
                    resource_type,
                )
                return False

            # Geen enkele afdwingbare conditie gevraagd: er valt niets te weigeren.
            return True
        except Exception as e:
            logger.error(f"Error evaluating conditions: {e}", exc_info=True)
            return False


# Helper function for dependency injection
async def get_rbac_service(
    db: AsyncSession | None = Depends(get_db),
) -> RBACService:
    """Get RBAC service instance with injected database session"""
    if db is None or not isinstance(db, AsyncSession):
        async with get_db_session() as session:
            return RBACService(session)
    return RBACService(db)
