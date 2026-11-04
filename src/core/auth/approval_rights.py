"""Goedkeuren is een procesbevoegdheid, geen beheerdersrecht (ADR-039 F1/F2/F7).

Besluit Rakesh 2026-10-09: "Een beheerder heeft niets te maken met een proces dat geaccordeerd
moet worden" en "in een klein bedrijf mag 1 persoon alle rollen beslaan".

Wie een HITL-ticket mag beslissen, volgt uit de database-RBAC (`role_permissions`) en niet uit de
naam van een rol. Er is een recht PER PROCES: `receivables:approve` (debiteuren) en `hr:approve`
(personeel). Welk recht bij een ticket hoort, staat in de twee tabellen hieronder; een actie of
agent die er niet in staat, wordt geweigerd (fail-closed) -- nieuwe processen vragen dus eerst een
regel hier, bewaakt door `tests/architecture/test_goedkeurrecht_per_actie.py`.

De beheerder (`*:*`) heeft deze rechten NIET: `RBACService.user_has_permission` laat de actie
`approve` alleen toe op een rij met precies die resource en actie. Een platform-superuser komt
er evenmin langs (F7): `is_admin` speelt hier niet mee, alleen de rechten die hij in DEZE tenant
heeft. Zelfgoedkeuring en de vier-ogen-instelling blijven in de routers zelf geregeld.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.exceptions import ApprovalRightRequiredError

RECEIVABLES_APPROVE = "receivables:approve"
HR_APPROVE = "hr:approve"
#: Een uitzondering van de crediteurenagent goedkeuren (onbekende leverancier, afwijkend IBAN); rol `goedkeurder`.
PAYABLES_APPROVE = "payables:approve"
#: Algemeen goedkeurrecht voor acties zonder eigen proces (e-mail versturen, documenten of taken
#: verwijderen); zit in de rol `goedkeurder` (besluit Rakesh 2026-10-10).
GOVERNANCE_APPROVE = "governance:approve"
#: Configuratie via serena inrichten: de BEHEERDER, als expliciet recht in de rol `admin`
#: (de actie `approve` komt nooit via `*:*`; besluit Rakesh 2026-10-10).
CONFIG_APPROVE = "config:approve"

#: Het broker-tool van het ticket naar het recht dat de beslisser nodig heeft.
RECHT_PER_TOOL: Mapping[str, str] = {
    "send_payment_reminder": RECEIVABLES_APPROVE,
    "schedule_training": HR_APPROVE,
    "propose_supplier_invoice": PAYABLES_APPROVE,
    "propose_payment_run": PAYABLES_APPROVE,
    "local__send_email": GOVERNANCE_APPROVE,
    # ActivePieces-acties die naar buiten gaan (ADR-040 B12): zelfde recht als `local__send_email`,
    # geen nieuw recht en dus geen nieuwe rolzaaiing.
    "gmail.send_email": GOVERNANCE_APPROVE,
    "slack.send_message": GOVERNANCE_APPROVE,
    "google-calendar.create_event": GOVERNANCE_APPROVE,
    "serena__delete_document": GOVERNANCE_APPROVE,
    "delete_task": GOVERNANCE_APPROVE,
    "serena__admin_config": CONFIG_APPROVE,
}

#: De agent van een gatekeeper-ticket (`hitl_requests.agent_id`) naar het recht.
RECHT_PER_AGENT: Mapping[str, str] = {
    "dunning": RECEIVABLES_APPROVE,
    "crediteuren": PAYABLES_APPROVE,
    "skillsgaptraining": HR_APPROVE,
    "internalmobility": HR_APPROVE,
    "employeesentiment": HR_APPROVE,
}

ALLE_PROCESRECHTEN: frozenset[str] = frozenset(
    {*RECHT_PER_TOOL.values(), *RECHT_PER_AGENT.values()}
)


def _forbidden(message: str) -> ApprovalRightRequiredError:
    return ApprovalRightRequiredError(message)


async def has_approval_right(db: AsyncSession, user: UserResponse, right: str) -> bool:
    """Heeft deze gebruiker dit goedkeurrecht in ZIJN tenant, via zijn databaserollen?

    Geen uitzondering voor beheerder, `system_admin` of platform-superuser: alleen een rij in
    `role_permissions` telt.
    """
    # Lokaal: `rbac_service` zit ver van de auth-laag; zo blijft deze module licht.
    from src.core.database.bypass_session import adopt_tenant
    from src.core.services.rbac_service import RBACService

    async with adopt_tenant(db, int(user.tenant_id)):
        return await RBACService(db).user_has_permission(
            int(user.id), right, tenant_id=int(user.tenant_id)
        )


async def require_any_approval_right(db: AsyncSession, user: UserResponse) -> None:
    """403 tenzij de gebruiker minstens een procesrecht heeft (lijst met openstaande tickets)."""
    for right in sorted(ALLE_PROCESRECHTEN):
        if await has_approval_right(db, user, right):
            return
    raise _forbidden("U heeft geen recht om aanvragen goed te keuren of af te keuren")


async def require_approval_right_for_tool(
    db: AsyncSession, user: UserResponse, tool_name: str
) -> None:
    """403 tenzij de gebruiker het recht heeft dat bij de ACTIE (tool) van het ticket hoort."""
    right = RECHT_PER_TOOL.get(tool_name)
    if right is None or not await has_approval_right(db, user, right):
        raise _forbidden("U heeft het goedkeurrecht voor deze actie niet")


async def require_approval_right_for_agent(
    db: AsyncSession, user: UserResponse, agent_id: str | None
) -> None:
    """403 tenzij de gebruiker het recht heeft dat bij de agent van het ticket hoort."""
    right = RECHT_PER_AGENT.get((agent_id or "").strip().lower())
    if right is None or not await has_approval_right(db, user, right):
        raise _forbidden("U heeft het goedkeurrecht voor deze actie niet")


async def tools_the_user_may_decide(db: AsyncSession, user: UserResponse) -> list[str]:
    """De tools waarvan de gebruiker de tickets mag beslissen (lijst met openstaande tickets).

    Een beslisser ziet alleen wat hij mag beslissen: de lijst geeft het ONBEWERKTE `tool_input`
    (OP-56), en de beheerder met `config:approve` hoort daarmee geen debiteurenbrief te lezen.
    """
    rechten = {r for r in ALLE_PROCESRECHTEN if await has_approval_right(db, user, r)}
    return sorted(tool for tool, recht in RECHT_PER_TOOL.items() if recht in rechten)
