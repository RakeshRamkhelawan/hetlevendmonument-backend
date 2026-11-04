"""Focus Builder internal agent loader.

Verplaatst vanuit src.core.api.v1.focus_builder.agents (SP-API-009 Dag 3)
om de agent_runtime -> core_api circulaire afhankelijkheid te verwijderen (ADR-033 criterium 4).

Consumenten:
  - src.core.agents.focus_builder_chat_agent (agent_runtime domein)
  - src.core.api.v1.focus_builder.agents (re-export shim, backward-compat)
"""

from typing import Any

from loguru import logger

# Department -> icon identifier mapping.
# NOTE: ASCII identifiers per CLAUDE.md (NOOIT non-ASCII in code).
# TODO(SP-API-010): afstemmen met frontend welke icon-namen gebruikt worden.
_DEPT_ICONS: dict[str, str] = {
    "strategy_business": "target",
    "product_innovation": "lightbulb",
    "operations_supply_chain": "cog",
    "sales_marketing": "chart",
    "finance_treasury": "coin",
    "hr_culture": "people",
    "it_security": "lock",
    "legal_compliance": "scale",
    "customer_experience": "star",
    "data_ai_governance": "robot",
}

# Technology -> category mapping
_TECH_CATEGORY: dict[str, str] = {
    "LLM": "ai",
    "llm": "ai",
    "ML": "ml",
    "ml": "ml",
    "HYBRID": "ai",
    "hybrid": "ai",
    "VISION": "vision",
    "vision": "vision",
}

_INTERNAL_AGENTS_CACHE: list[dict[str, Any]] | None = None  # TODO(TYPE): replace Any


def _build_als_agents() -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Load all agents from AGENT_REGISTRY + AgentCatalogLoader for description/integrations."""
    try:
        from src.core.als.agents.departments import AGENT_REGISTRY
        from src.core.als.agents.loader import AgentCatalogLoader

        loader = AgentCatalogLoader()
        agents = []
        for agent_id, (dept, class_name, tech) in AGENT_REGISTRY.items():
            name = agent_id.replace("_", " ").title()
            loader_key = AgentCatalogLoader._normalize_agent_key(class_name)
            config = loader.agents.get(loader_key)
            agents.append(
                {
                    "id": agent_id,
                    "name": name,
                    "category": _TECH_CATEGORY.get(tech, "ai"),
                    "icon": _DEPT_ICONS.get(dept, "tool"),
                    "source": "internal",
                    "is_connected": True,
                    "department": dept,
                    "description": config.description or "" if config else "",
                    "required_integrations": config.required_integrations if config else [],
                }
            )
        agents.sort(key=lambda a: (a["department"], a["name"]))
        logger.info("Loaded %s ALS agents into focus-builder agent list", len(agents))
        return agents
    except Exception as exc:
        logger.warning(
            "Could not load ALS AGENT_REGISTRY: %s: %s", type(exc).__name__, exc, exc_info=True
        )
        return []


def _get_internal_agents() -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Lazy loader: builds the internal agent list once, on first real use."""
    global _INTERNAL_AGENTS_CACHE
    if _INTERNAL_AGENTS_CACHE is None:
        als_agents = _build_als_agents()
        _INTERNAL_AGENTS_CACHE = [
            {
                "id": "workflow_generator_agent",
                "name": "Workflow Generator",
                "category": "ai",
                "icon": "brain",
                "source": "internal",
                "is_connected": True,
                "department": None,
            },
            *als_agents,
        ]
    return _INTERNAL_AGENTS_CACHE
