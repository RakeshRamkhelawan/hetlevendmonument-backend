from typing import Any


class WorkflowValidationError(Exception):
    """Raised when workflow topology is invalid"""

    pass


def validate_topology(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bool:  # TODO(TYPE): replace Any with concrete type
    """
    Validates the workflow graph topology.

    Checks for:
    1. Valid edges (source/target exist)
    2. Cycles (DAG violation)
    3. Connectivity (All nodes must be reachable from start nodes or part of the connected component)

    Args:
        nodes: List[Any] of node dictionaries  # TODO(TYPE): replace Any with concrete type
        edges: List[Any] of edge dictionaries  # TODO(TYPE): replace Any with concrete type

    Returns:
        bool: True if valid

    Raises:
        WorkflowValidationError: If topology is invalid
    """
    node_ids = {n["id"] for n in nodes}

    # 1. Validate Edges
    adj: dict[Any, list[Any]] = {node_id: [] for node_id in node_ids}  # TODO(TYPE): replace Any with concrete type
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")

        if source not in node_ids:
            raise WorkflowValidationError(f"Edge references unknown node: {source}")
        if target not in node_ids:
            raise WorkflowValidationError(f"Edge references unknown node: {target}")

        adj[source].append(target)

    # 2. Cycle Detection (DFS)
    visited: set[Any] = set()  # TODO(TYPE): replace Any with concrete type
    recursion_stack: set[Any] = set()  # TODO(TYPE): replace Any with concrete type

    def has_cycle(node_id: Any) -> bool:  # TODO(TYPE): replace Any with concrete type
        visited.add(node_id)
        recursion_stack.add(node_id)

        for neighbor in adj[node_id]:
            if neighbor not in visited:
                if has_cycle(neighbor):
                    return True
            elif neighbor in recursion_stack:
                return True

        recursion_stack.remove(node_id)
        return False

    for node_id in node_ids:
        if node_id not in visited:
            if has_cycle(node_id):
                raise WorkflowValidationError("Cycle detected in workflow graph")

    # 3. Connectivity Check (Weak Connectivity)
    # Ensure the graph is a single connected component (ignoring direction)
    if not node_ids:
        return True

    # Build undirected adjacency list for connectivity check
    undirected_adj: dict[Any, list[Any]] = {node_id: [] for node_id in node_ids}  # TODO(TYPE): replace Any with concrete type
    for edge in edges:
        source, target = edge["source"], edge["target"]
        undirected_adj[source].append(target)
        undirected_adj[target].append(source)

    # BFS to find all reachable nodes from the first node
    start_node = next(iter(node_ids))
    connected_visited: set[Any] = {start_node}  # TODO(TYPE): replace Any with concrete type
    queue: list[Any] = [start_node]  # TODO(TYPE): replace Any with concrete type

    while queue:
        current = queue.pop(0)
        for neighbor in undirected_adj[current]:
            if neighbor not in connected_visited:
                connected_visited.add(neighbor)
                queue.append(neighbor)

    if len(connected_visited) != len(node_ids):
        # Find which nodes are disconnected for the error message
        disconnected_nodes = list(node_ids - connected_visited)
        raise WorkflowValidationError(
            f"Disconnected subgraph detected. Unreachable nodes: {disconnected_nodes}"
        )

    return True


def topological_sort(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str]:  # TODO(TYPE): replace Any with concrete type
    """
    Returns task IDs in topological order (dependencies before dependents).
    Uses Kahn's algorithm for stability.
    """
    from collections import deque

    node_ids = {n["id"] for n in nodes}
    in_degree = {node_id: 0 for node_id in node_ids}
    adj: dict[Any, list[Any]] = {node_id: [] for node_id in node_ids}  # TODO(TYPE): replace Any with concrete type

    # Build adjacency and in-degree
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source in node_ids and target in node_ids:
            adj[source].append(target)
            in_degree[target] += 1

    # Queue of nodes with no dependencies (in-degree = 0)
    queue = deque([node_id for node_id in node_ids if in_degree[node_id] == 0])
    sorted_tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    while queue:
        node_id = queue.popleft()
        sorted_tasks.append(node_id)

        for neighbor in adj[node_id]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_tasks) != len(node_ids):
        # This should be caught by validate_topology, but as a safeguard:
        raise WorkflowValidationError("Cycle detected during topological sort")

    return sorted_tasks
