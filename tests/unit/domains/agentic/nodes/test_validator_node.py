import pytest

from src.domains.agentic.graph.state import AgentState

# We expect this import to fail initially
try:
    from src.domains.agentic.nodes.validator import validate_graph_node
except ImportError:
    validate_graph_node = None


def test_validator_node_exists():
    assert validate_graph_node is not None, "Validator node module not found"


def test_validator_valid_graph():
    if not validate_graph_node:
        pytest.fail("Validator node not implemented")

    state = AgentState(
        input="test",
        chat_history=[],
        focus_flow={"nodes": [{"id": "1", "data": {"label": "Node 1"}}], "edges": []},
    )

    result = validate_graph_node(state)
    assert "error" not in result.get("focus_flow", {}), "Valid graph should not have errors"
    assert result["focus_flow"]["validation_status"] == "valid"


def test_validator_missing_nodes():
    if not validate_graph_node:
        pytest.fail("Validator node not implemented")

    state = AgentState(input="test", chat_history=[], focus_flow={"edges": []})  # Missing nodes

    result = validate_graph_node(state)
    assert "error" in result["focus_flow"], "Missing nodes should be an error"


def test_validator_malformed_structure():
    if not validate_graph_node:
        pytest.fail("Validator node not implemented")

    state = AgentState(input="test", chat_history=[], focus_flow="INVALID_STRING")  # Not a dict

    result = validate_graph_node(state)
    assert "error" in result["focus_flow"]
