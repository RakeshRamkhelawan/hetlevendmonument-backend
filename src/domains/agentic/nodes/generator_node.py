
from src.domains.agentic.graph.experiment_state import ExperimentState
from src.domains.agentic.services.prompt_mutator import PromptMutator


class GeneratorNode:
    """
    Node responsible for generating prompt variants based on instructions.
    Uses PromptMutator to perform the actual LLM generation.
    """

    def __init__(self) -> None:
        self.mutator = PromptMutator()

    async def invoke(self, state: ExperimentState, num_variants: int = 3) -> ExperimentState:
        """
        Execute the generation step.
        Mutates the base prompt `num_variants` times.
        """
        prompt = state.get("prompt_template", "")
        instruction = state.get("instruction", "")

        if not prompt or not instruction:
            # If missing inputs, return state as is or with error
            # For now, just logging error in state might be better
            return {**state, "error": "Missing prompt_template or instruction"}

        variants: list[str] = []

        # Parallel generation could be better, but sequential for now to match interface
        for _ in range(num_variants):
            try:
                # We interpret the instruction as "Mutation instruction"
                # Ideally we might vary the instruction slightly or use temperature for diversity
                variant = await self.mutator.mutate_prompt(prompt, instruction)
                variants.append(variant)
            except Exception as e:
                # Log error but verify if we should fail hard
                # For this MVP, we'll just track what we can
                pass

        # Return state update
        return {**state, "variants": variants}
