"""Prana cost model (ADR-021) -- single source of truth.

ADR-021 defines a per-agent-type cost table (prana spent per execution). Copilot
actions do not carry an agent-type, so this module also classifies a free-form
copilot ``action_type`` into a tier: reads are cheap (ml), mutations cost more (llm),
and anything unrecognised falls back to the cheapest tier (fail-safe -- never
over-charge a tenant for an action we cannot classify).
"""

from __future__ import annotations

# ADR-021: prana cost per execution, keyed by agent-type tier.
AGENT_COSTS: dict[str, int] = {
    "ml": 10,
    "llm": 50,
    "vision": 100,
    "hybrid": 75,
}

# Fail-safe tier for unknown/free-form action types: the cheapest, so an
# unclassifiable action can never over-charge.
DEFAULT_TIER = "ml"

# Copilot action_type -> tier. Prefix-based because action_type is a free string
# (tool name from the LLM), not an enum.
_READ_PREFIXES = ("list_", "get_", "search_", "read_", "fetch_", "verify_")
_WRITE_PREFIXES = (
    "create_",
    "update_",
    "delete_",
    "send_",
    "export_",
    "publish_",
    "share_",
)


def tier_for_action(action_type: str) -> str:
    """Classify a copilot action_type into an ADR-021 agent-type tier."""
    action = (action_type or "").lower()
    if action.startswith(_READ_PREFIXES):
        return "ml"
    if action.startswith(_WRITE_PREFIXES):
        return "llm"
    return DEFAULT_TIER


def cost_for_tier(tier: str) -> int:
    """Prana cost for an agent-type tier (unknown tier -> cheapest)."""
    return AGENT_COSTS.get(tier, AGENT_COSTS[DEFAULT_TIER])


def cost_for_action(action_type: str) -> int:
    """Prana cost for a copilot action_type (via its classified tier)."""
    return cost_for_tier(tier_for_action(action_type))
