"""
RBAC (Role-Based Access Control) - Production Implementation
Functionele FastAPI dependency voor autorisatie zoals gespecificeerd in FASE 1 STAP 1.3
"""

import logging
from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING, Any
from collections.abc import Callable

if TYPE_CHECKING:
    from src.core.tool_broker.risk_classifier import ToolRiskClassifier

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _tool_risk_classifier() -> "ToolRiskClassifier":
    """De toolconfiguratie eenmaal inlezen, niet per autorisatievraag.

    `ToolRiskClassifier.__init__` doet een blokkerende `open()` plus `yaml.safe_load`. Deze
    functie wordt aangeroepen binnen het beraadslagingsbudget van de SecurityOfficer
    (`timeout_ms = 300`); een schijflees per actie zou onder belasting legitieme acties doen
    afketsen op een timeout, die de coordinator als VETO telt. Zelfde patroon als
    `_get_rbac_service()` in `copilot/council/factory.py`.

    De configuratie is statisch; wijzigen vraagt een herstart, net als bij de risiconiveaus.
    """
    from src.core.tool_broker.risk_classifier import ToolRiskClassifier

    return ToolRiskClassifier()


# MVP allowlist of Council action_types. Unknown types are fail-denied (ADR-017).
# Extend when new action_types are added to Proposal builders.
_COUNCIL_ALLOWED_ACTION_TYPES: frozenset[str] = frozenset(
    {
        # CVA / copilot actions
        "send_notification",
        "navigate_to",
        "read_data",
        "write_data",
        "create_task",
        "update_task",
        "delete_task",
        "admin_action",
        # Scheduling voice actions
        "create_meeting",
        "cancel_meeting",
        "reschedule_meeting",
        "check_availability",
        "list_meetings",
        "clarify",
        "confirm",
        "unknown",
    }
)


class Permission(Enum):
    """Permissions voor RBAC systeem"""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    SYSTEM_MONITOR = "system_monitor"
    SYSTEM_ADMIN = "system_admin"
    LOG_ANALYZER = "log_analyzer"
    #: Een debiteurenbrief VOORSTELLEN (herinnering of aanmaning). Smaller dan `WRITE`: de rol
    #: `debiteuren` krijgt hiermee alleen de broker-tools waar `tool_risk_levels.yml` dit recht
    #: voor vraagt, niet elke schrijftool. Het versturen blijft HIGH en wacht op een beheerder
    #: (HITL); goedkeuren loopt via `_require_approver`, niet via deze matrix.
    RECEIVABLES_PROPOSE = "receivables_propose"


#: De rechten die `tool_risk_levels.yml` mag vragen, in de vorm `resource:actie` van
#: `role_permissions`. Dit is GEEN rolmatrix -- welke rol welk recht heeft staat in de database
#: (`RBACService.ensure_default_roles` zaait, een beheerder past aan). Dit is de lijst van
#: GELDIGE waarden voor een toolregel: een typefout of een wildcard (`*:*`) in de configuratie
#: wordt geweigerd in plaats van doorgelaten (zero-trust). Een nieuw recht vraagt hier een
#: regel; dat is bewuste wrijving, bewaakt door
#: `tests/architecture/test_every_executable_tool_has_a_required_permission.py`.
TOOL_RECHTEN: frozenset[str] = frozenset(
    {
        "tools:read",
        "tools:write",
        "tools:admin",
        #: Een debiteurenbrief VOORSTELLEN (herinnering of aanmaning). Smaller dan
        #: `tools:write`: de rol `debiteuren` krijgt hiermee alleen de broker-tools waar de
        #: configuratie dit recht voor vraagt, niet elke schrijftool. Het versturen blijft HIGH
        #: en wacht op een beheerder (HITL).
        "receivables:propose",
        #: Personeelsgegevens lezen en de kloofanalyse draaien (HR-pilot dag 1). Tot dan vroeg
        #: dit `tools:admin`, waardoor alleen een beheerder het pakket kon gebruiken.
        "hr:read",
        #: Taken aanmaken en wijzigen (besluit Rakesh 2026-10-23: een medewerker mag via een workflow taken maken).
        #: Smaller dan `tools:write`, dat elke schrijftool opent (ook bestanden schrijven); `delete_task` blijft
        #: `tools:admin`. Alleen de rol `editor` krijgt dit recht (en de beheerder via `*:*`).
        "tasks:write",
        #: Een inkoopfactuur door de crediteurenagent laten verwerken (crediteuren dag 2). Hetzelfde recht als het
        #: vastleggen in het scherm (rol `crediteuren`); het goedkeuren van een uitzondering is `payables:approve`.
        "payables:write",
    }
)


class RBACService:
    """Beslist of een MENS een tool mag laten uitvoeren, op basis van `role_permissions`."""

    async def user_has_scope_for(
        self, user_id: int, action_type: str, *, tenant_id: int | None = None
    ) -> bool:
        """Mag deze MENS deze actie laten uitvoeren? (ADR-017 gatekeeper, RC-004)

        Twee soorten `action_type` komen hier binnen, en ze worden verschillend behandeld:

        1. **Chat-acties van de copilot** (`_COUNCIL_ALLOWED_ACTION_TYPES`). Ongewijzigd:
           naam op de lijst is genoeg. Dat gedrag bestaat sinds BE-GOV-001 en verschuift hier
           NIET -- deze wijziging gaat over toolnamen die daar niet op staan.

        2. **Toolnamen van de ToolBroker** (SP-COUNCIL-GATE-001). Die stonden op geen enkele
           lijst, dus de SecurityOfficer gaf `MISSING_SCOPE` en geen enkele agent voerde ooit
           een tool uit. Ze simpelweg aan de lijst toevoegen zou het omgekeerde gat maken:
           dan mag IEDERE gebruiker via een agent IEDERE tool draaien, inclusief een leesactie
           op personeelsgegevens. Daarom erft de actie het recht van de aanvragende mens --
           de agent is een hulpmiddel, nooit een rechtenverhoging.

        **Een bron van waarheid (ADR-036 OP-143, 2026-10-09).** Het vereiste recht komt uit
        `tool_risk_levels.yml` als `resource:actie`; of de gebruiker het heeft beslist de
        database (`role_permissions`, via `services.rbac_service.RBACService`), dezelfde bron
        als de HTTP-routes. Tot die dag stond hier een eigen matrix in de code
        (een vaste rolmatrix) die de database nooit las.

        `tenant_id` is verplicht voor het tweede geval en heeft met opzet GEEN terugval op de
        ContextVar: dan zou een autorisatie-antwoord afhangen van ambient toestand die in een
        Dramatiq-worker of een geneste aanroep niet gegarandeerd bij dit voorstel hoort.
        Ontbreekt hij, dan is het antwoord nee (Gate 2-review, H2).

        Weigert bij: onbekende tool (strengste eis), onbekende of verwijderde gebruiker,
        gebruiker uit een andere tenant, rol zonder het vereiste recht, en een onbekende of
        wildcard-rechtennaam in de configuratie.
        """
        if action_type in _COUNCIL_ALLOWED_ACTION_TYPES:
            return True

        return await self.user_has_tool_right(user_id, action_type, tenant_id=tenant_id)

    async def user_has_tool_right(
        self, user_id: int, action_type: str, *, tenant_id: int | None = None
    ) -> bool:
        """Heeft deze MENS het recht dat `tool_required_permission` voor deze tool vraagt?

        Dit is de tweede helft van `user_has_scope_for`, zonder de kortsluiting voor de
        copilot-chatacties. Een workflowstap mag die kortsluiting niet gebruiken: `create_task`,
        `update_task` en `delete_task` staan op die lijst en zouden dan voor IEDEREEN waar zijn
        (OP-142), terwijl de configuratie er `tools:write` of `tools:admin` voor vraagt.
        Zelfde weigerregels als hierboven: geen tenant, onbekende tool, onbekend recht, onbekende of
        vreemde gebruiker.
        """
        if tenant_id is None:
            logger.warning(
                "Scope-controle zonder tenant voor actie %r (gebruiker %s) -- geweigerd",
                action_type,
                user_id,
            )
            return False

        vereist = _tool_risk_classifier().required_permission(action_type)
        if vereist is None:
            logger.warning(
                "Tool %r heeft geen regel in tool_required_permission -- geweigerd voor "
                "iedereen, ook voor een beheerder (zero-trust)",
                action_type,
            )
            return False

        if vereist not in TOOL_RECHTEN:
            logger.error(
                "Onbekend recht %r voor tool %r in tool_risk_levels.yml -- geweigerd",
                vereist,
                action_type,
            )
            return False

        resource, _, actie = vereist.partition(":")
        toegestaan = await self._gebruiker_heeft_recht(user_id, tenant_id, resource, actie)
        if not toegestaan:
            logger.info(
                "Gebruiker %s (tenant %s) mist %s voor tool %r",
                user_id,
                tenant_id,
                vereist,
                action_type,
            )
        return toegestaan

    async def user_has_resource_right(
        self, user_id: int, resource: str, actie: str, *, tenant_id: int | None = None
    ) -> bool:
        """Heeft deze MENS dit recht (`resource:actie`) in deze klant? Voor een stap die zonder tool data leest.

        Zelfde weigerregels als `user_has_tool_right`: geen klant geeft nee. Een agentstap die geen tool uitvoert
        (btw-overzicht, bonnensamenvatting) heeft geen toolnaam om te toetsen, dus toetst hij het leesrecht dat de
        API voor dezelfde gegevens eist.
        """
        if tenant_id is None:
            return False
        return await self._gebruiker_heeft_recht(user_id, tenant_id, resource, actie)

    async def _gebruiker_heeft_recht(
        self, user_id: int, tenant_id: int, resource: str, actie: str
    ) -> bool:
        """Heeft deze gebruiker BINNEN deze tenant dit recht in `role_permissions`?

        Twee controles, en de tweede is niet genoeg zonder de eerste: de database-RBAC kijkt
        alleen naar rollen (`user_has_permission`), terwijl deze functie belooft te weigeren
        voor een onbekende, gedeactiveerde, verwijderde of tenant-vreemde GEBRUIKER. Een
        gedeactiveerde gebruiker met een geldige rol zou anders door de rechtencontrole komen.

        Expliciet `User.tenant_id == tenant_id` en niet leunen op de ADR-004-hook: die is
        alleen geregistreerd wanneer `app_lifespan` heeft gedraaid, dus in een worker of een
        test zou het filter er stilzwijgend niet zijn (CLAUDE.md regel 11).

        **Eigen sessie en `adopt_tenant` (ADR-036 OP-155, OP-154 stap 2).** Deze functie draait
        ook in workers en achtergrondtaken, buiten elk verzoek, en opent daarom een EIGEN
        sessie zonder tenantcontext. Onder `sanskritisetu_app` geeft elke SELECT dan nul rijen
        ZONDER foutmelding (OP-155), en `user_has_permission` slikt een fout als `False`: iedereen,
        ook een beheerder, zou `MISSING_SCOPE` krijgen met de verkeerde reden. Gemeten in
        `tests/integration/security/test_tools_rechten_uit_de_database_onder_de_applicatierol.py`:
        zonder `adopt_tenant` worden de drie toestaantests rood. `tenant_id` is de
        parameter van deze functie -- hij komt van de aanroeper en NOOIT uit invoer -- en de
        predicaten blijven staan: de policy is een tweede slot, geen vervanging van het eerste.
        """
        from sqlalchemy import select

        from src.core.database.bypass_session import adopt_tenant
        from src.core.database.database import db_manager
        from src.core.models.rbac_models import User
        from src.core.services.rbac_service import RBACService as DatabaseRBACService

        async with db_manager.get_session() as db:
            async with adopt_tenant(db, tenant_id):
                gebruiker = await db.execute(
                    select(User.id).where(
                        User.id == user_id,
                        User.tenant_id == tenant_id,
                        User.is_active.is_(True),
                        User.deleted_at.is_(None),
                    )
                )
                if gebruiker.scalar_one_or_none() is None:
                    return False
                return await DatabaseRBACService(db).has_permission(
                    user_id, resource, actie, tenant_id=tenant_id
                )


# Global RBAC service instance
rbac_service = RBACService()


# Import require_permission from dependencies and create alias
# Note: This is imported here to avoid circular imports
def RequirePermission(
    permission: Permission,
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator voor RBAC permission checking.
    Dit is een alias naar de require_permission dependency voor consistente naming.

    Usage:
        @router.get("/endpoint")
        @RequirePermission(Permission.ADMIN)
        async def my_endpoint(current_user: UserResponse = Depends(get_current_user)):
            ...

    Args:
        permission: Required permission enum

    Returns:
        Dependency function that validates permission

    Raises:
        HTTPException 403: Permission denied
    """

    # Return dependency as a decorator-style function
    # This allows @RequirePermission(Permission.X) syntax
    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
        # Store permission metadata on function
        func.__required_permission__ = permission  # type: ignore[attr-defined]
        return func

    return decorator


# Circular import removed: require_permission must be imported from dependencies.py directly

__all__ = [
    "Permission",
    "TOOL_RECHTEN",
    "RBACService",
    "rbac_service",
    "RequirePermission",
]
