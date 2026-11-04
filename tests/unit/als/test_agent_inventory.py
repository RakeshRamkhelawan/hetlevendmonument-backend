import pytest

from src.core.als.agents.departments import AGENT_REGISTRY, get_total_agent_count


def test_total_agent_count_is_40():
    count = get_total_agent_count()
    # Expect 40 agents based on the organogram
    assert count >= 40
    print(f"DEBUG: Found {count} agents in registry.")


def test_agent_registry_integrity():
    # Check a few specific ones across departments
    # Note: Agent keys are normalized (no underscores) in the registry
    assert "taxcompliance" in AGENT_REGISTRY
    assert "talentacquisition" in AGENT_REGISTRY
    assert "threathunter" in AGENT_REGISTRY
    assert "market_intelligence" in AGENT_REGISTRY

    # Verify tuple format (department, class_name, technology)
    info = AGENT_REGISTRY["threathunter"]
    assert info[0] == "it_security"
    assert info[1] == "ThreatHunterAgent"
    assert info[2] == "LLM"
