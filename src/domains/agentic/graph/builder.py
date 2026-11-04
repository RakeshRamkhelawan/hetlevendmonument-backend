from typing import Any

from langgraph.graph import StateGraph

from src.domains.agentic.graph.state import AgentState


class WorkflowGraphBuilder:
    """Builder for the agentic workflow graph."""

    def __init__(self) -> None:
        self.graph = StateGraph(AgentState)

    def build(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Compile the graph."""
        return self.graph.compile()
