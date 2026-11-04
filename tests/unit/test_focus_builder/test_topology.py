"""
TDD Test Suite for GraphTopologyValidator

These tests are written FIRST (TDD approach) to define the expected behavior
of the GraphTopologyValidator before implementation.

Test Cases:
1. Valid linear graph should pass
2. Cycle detection should raise error
3. Missing trigger should raise error
4. Multiple triggers should raise error
5. Orphan nodes should raise error
6. Invalid edge references should raise error
7. Max nodes exceeded should raise error
8. Max edges exceeded should raise error
"""

from typing import Any, Dict, List

import pytest


def create_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Helper to create a graph structure."""
    return {"nodes": nodes, "edges": edges}


def create_node(node_id: str, node_type: str = "action", label: str = "Node") -> Dict[str, Any]:
    """Helper to create a node."""
    return {
        "id": node_id,
        "type": node_type,
        "data": {"label": label},
        "position": {"x": 0, "y": 0},
    }


def create_edge(source: str, target: str) -> Dict[str, Any]:
    """Helper to create an edge."""
    return {"id": f"e{source}-{target}", "source": source, "target": target}


class TestGraphTopologyValidator:
    """Test suite for GraphTopologyValidator."""

    def test_valid_linear_graph(self):
        """
        A valid linear graph: Trigger -> Action -> Action should pass validation.
        """
        from src.core.focus_builder.validators import GraphTopologyValidator

        graph = create_graph(
            nodes=[
                create_node("1", "trigger", "Start"),
                create_node("2", "action", "Process"),
                create_node("3", "action", "End"),
            ],
            edges=[create_edge("1", "2"), create_edge("2", "3")],
        )

        validator = GraphTopologyValidator(graph)
        result = validator.validate()
        assert result is True

    def test_cycle_detection(self):
        """
        A graph with a cycle: A -> B -> C -> A should raise CycleDetectedError.
        """
        from src.core.focus_builder.validators import CycleDetectedError, GraphTopologyValidator

        graph = create_graph(
            nodes=[
                create_node("1", "trigger", "Start"),
                create_node("2", "action", "A"),
                create_node("3", "action", "B"),
                create_node("4", "action", "C"),
            ],
            edges=[
                create_edge("1", "2"),
                create_edge("2", "3"),
                create_edge("3", "4"),
                create_edge("4", "2"),  # Creates cycle: 2 -> 3 -> 4 -> 2
            ],
        )

        validator = GraphTopologyValidator(graph)
        with pytest.raises(CycleDetectedError) as exc_info:
            validator.validate()

        assert "cycle" in str(exc_info.value).lower()

    def test_missing_trigger(self):
        """
        A graph without a trigger node should raise ValidationError.
        """
        from src.core.focus_builder.validators import GraphTopologyValidator, MissingTriggerError

        graph = create_graph(
            nodes=[
                create_node("1", "action", "Action 1"),
                create_node("2", "action", "Action 2"),
            ],
            edges=[create_edge("1", "2")],
        )

        validator = GraphTopologyValidator(graph)
        with pytest.raises(MissingTriggerError) as exc_info:
            validator.validate()

        assert "trigger" in str(exc_info.value).lower()

    def test_multiple_triggers(self):
        """
        A graph with 2+ triggers should raise ValidationError.
        """
        from src.core.focus_builder.validators import GraphTopologyValidator, MultipleTriggerError

        graph = create_graph(
            nodes=[
                create_node("1", "trigger", "Trigger 1"),
                create_node("2", "trigger", "Trigger 2"),
                create_node("3", "action", "Action"),
            ],
            edges=[create_edge("1", "3"), create_edge("2", "3")],
        )

        validator = GraphTopologyValidator(graph)
        with pytest.raises(MultipleTriggerError) as exc_info:
            validator.validate()

        assert "multiple" in str(exc_info.value).lower() or "trigger" in str(exc_info.value).lower()

    def test_orphan_nodes(self):
        """
        Nodes not connected to the main graph should raise ValidationError.
        """
        from src.core.focus_builder.validators import GraphTopologyValidator, OrphanNodeError

        graph = create_graph(
            nodes=[
                create_node("1", "trigger", "Start"),
                create_node("2", "action", "Connected"),
                create_node("3", "action", "Orphan"),  # Not connected
            ],
            edges=[
                create_edge("1", "2")
                # Node "3" has no edges
            ],
        )

        validator = GraphTopologyValidator(graph)
        with pytest.raises(OrphanNodeError) as exc_info:
            validator.validate()

        assert "orphan" in str(exc_info.value).lower() or "connected" in str(exc_info.value).lower()

    def test_invalid_edge_reference(self):
        """
        An edge pointing to a non-existent node should raise ValidationError.
        """
        from src.core.focus_builder.validators import GraphTopologyValidator, InvalidEdgeError

        graph = create_graph(
            nodes=[
                create_node("1", "trigger", "Start"),
                create_node("2", "action", "End"),
            ],
            edges=[
                create_edge("1", "2"),
                create_edge("2", "999"),
            ],  # Node "999" doesn't exist
        )

        validator = GraphTopologyValidator(graph)
        with pytest.raises(InvalidEdgeError) as exc_info:
            validator.validate()

        assert "999" in str(exc_info.value) or "invalid" in str(exc_info.value).lower()

    def test_max_nodes_exceeded(self):
        """
        A graph with more than MAX_NODES (100) should raise ValidationError.
        """
        from src.core.focus_builder.validators import GraphLimitError, GraphTopologyValidator

        # Create 101 nodes
        nodes = [create_node("0", "trigger", "Start")]
        nodes.extend([create_node(str(i), "action", f"Action {i}") for i in range(1, 101)])

        edges = [create_edge(str(i), str(i + 1)) for i in range(100)]

        graph = create_graph(nodes=nodes, edges=edges)

        validator = GraphTopologyValidator(graph)
        with pytest.raises(GraphLimitError) as exc_info:
            validator.validate()

        assert "node" in str(exc_info.value).lower() or "limit" in str(exc_info.value).lower()

    def test_max_edges_exceeded(self):
        """
        A graph with more than MAX_EDGES (500) should raise ValidationError.
        """
        from src.core.focus_builder.validators import GraphLimitError, GraphTopologyValidator

        # Create a dense graph with many edges (need enough nodes to have 501 edges)
        # For a complete graph with n nodes, edges = n*(n-1)/2
        # For 501 edges, we need about 32 nodes for complete graph
        # But we'll create a simpler case with explicit edges

        nodes = [create_node("0", "trigger", "Start")]
        nodes.extend([create_node(str(i), "action", f"Action {i}") for i in range(1, 50)])

        # Create 501 edges (some will be duplicates conceptually, but different edge IDs)
        edges = []
        edge_count = 0
        for i in range(50):
            for j in range(i + 1, 50):
                if edge_count >= 501:
                    break
                edges.append({"id": f"e{i}-{j}-{edge_count}", "source": str(i), "target": str(j)})
                edge_count += 1
            if edge_count >= 501:
                break

        graph = create_graph(nodes=nodes, edges=edges)

        validator = GraphTopologyValidator(graph)
        with pytest.raises(GraphLimitError) as exc_info:
            validator.validate()

        assert "edge" in str(exc_info.value).lower() or "limit" in str(exc_info.value).lower()

    def test_empty_graph(self):
        """
        An empty graph should raise MissingTriggerError.
        """
        from src.core.focus_builder.validators import GraphTopologyValidator, MissingTriggerError

        graph = create_graph(nodes=[], edges=[])

        validator = GraphTopologyValidator(graph)
        with pytest.raises(MissingTriggerError):
            validator.validate()

    def test_valid_branch_graph(self):
        """
        A valid branching graph should pass validation.
        Trigger -> Branch -> [Action1, Action2]
        """
        from src.core.focus_builder.validators import GraphTopologyValidator

        graph = create_graph(
            nodes=[
                create_node("1", "trigger", "Start"),
                create_node("2", "branch", "Decision"),
                create_node("3", "action", "Path A"),
                create_node("4", "action", "Path B"),
            ],
            edges=[create_edge("1", "2"), create_edge("2", "3"), create_edge("2", "4")],
        )

        validator = GraphTopologyValidator(graph)
        result = validator.validate()
        assert result is True

    def test_valid_loop_node(self):
        """
        A loop node (iteration over items) is valid and should not be confused with cycles.
        """
        from src.core.focus_builder.validators import GraphTopologyValidator

        graph = create_graph(
            nodes=[
                create_node("1", "trigger", "Start"),
                create_node("2", "loop", "For Each Item"),
                create_node("3", "action", "Process Item"),
                create_node("4", "action", "After Loop"),
            ],
            edges=[
                create_edge("1", "2"),
                create_edge("2", "3"),  # Loop body
                create_edge("2", "4"),  # After loop
            ],
        )

        validator = GraphTopologyValidator(graph)
        result = validator.validate()
        assert result is True
