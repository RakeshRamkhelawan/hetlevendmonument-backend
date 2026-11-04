from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agentic.graph.experiment_builder import ExperimentGraphBuilder
from src.domains.agentic.graph.experiment_state import ExperimentState


@pytest.fixture
def mock_dependencies():
    with (
        patch("src.domains.agentic.nodes.generator_node.PromptMutator") as MockMutator,
        patch("src.domains.agentic.nodes.simulator_node.create_llm_client") as mock_create_llm,
    ):
        # Generator Mock
        mutator_instance = MockMutator.return_value
        mutator_instance.mutate_prompt = AsyncMock(
            side_effect=["Variant A", "Variant B", "Variant C"]
        )

        # Simulator Mock
        mock_client = AsyncMock()
        mock_create_llm.return_value = mock_client
        mock_client.generate_response = AsyncMock(return_value="Output")

        yield mutator_instance, mock_client


@pytest.mark.asyncio
async def test_experiment_graph_execution(mock_dependencies):
    """
    Test the full lifecycle of the experiment graph.
    """
    # Arrange
    builder = ExperimentGraphBuilder()
    graph = builder.build()

    initial_state: ExperimentState = {
        "prompt_template": "Original",
        "instruction": "Optimize",
        "variants": [],
        "test_cases": [{"input": "Test 1"}],
        "simulations": {},
        "evaluations": {},
        "best_variant": None,
        "error": None,
    }

    # Act
    # Invoke returns a dict (or StateSnapshot)
    final_state = await graph.ainvoke(initial_state)

    # Assert
    # 1. Generator Node
    assert "variants" in final_state
    # invoked invoke(state, num_variants=3) default?
    # Current implementation of GeneratorNode.invoke uses default 3
    assert len(final_state["variants"]) == 3
    assert "Variant A" in final_state["variants"]

    # 2. Simulator Node
    assert "simulations" in final_state
    # Should have simulations for all 3 variants
    assert len(final_state["simulations"]) == 3

    # 3. Evaluator Node
    assert "evaluations" in final_state
    assert len(final_state["evaluations"]) == 3
    assert final_state["best_variant"] is not None

    # Logic verification (heuristic: length)
    # Since all outputs are "Output" (len 6), any could be best, or first
    assert final_state["best_variant"] in ["Variant A", "Variant B", "Variant C"]
