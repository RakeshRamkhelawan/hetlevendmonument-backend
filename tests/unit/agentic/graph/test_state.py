from typing import get_type_hints

import pytest
from langchain_core.messages import BaseMessage

from src.domains.agentic.graph.state import AgentState


def test_agent_state_schema():
    """Verify AgentState has the required keys and types for LangGraph."""
    hints = get_type_hints(AgentState)

    assert "input" in hints, "AgentState must have 'input' key"
    assert "chat_history" in hints, "AgentState must have 'chat_history' key"
    assert "intermediate_steps" in hints, "AgentState must have 'intermediate_steps' key"

    assert hints["input"] is str
    # Note: Checking List[BaseMessage] exactly can be tricky due to generics,
    # but basic existence and type safety is what we care about here.


def test_agent_state_instantiation():
    """Verify we can instantiate a mock state."""
    state: AgentState = {
        "input": "test input",
        "chat_history": [],
        "intermediate_steps": [],
    }
    assert state["input"] == "test input"


def test_agent_state_missing_keys():
    """Verify standard dict behavior: accessing missing keys raises KeyError."""
    state: AgentState = {
        "input": "test",
        # missing other keys
    }

    # Just to confirm it behaves like a dict at runtime
    with pytest.raises(KeyError):
        _ = state["chat_history"]


def test_agent_state_reducer_annotation():
    """Verify that 'intermediate_steps' is Annotated with operator.add (Unhappy path prevention).

    If this reducer is missing, LangGraph will overwrite the list instead of appending to it,
    which is a critical 'unhappy path' for the agent's memory.
    """
    hints = get_type_hints(AgentState, include_extras=True)
    steps_type = hints["intermediate_steps"]

    # Check if it is an Annotated type
    assert hasattr(steps_type, "__metadata__"), "intermediate_steps must be Annotated"

    # Verify the reducer function is operator.add
    # Metadata is usually a tuple, likely (operator.add,)
    import operator

    assert (
        operator.add in steps_type.__metadata__
    ), "intermediate_steps must use operator.add reducer"
