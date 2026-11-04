"""
GraphTopologyValidator - Validates React Flow graph structure before execution.

This module provides validation for workflow graphs to ensure:
1. Exactly one trigger node exists
2. No cycles in the graph (DAG requirement)
3. All nodes are connected (no orphans)
4. All edge references are valid
5. Graph size limits are respected (DoS prevention)
"""

from collections import defaultdict
from typing import Any, Optional


# Custom Exception Classes
class GraphValidationError(ValueError):
    """Base exception for graph validation errors."""

    pass


class CycleDetectedError(GraphValidationError):
    """Raised when a cycle is detected in the graph."""

    pass


class MissingTriggerError(GraphValidationError):
    """Raised when no trigger node is found."""

    pass


class MultipleTriggerError(GraphValidationError):
    """Raised when multiple trigger nodes are found."""

    pass


class OrphanNodeError(GraphValidationError):
    """Raised when disconnected (orphan) nodes are found."""

    pass


class InvalidEdgeError(GraphValidationError):
    """Raised when an edge references a non-existent node."""

    pass


class GraphLimitError(GraphValidationError):
    """Raised when graph exceeds size limits."""

    pass


class GraphTopologyValidator:
    """
    Validates the topology of a React Flow graph for workflow execution.

    Ensures the graph is a valid DAG (Directed Acyclic Graph) with exactly
    one trigger node and no orphan nodes.
    """

    MAX_NODES = 100
    MAX_EDGES = 500
    TRIGGER_TYPES = {"trigger"}  # Node types considered as triggers

    def __init__(self, graph: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """
        Initialize validator with a React Flow graph structure.

        Args:
            graph: Dict[str, Any] with 'nodes' and 'edges' keys  # TODO(TYPE): replace Any with concrete type
        """
        self.nodes: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.edges: list[dict[str, Any]] = graph.get("edges", [])  # TODO(TYPE): replace Any with concrete type

        # Build node lookup
        for node in graph.get("nodes", []):
            node_id = node.get("id")
            if node_id:
                self.nodes[node_id] = node

        # Build adjacency lists (both directions for connectivity check)
        self.adjacency: dict[str, list[str]] = defaultdict(list)
        self.reverse_adjacency: dict[str, list[str]] = defaultdict(list)
        self._build_adjacency()

    def _build_adjacency(self) -> None:
        """Build adjacency lists from edges."""
        for edge in self.edges:
            source = edge.get("source")
            target = edge.get("target")
            if source and target:
                self.adjacency[source].append(target)
                self.reverse_adjacency[target].append(source)

    def validate(self) -> bool:
        """
        Run all validations on the graph.

        Returns:
            True if valid

        Raises:
            GraphValidationError: If any validation fails
        """
        self._check_limits()
        self._check_edge_references()
        self._check_single_trigger()
        self._check_connected()
        self._check_no_cycles()
        return True

    def _check_limits(self) -> None:
        """Check that graph doesn't exceed size limits."""
        if len(self.nodes) > self.MAX_NODES:
            raise GraphLimitError(
                f"Graph exceeds maximum node limit: {len(self.nodes)} > {self.MAX_NODES}"
            )
        if len(self.edges) > self.MAX_EDGES:
            raise GraphLimitError(
                f"Graph exceeds maximum edge limit: {len(self.edges)} > {self.MAX_EDGES}"
            )

    def _check_edge_references(self) -> None:
        """Check that all edges reference existing nodes."""
        for edge in self.edges:
            source = edge.get("source")
            target = edge.get("target")

            if source and source not in self.nodes:
                raise InvalidEdgeError(f"Edge references non-existent source node: {source}")
            if target and target not in self.nodes:
                raise InvalidEdgeError(f"Edge references non-existent target node: {target}")

    def _check_single_trigger(self) -> None:
        """Check that exactly one trigger node exists."""
        triggers: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for node_id, node in self.nodes.items():
            node_type = node.get("type", "").lower()
            if node_type in self.TRIGGER_TYPES:
                triggers.append(node_id)

        if len(triggers) == 0:
            raise MissingTriggerError("Graph must contain exactly one trigger node. Found: 0")
        if len(triggers) > 1:
            raise MultipleTriggerError(
                f"Graph must contain exactly one trigger node. Found {len(triggers)}: {triggers}"
            )

    def _check_connected(self) -> None:
        """Check that all nodes are reachable from the trigger."""
        if not self.nodes:
            return  # Empty graph handled by trigger check

        # Find the trigger node
        trigger_id: str | None = None
        for node_id, node in self.nodes.items():
            node_type = node.get("type", "").lower()
            if node_type in self.TRIGGER_TYPES:
                trigger_id = node_id
                break

        if not trigger_id:
            return  # Handled by trigger check

        # BFS from trigger to find all reachable nodes
        visited: set[str] = set()
        queue = [trigger_id]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            # Add all neighbors (both directions for undirected connectivity)
            for neighbor in self.adjacency.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)
            for neighbor in self.reverse_adjacency.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)

        # Check for orphan nodes
        orphans = set(self.nodes.keys()) - visited
        if orphans:
            raise OrphanNodeError(
                f"Graph contains orphan nodes not connected to trigger: {list(orphans)}"
            )

    def _check_no_cycles(self) -> None:
        """
        Check for cycles using DFS with recursion stack tracking.

        Uses the standard algorithm for cycle detection in directed graphs:
        - Track visited nodes globally
        - Track nodes in current recursion stack
        - A cycle exists if we visit a node already in the recursion stack
        """
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node_id: str) -> bool:
            """
            DFS helper that returns True if a cycle is found.
            """
            visited.add(node_id)
            rec_stack.add(node_id)

            for neighbor in self.adjacency.get(node_id, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    # Found a back edge - cycle detected
                    return True

            rec_stack.remove(node_id)
            return False

        # Run DFS from each unvisited node
        for node_id in self.nodes:
            if node_id not in visited:
                if dfs(node_id):
                    raise CycleDetectedError(f"Cycle detected in graph involving node: {node_id}")
