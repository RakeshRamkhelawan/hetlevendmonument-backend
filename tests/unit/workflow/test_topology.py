import pytest

from src.core.workflow.validator import WorkflowValidationError, validate_topology


def test_valid_linear_workflow():
    """Test a simple A -> B -> C linear workflow"""
    nodes = [
        {"id": "node_1", "type": "start"},
        {"id": "node_2", "type": "action"},
        {"id": "node_3", "type": "end"},
    ]
    edges = [
        {"source": "node_1", "target": "node_2"},
        {"source": "node_2", "target": "node_3"},
    ]
    assert validate_topology(nodes, edges) is True


def test_detect_simple_cycle():
    """Test detection of A -> B -> A cycle"""
    nodes = [{"id": "node_1", "type": "start"}, {"id": "node_2", "type": "action"}]
    edges = [
        {"source": "node_1", "target": "node_2"},
        {"source": "node_2", "target": "node_1"},
    ]
    with pytest.raises(WorkflowValidationError, match="Cycle detected"):
        validate_topology(nodes, edges)


def test_detect_self_loop():
    """Test detection of A -> A self-loop"""
    nodes = [{"id": "node_1", "type": "action"}]
    edges = [{"source": "node_1", "target": "node_1"}]
    with pytest.raises(WorkflowValidationError, match="Cycle detected"):
        validate_topology(nodes, edges)


def test_detect_disconnected_island():
    """Test detection of disconnected subgraph (Node C is isolated)"""
    nodes = [
        {"id": "node_1", "type": "start"},
        {"id": "node_2", "type": "end"},
        {"id": "node_3", "type": "action"},
    ]
    edges = [{"source": "node_1", "target": "node_2"}]
    # Enforcing that all nodes must be reachable or connected
    with pytest.raises(WorkflowValidationError, match="Disconnected subgraph detected"):
        validate_topology(nodes, edges)


def test_invalid_edge_references():
    """Test edges referring to non-existent nodes"""
    nodes = [{"id": "node_1", "type": "start"}]
    edges = [{"source": "node_1", "target": "node_999"}]
    with pytest.raises(WorkflowValidationError, match="Edge references unknown node"):
        validate_topology(nodes, edges)


def test_detect_disconnected_subgraph():
    """Test detection of two separate, internally connected chains (A->B, C->D)"""
    nodes = [
        {"id": "node_1", "type": "start"},
        {"id": "node_2", "type": "action"},
        {"id": "node_3", "type": "start"},
        {"id": "node_4", "type": "end"},
    ]
    edges = [
        {"source": "node_1", "target": "node_2"},
        {"source": "node_3", "target": "node_4"},
    ]
    # This should fail because node_3/node_4 are not reachable from node_1
    # and node_1/node_2 are not reachable from node_3.
    # The graph has 2 connected components, but we require 1.
    with pytest.raises(WorkflowValidationError, match="Disconnected subgraph detected"):
        validate_topology(nodes, edges)
