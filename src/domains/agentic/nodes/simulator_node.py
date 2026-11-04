from typing import Any

from src.core.llm.llm_client import LLMMessage, create_llm_client
from src.domains.agentic.graph.experiment_state import ExperimentState


class SimulatorNode:
    """
    Node responsible for running variants against test cases.
    It takes the generated variants and executes them using the LLM.
    """

    def __init__(self) -> None:
        # In production, we might want to inject the client or use a factory
        # For now, we instantiate on invoke or init
        pass

    async def invoke(self, state: ExperimentState) -> ExperimentState:
        """
        Execute simulations.
        """
        variants = state.get("variants", [])
        test_cases = state.get("test_cases", [])

        if not variants or not test_cases:
            return state

        client = create_llm_client(provider_name="google")
        simulations: dict[int, list[dict[str, Any]]] = {}  # TODO(TYPE): replace Any with concrete type

        for idx, variant_prompt in enumerate(variants):
            variant_results: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
            for test_case in test_cases:
                # Construct messages for simulation
                # Assuming test_case has 'input'
                user_input = test_case.get("input", "")

                messages = [
                    LLMMessage(role="system", content=variant_prompt),
                    LLMMessage(role="user", content=user_input),
                ]

                try:
                    response = await client.generate_response(prompt="", messages=messages)
                    variant_results.append(
                        {"test_case": test_case, "output": response, "error": None}
                    )
                except Exception as e:
                    variant_results.append(
                        {"test_case": test_case, "output": None, "error": str(e)}
                    )

            simulations[idx] = variant_results

        return {**state, "simulations": simulations}
