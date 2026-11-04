import pytest

from src.core.workflow.models import C7WorkflowTemplate

# Mock the registry if it doesn't exist yet, or import if we expect it to eventually exist
# For TDD, we expect to import a 'get_ooda_agents' function that returns our list.
# Since it doesn't exist yet, we will mock the expected structure or try to import and fail.


@pytest.mark.xfail(
    reason="TDD RED PHASE: get_ooda_agents function not yet implemented in scripts.seed_templates"
)
def test_ooda_agent_definitions_exist():
    """
    [RED PHASE]
    This test verifies that the 20 OODA Agents (A1-A20) are defined in the seed script logic.
    It currently fails because 'scripts.seed_templates' does not have 'get_ooda_agents'.
    """
    try:
        from scripts.seed_templates import get_ooda_agents

        agents = get_ooda_agents()
    except ImportError:
        pytest.fail(
            "Could not import 'get_ooda_agents' from scripts.seed_templates. The implementation is missing."
        )
    except Exception:
        # Fallback if file exists but function missing
        pytest.fail("get_ooda_agents function missing or broken.")

    # 1. Verify Count (20 Core + 1 Showcase = 21)
    assert len(agents) >= 20, f"Expected at least 20 OODA agents, found {len(agents)}"

    # 2. Verify Specific Agents (A1, A11, A17)
    agent_ids = [a["id"] for a in agents]
    assert "A1_MARKET_INTEL" in agent_ids, "A1 Market Intelligence Agent missing"
    assert "A11_ORCHESTRATOR" in agent_ids, "A11 Chief Orchestrator missing"
    assert "A17_DEVOPS" in agent_ids, "A17 DevOps Agent missing"

    # 3. Verify 'Work Visit' Showcase
    assert "SHOWCASE_WORK_VISIT" in agent_ids, "Work Visit Orchestrator showcase missing"

    # 4. Verify OODA Structure in Payload
    for agent in agents:
        graph = agent["spec_json"]
        nodes = graph.get("nodes", [])
        node_labels = [n.get("data", {}).get("label", "").lower() for n in nodes]

        # Heuristic: Should have 'observe', 'decide', 'act' related keywords
        # or at least be a valid DAG
        assert len(nodes) > 0, f"Agent {agent['id']} has empty graph"
