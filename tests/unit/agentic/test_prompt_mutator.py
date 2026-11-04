from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Will fail until implemented
from src.domains.agentic.services.prompt_mutator import PromptMutator


class TestPromptMutator:
    @pytest.fixture
    def mock_llm_client(self):
        client = AsyncMock()
        # Mock LLMResponse with content attribute
        mock_response = MagicMock()
        mock_response.content = "Optimized prompt content"
        client.chat_completion.return_value = mock_response
        return client

    @pytest.mark.asyncio
    async def test_mutate_prompt_success(self, mock_llm_client):
        """Should generate a mutated prompt using LLM."""

        mutator = PromptMutator()

        with patch(
            "src.domains.agentic.services.prompt_mutator.create_llm_client",
            return_value=mock_llm_client,
        ):
            original_prompt = "You are a helpful assistant."
            instruction = "Make it more professional."

            new_prompt = await mutator.mutate_prompt(original_prompt, instruction)

            assert new_prompt == "Optimized prompt content"
            mock_llm_client.chat_completion.assert_called_once()

            # Check prompt payload contains instructions
            call_args = mock_llm_client.chat_completion.call_args[0]
            assert instruction in str(call_args)
            assert original_prompt in str(call_args)

    @pytest.mark.asyncio
    async def test_mutate_prompt_failure(self, mock_llm_client):
        """Should raise exception if LLM fails."""

        mock_llm_client.chat_completion.side_effect = Exception("LLM Error")
        mutator = PromptMutator()

        with patch(
            "src.domains.agentic.services.prompt_mutator.create_llm_client",
            return_value=mock_llm_client,
        ):
            with pytest.raises(Exception):
                await mutator.mutate_prompt("prompt", "instruction")
