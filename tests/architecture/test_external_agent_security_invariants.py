"""
Architecture tests: external agent security invariants.

All tests in this file are intentionally RED until the corresponding
backlog items are resolved (SP-SEC-002).
"""

import re
from pathlib import Path


ROUTER_PATH = Path("src/core/api/v1/company/external_agent_router.py")
SERVICE_PATH = Path("src/core/company/external_agent_service.py")


def test_get_next_task_and_complete_task_verify_api_key():
    """get_next_task/complete_task MOETEN api_key cryptografisch verifiëren.

    TODO(SP-SEC-002): Beide handlers doen `cred_agent_id, _ = credentials` --
    de api_key wordt weggegooid zonder bcrypt-check. Elke caller met een
    bekend agent-UUID kan tasks ophalen of voltooien zonder geldige sleutel.
    Fix: geef api_key door aan service.get_next_task() / service.complete_task()
    en voeg bcrypt-verificatie toe in de service.
    """
    src = ROUTER_PATH.read_text(encoding="utf-8")
    violation = re.search(r"cred_agent_id,\s*_\s*=\s*credentials", src)
    assert violation is None, (
        "get_next_task/complete_task gooit de api_key weg (cred_agent_id, _ = credentials). "
        "Voeg bcrypt-verificatie toe via service-methode."
    )


def test_external_agent_list_agents_has_pagination():
    """ExternalAgentService.list_agents MOET limit/offset ondersteunen.

    TODO(SP-SEC-002): list_agents() geeft alle agents terug zonder paginering.
    Onbegrensde resultaatsets zijn een DoS-vector en performance-risico.
    Fix: voeg limit en offset toe aan service.list_agents() en de router.
    """
    import inspect
    from src.core.company.external_agent_service import ExternalAgentService

    sig = inspect.signature(ExternalAgentService.list_agents)
    params = list(sig.parameters.keys())
    assert "limit" in params and "offset" in params, (
        "ExternalAgentService.list_agents heeft geen limit/offset parameters. "
        "Voeg paginering toe aan service en router."
    )


def test_api_key_endpoints_have_independent_service_dependency():
    """heartbeat/get_next_task/complete_task MOGEN GEEN JWT-dependency hebben.

    TODO(SP-SEC-002): Alle endpoints (inclusief API-key endpoints) gebruiken
    get_external_agent_service dat get_current_user (JWT) vereist.
    Externe agents hebben geen JWT -- ze authenticeren via API-key.
    Fix: maak get_agent_service_from_api_key dependency die tenant-context
    resolveert via agent-lookup in de DB (geen JWT nodig).
    """
    src = ROUTER_PATH.read_text(encoding="utf-8")
    assert "get_agent_service_from_api_key" in src, (
        "API-key endpoints (heartbeat/get_next_task/complete_task) vereisen JWT "
        "via get_external_agent_service -> get_current_user. "
        "Maak een aparte service-dependency zonder JWT-vereiste."
    )
