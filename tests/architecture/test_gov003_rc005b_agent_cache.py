"""Architecture test: AgentRegistry cache MOET tenant-aware zijn (RC-005b).

TODO(SP-GOV-003): fix agent_registry.py -- voeg tenant_id verificatie toe in get_agent() cache pad
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_agent_registry_cache_is_tenant_aware() -> None:
    """RC-005b: cache hit in get_agent() MOET tenant_id verifiëren voor retourneren.

    Acceptabele patronen:
    - tuple-keyed dict: dict[tuple[int | None, str], Agent]
    - tenant_id check op gecachede agent: cached_agent.tenant_id of getattr(cached_agent, ...)
    """
    src = (_REPO_ROOT / "src/core/agents/agent_registry.py").read_text(encoding="utf-8")
    has_tenant_aware_cache = (
        "dict[tuple[" in src or "cached_agent.tenant_id" in src or "getattr(cached_agent" in src
    )
    assert has_tenant_aware_cache, (
        "RC-005b: AgentRegistry.get_agent() retourneert cache hit zonder tenant_id verificatie -- "
        "voeg tenant check toe: cached_agent.tenant_id == resolved_tenant_id"
    )
