import pytest

from src.domains.agentic.graph.experiment_state import ExperimentState
from src.domains.agentic.nodes.evaluator_node import EvaluatorNode


@pytest.mark.asyncio
async def test_evaluator_node_execution():
    """
    Test that EvaluatorNode scores simulations and picks a winner.
    """
    # Arrange
    node = EvaluatorNode()
    state: ExperimentState = {
        "prompt_template": "Base",
        "instruction": "Opt",
        "variants": ["Long Response Variant", "Short Variant"],
        "test_cases": [{"input": "test"}],
        "simulations": {
            0: [{"output": "This is a very long response indeed."}],  # Length ~32
            1: [{"output": "Short."}],  # Length ~6
        },
        "evaluations": {},
        "best_variant": None,
        "error": None,
    }

    # Act
    # We'll use a specific scoring strategy if configurable,
    # but for default let's assume it scores based on length (just for deterministic testing)
    # OR we can mock the scoring method.
    # Let's assume the node has a simple heuristic: higher length = higher score (demo)
    # or provided scoring function.

    new_state = await node.invoke(state)

    # Assert
    assert "evaluations" in new_state
    evals = new_state["evaluations"]
    assert len(evals) == 2

    # Verify we have scores
    assert 0 in evals
    assert 1 in evals

    # Verify best_variant is set
    assert new_state["best_variant"] is not None
    # If our heuristic is length, Variant 0 should win
    assert new_state["best_variant"] == "Long Response Variant"
