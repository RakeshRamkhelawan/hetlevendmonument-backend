import pytest
from langgraph.graph import StateGraph

from src.domains.agentic.graph.builder import WorkflowGraphBuilder
from src.domains.agentic.graph.state import AgentState


def test_builder_initialization():
    """Verify builder initializes with correct state schema."""
    builder = WorkflowGraphBuilder()
    assert isinstance(builder.graph, StateGraph)
    # Accessing the schema usually depends on LangGraph internals,
    # but we can verify the builder holds the graph.


def test_builder_compilation():
    """Verify build() returns a compiled graph."""
    builder = WorkflowGraphBuilder()

    # We need at least one node and edge to compile a valid graph usually,
    # or at least a start/end path.
    # For a base builder, maybe it just sets up the empty structure?
    # LangGraph throws validation errors if graph is empty/disconnected on compile.
    # So we might expect a specific behavior or we need to add a dummy node in the builder for now?
    # Or strict TDD: we expect it to fail if we don't define nodes.

    # For now, let's assume the builder should produce a VALID graph by default (maybe a pass-through).
    # OR we expose methods to add nodes.

    # Let's test that we can add a simple node and compile.

    def dummy_node(state: AgentState):
        return {"intermediate_steps": [("dummy", "result")]}

    builder.graph.add_node("test_node", dummy_node)
    builder.graph.set_entry_point("test_node")
    builder.graph.set_finish_point("test_node")

    app = builder.build()
    # Checked compiled graph by duck-typing invoke method
    assert hasattr(app, "invoke")


def test_builder_empty_build_unhappy_path():
    """Unhappy path: Building an empty graph should likely raise error or validation issue."""
    builder = WorkflowGraphBuilder()
    # LangGraph validation usually happens at compile time (GraphValueError)
    try:
        builder.build()
    except Exception as e:
        print(f"Caught expected exception: {e}")
        assert True
        return

    # If it didn't raise, we might need to check if it's actually valid
    # (newer langgraph might allow empty graphs but warn)
    # But usually it requires at least one node/edge.
    # If it didn't verify, fail
    print(f"Graph app instance: {builder}")
    # We expect graph to NOT be runnable without nodes usually.
    # But if `compile()` succeeds, it returns a CompiledGraph.
    # Let's assume for now that if compile() works, the builder is working "technically".
    # We will refine this when we add actual nodes.
    # assert isinstance(app, CompiledGraph)
    pytest.fail("Should have raised an exception for empty graph")
    pass
