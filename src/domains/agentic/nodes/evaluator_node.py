from typing import Optional

from src.domains.agentic.graph.experiment_state import ExperimentState


class EvaluatorNode:
    """
    Node responsible for scoring simulation results.
    In a real system, this would use 'LLM-as-a-Judge'.
    For MVP, we implement a simple heuristic (e.g., Output Length)
    or just aggregate results.
    """

    async def invoke(self, state: ExperimentState) -> ExperimentState:
        """
        Score simulations and determine the winner.
        """
        simulations = state.get("simulations", {})
        if not simulations:
            return state

        evaluations: dict[int, float] = {}
        best_variant_idx = -1
        max_score = -1.0

        for idx, results in simulations.items():
            # Aggregate score for this variant
            total_score: float = 0.0
            count: int = 0

            for res in results:
                output = res.get("output", "")
                if output:
                    # HEURISTIC: Score = Length of output (Longer is better for now)
                    # In real world: specialized prompt to grade the output
                    score = len(output)
                    total_score += score
                    count += 1

            avg_score = total_score / count if count > 0 else 0.0
            evaluations[idx] = avg_score

            if avg_score > max_score:
                max_score = avg_score
                best_variant_idx = idx

        # Determine unique key for best variant
        best_variant: str | None = None
        variants = state.get("variants", [])
        if best_variant_idx >= 0 and best_variant_idx < len(variants):
            best_variant = variants[best_variant_idx]

        return {**state, "evaluations": evaluations, "best_variant": best_variant}
