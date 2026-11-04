from typing import Any

from src.domains.agentic.graph.state import AgentState


def validate_graph_node(state: AgentState) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Validates that the generated focus_flow has the correct structure for React Flow.
    Input: state.focus_flow
    Output: state update (adding validation_status or error)
    """
    focus_flow = state.get("focus_flow")

    # 1. Check if focus_flow is a dict
    if not isinstance(focus_flow, dict):
        return {"focus_flow": {"error": "Invalid graph format: Output must be a JSON object"}}

    # Check for existing error
    if "error" in focus_flow:
        return {"focus_flow": focus_flow}  # Pass through existing error

    # 2. Check for required keys 'nodes' and 'edges'
    nodes = focus_flow.get("nodes")
    edges = focus_flow.get("edges")

    if nodes is None or edges is None:
        return {"focus_flow": {"error": "Invalid graph format: Missing 'nodes' or 'edges' keys"}}

    if not isinstance(nodes, list) or not isinstance(edges, list):
        return {"focus_flow": {"error": "Invalid graph format: 'nodes' and 'edges' must be lists"}}

    # 3. Simple schema validation (ids, labels)
    for node in nodes:
        if "id" not in node or "data" not in node:
            return {"focus_flow": {"error": f"Invalid node format: Missing id or data in {node}"}}

    # If valid, mark as valid
    updated_flow = focus_flow.copy()
    updated_flow["validation_status"] = "valid"

    return {"focus_flow": updated_flow}
