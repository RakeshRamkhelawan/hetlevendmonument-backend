"""De identiteit en de broker van een workflowstap (ADR-036 OP-13, brief 2026-10-22).

Een workflowstap die een tool uitvoert draait onder de identiteit `workflow_engine`. Het permissieprofiel staat in
`config/tool_permissions.yml` (default-deny, bewust klein). Deze module bouwt de `ToolBrokerService` waarmee de
workflow-engine die tool uitvoert, zodat `src/core/workflow/providers.py` een enkele afhankelijkheid van `tool_broker`
heeft in plaats van vier (de koppelingsmeter in `tests/architecture/test_dsm_008_reclassification.py` telt elke import).

Een tool met hoog risico (HITL) wordt door de broker geweigerd zonder ticket: een workflowstap kan geen goedkeuring
afwachten, dus hij faalt zichtbaar in plaats van te blijven hangen.

Logboek: deze broker krijgt een `audit_session_factory` (F7, 2026-10-26), dus een workflowtoolstap schrijft een regel in
`tool_audit_logs`. De repository is aan een klant gebonden; de broker is dat niet. Daarom bouwt de broker de repository
PER REGEL, op een eigen korte sessie en voor de klant van die aanroep (uit de executiecontext, nooit uit de payload).
Stappen van verschillende klanten halen zo geen gedeelde sessie of keten door elkaar. Het schrijven is best effort en
loopt onder het slot per klant van de ketenvolgorde (`audit_repository.TOOL_AUDIT_LOCK_RUIMTE`). Daarnaast blijven de
taakregel van de stap (`c7_execution_tasks`) en de gebeurtenissen van de uitvoering.
"""

from __future__ import annotations

import importlib
from typing import cast

from src.core.tool_broker.hitl_store import HITLStore
from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.permission_manager import ToolPermissionManager
from src.core.tool_broker.service import ISequentialThinkingClient, ISerenaClient, ToolBrokerService

#: De identiteit waaronder een workflowstap een tool uitvoert.
WORKFLOW_IDENTITEIT = "workflow_engine"


class _GeenClient:
    """Een workflowstap gebruikt geen Serena of Sequential Thinking; die clients doen hier niets."""

    async def call(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
        return {"success": False, "tool": tool_name, "noop": True}


def bouw_workflow_broker() -> ToolBrokerService:
    """De `ToolBrokerService` voor workflowstappen, met de databasesessies van het proces zelf."""
    db_manager = importlib.import_module("src.core.database.database").db_manager
    return ToolBrokerService(
        serena_client=cast(ISerenaClient, _GeenClient()),
        seq_thinking_client=cast(ISequentialThinkingClient, _GeenClient()),
        local_registry=LocalToolRegistry(),
        enable_resilience=False,
        hitl_store=HITLStore(session_factory=db_manager.get_session),
        audit_session_factory=db_manager.get_session,
    )


async def starter_heeft_toolrecht(starter: str | None, tool_name: str, tenant_id: int) -> bool:
    """Heeft de MENS die de workflow startte het recht dat deze tool vraagt, in de klant van de uitvoering?

    Een workflowstap mag alleen wat ZOWEL `workflow_engine` (het profiel, bovengrens) ALS de starter mag. Dit is
    de tweede helft. Hij wordt bij het UITVOEREN van de stap gevraagd, dus een recht dat na het starten is
    ingetrokken telt niet meer. Fail-closed: geen starter, een starter die geen positief geheel getal is
    (`initiated_by` is een tekst en kan een systeemnaam bevatten) of een starter zonder rij in deze klant geeft
    `False`. Vandaag zetten alleen de twee startroutes van de API `initiated_by`, en dat is altijd een gebruikers-id.
    """
    if starter is None or not (starter.isascii() and starter.isdigit()) or int(starter) <= 0:
        return False
    from src.core.auth.rbac import rbac_service

    return await rbac_service.user_has_tool_right(int(starter), tool_name, tenant_id=tenant_id)


def toegestane_workflowtools() -> list[str]:
    """De tools die de identiteit `workflow_engine` mag gebruiken (uit het permissieprofiel)."""
    profiel = ToolPermissionManager()._agent_profiles.get(WORKFLOW_IDENTITEIT)
    return list(profiel.allowed_tools) if profiel else []


def reden_in_gewone_taal(fout: Exception) -> str:
    """Een korte reden voor de klant; de technische tekst van de broker staat al in het log."""
    tekst = str(fout)
    if "Permission denied" in tekst or "not authorized" in tekst:
        return "deze workflow mag die tool niet gebruiken"
    if "requires human approval" in tekst:
        return "die tool vraagt goedkeuring van een mens en een workflowstap kan die niet afwachten"
    if "Unknown tool" in tekst:
        return "die tool bestaat niet"
    return tekst
