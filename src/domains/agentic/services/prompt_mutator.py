import logging

# Attempt to import LLM components
_llm_imports_available = False
try:
    from src.core.llm.llm_client import LLMMessage, create_llm_client

    _llm_imports_available = True
except ImportError:
    pass

logger = logging.getLogger(__name__)


class PromptMutator:
    """
    Service to mutate and optimize prompts using an LLM.
    Acts as an automated Prompt Engineer.
    """

    async def mutate_prompt(self, original_prompt: str, instruction: str) -> str:
        """
        Generate a new version of a prompt based on instructions.

        Args:
            original_prompt: Current prompt text
            instruction: Optimization goal (e.g. "Reduce token usage", "Be more empathetic")

        Returns:
            The mutated prompt text
        """
        if not _llm_imports_available:
            raise ImportError("LLM Client not available")

        client = create_llm_client(provider_name="google")  # pyright: ignore[reportPossiblyUnboundVariable]

        # Meta-prompt for the mutation task
        system_msg = (
            "You are an expert Prompt Engineer. Your task is to rewrite the given prompt "
            "based strictly on the user's optimization instruction. "
            "Return ONLY the new prompt content. Do not include quotes or markdown blocks unless part of the prompt."
        )

        user_msg = f"""
Original Prompt:
---
{original_prompt}
---

Optimization Instruction:
{instruction}

New Prompt:
"""

        if not _llm_imports_available:
            raise ImportError("LLMMessage not available")
        messages = [
            LLMMessage(role="system", content=system_msg),  # pyright: ignore[reportPossiblyUnboundVariable]
            LLMMessage(role="user", content=user_msg),  # pyright: ignore[reportPossiblyUnboundVariable]
        ]

        logger.info(f"Mutating prompt with instruction: {instruction}")

        try:
            llm_response = await client.chat_completion(messages)
            response = llm_response.content

            # Basic cleanup
            cleaned = response.strip()
            if cleaned.startswith("```") and cleaned.endswith("```"):
                # Remove markdown code blocks if the LLM added them wrapping the prompt
                lines = cleaned.split("\n")
                if len(lines) >= 2:
                    cleaned = "\n".join(lines[1:-1])

            return cleaned.strip()

        except Exception as e:
            logger.error(f"Failed to mutate prompt: {e}")
            raise
