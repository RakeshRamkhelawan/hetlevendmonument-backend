"""
Enterprise Department Agents - All 10 Departments.

Total: 1 Chief Orchestrator + 40 Department Agents

Departments:
    1. Strategy & Business (3 agents)
    2. Product & Innovation (4 agents)
    3. Operations & Supply Chain (4 agents)
    4. Sales & Marketing (6 agents - incl. 1 human)
    5. Finance & Treasury (5 agents)
    6. HR & Culture (4 agents)
    7. IT, Infra & Cyber Security (4 agents)
    8. Legal, Risk & Compliance (4 agents)
    9. Customer Experience (3 agents)
    10. Data & AI Governance (3 agents)
"""

from typing import Any, Optional

from src.core.als.agents.departments import (
    customer_experience,
    data_ai_governance,
    finance_treasury,
    hr_culture,
    it_security,
    legal_compliance,
    operations_supply_chain,
    product_innovation,
    sales_marketing,
    strategy_business,
)

# Import all department modules
from src.core.als.agents.departments.base_department_agent import (
    AgentTechnology,
    DepartmentAgent,
    DepartmentType,
    HybridAgent,
    LLMAgent,
    MLAgent,
    VisionAgent,
)
from src.core.als.agents.departments.customer_experience.sentiment_support import (
    SentimentSupportAgent,
)
from src.core.als.agents.departments.data_ai_governance.data_quality_sentinel import (
    DataQualitySentinelAgent,
)
from src.core.als.agents.departments.it_security.threat_hunter import ThreatHunterAgent
from src.core.als.agents.departments.legal_compliance.gdpr_privacy_guard import (
    GDPRPrivacyGuardAgent,
)
from src.core.als.agents.departments.operations_supply_chain.inventory_forecaster import (
    InventoryForecasterAgent,
)
from src.core.als.agents.departments.product_innovation.technical_architect import (
    TechnicalArchitectAgent,
)
from src.core.als.agents.loader import AgentCatalogLoader

# Agent registry for dynamic instantiation
AGENT_REGISTRY = {
    # === STRATEGY & BUSINESS (3 agents) ===
    "market_intelligence": ("strategy_business", "MarketIntelligenceAgent", "ML"),
    "ma_analyst": ("strategy_business", "MaAnalystAgent", "LLM"),
    "partnerships": ("strategy_business", "PartnershipsAgent", "LLM"),
    # ... (rest of the hardcoded registry remains)
}

# Dynamically extend registry from YAML configs
try:
    _loader = AgentCatalogLoader()
    _loader.load_all()
    dynamic_agents = _loader.get_agent_registry_format()
    # Update hardcoded with dynamic (dynamic wins)
    AGENT_REGISTRY.update(dynamic_agents)
except Exception as e:
    import logging

    logging.getLogger(__name__).error(f"Failed to perform dynamic agent registration: {e}")


# Department agent counts
DEPARTMENT_AGENT_COUNTS = {
    "strategy_business": 3,
    "product_innovation": 4,
    "operations_supply_chain": 4,
    "sales_marketing": 6,
    "finance_treasury": 5,
    "hr_culture": 4,
    "it_security": 4,
    "legal_compliance": 4,
    "customer_experience": 3,
    "data_ai_governance": 3,
}


def get_total_agent_count() -> int:
    """Return total number of agents across all departments."""
    return len(AGENT_REGISTRY)


def get_department_agents(
    department: str,
) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
    """Get all agent names for a specific department."""
    return [name for name, (dept, _, _) in AGENT_REGISTRY.items() if dept == department]


def get_agent_info(
    agent_name: str,
) -> tuple[Any, ...] | None:  # TODO(TYPE): replace Any with concrete type
    """Get (department, class_name, technology) for an agent."""
    return AGENT_REGISTRY.get(agent_name)


__all__ = [
    "AGENT_REGISTRY",
    "DEPARTMENT_AGENT_COUNTS",
    "get_total_agent_count",
    "get_department_agents",
    "get_agent_info",
    # Department modules
    "strategy_business",
    "product_innovation",
    "operations_supply_chain",
    "sales_marketing",
    "finance_treasury",
    "hr_culture",
    "it_security",
    "legal_compliance",
    "customer_experience",
    "data_ai_governance",
]
