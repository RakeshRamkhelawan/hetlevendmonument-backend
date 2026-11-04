"""Fase 1 -- prana cost model (ADR-021). Single source of truth for the cost table
and the copilot action_type -> agent-type tier classification.
"""

import pytest

from src.core.governance import prana_costs


@pytest.mark.unit
def test_cost_table_matches_adr021():
    """The ADR-021 per-agent-type cost tiers must be exactly ml/llm/vision/hybrid."""
    assert prana_costs.AGENT_COSTS == {"ml": 10, "llm": 50, "vision": 100, "hybrid": 75}


@pytest.mark.unit
def test_read_action_is_cheapest_tier():
    """A read (list_) copilot action maps to the ml tier (cheapest)."""
    assert prana_costs.tier_for_action("list_tasks") == "ml"
    assert prana_costs.cost_for_action("list_tasks") == 10


@pytest.mark.unit
def test_write_action_is_llm_tier():
    """A mutating (create_/update_/delete_) copilot action maps to the llm tier."""
    for action in ("create_task", "update_task_status", "delete_task"):
        assert prana_costs.tier_for_action(action) == "llm", action
        assert prana_costs.cost_for_action(action) == 50, action


@pytest.mark.unit
def test_unknown_action_defaults_to_cheapest_failsafe():
    """An unknown/free-form action_type falls back to the cheapest tier (fail-safe)."""
    assert prana_costs.tier_for_action("noop") == "ml"
    assert prana_costs.cost_for_action("") == 10
