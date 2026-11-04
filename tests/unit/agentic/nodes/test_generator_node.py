from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agentic.graph.experiment_state import ExperimentState

# We haven't created the node yet, so we'll import it proactively assuming the path
from src.domains.agentic.nodes.generator_node import GeneratorNode


@pytest.fixture
def mock_mutator():
    with patch("src.domains.agentic.nodes.generator_node.PromptMutator") as MockMutator:
        instance = MockMutator.return_value
        instance.mutate_prompt = AsyncMock(return_value="Mutated Prompt Content")
        yield instance


@pytest.mark.asyncio
async def test_generator_node_execution(mock_mutator):
    """
    Test that GeneratorNode uses PromptMutator to generate variants.
    """
    # Arrange
    node = GeneratorNode()
    state: ExperimentState = {
        "prompt_template": "Original Prompt",
        "instruction": "Make it shorter",
        "variants": [],
        "test_cases": [],
        "simulations": {},
        "evaluations": {},
        "best_variant": None,
        "error": None,
    }

    # Act
    # We expect the node to generate, say, 3 variants
    new_state = await node.invoke(state, num_variants=3)

    # Assert
    assert "variants" in new_state
    assert len(new_state["variants"]) == 3
    assert new_state["variants"][0] == "Mutated Prompt Content"

    # Verify mutator was called 3 times
    assert mock_mutator.mutate_prompt.call_count == 3
    # Check arguments of the first call
    mock_mutator.mutate_prompt.assert_any_call("Original Prompt", "Make it shorter")
