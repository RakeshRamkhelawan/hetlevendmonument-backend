from typing import Any, Optional, TypedDict


class ExperimentState(TypedDict):
    """
    State for the Experiment Optimization Graph.
    Tracks the lifecycle of a prompt optimization experiment.
    """

    # Inputs
    prompt_template: str
    instruction: str  # Optimization goal
    test_cases: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type

    # Generation Phase
    variants: list[str]

    # Simulation Phase
    # Map of variant_index -> List[SimulationResult]
    simulations: dict[int, list[dict[str, Any]]]  # TODO(TYPE): replace Any with concrete type

    # Evaluation Phase
    # Map of variant_index -> aggregated_score
    evaluations: dict[int, float]

    # Output
    best_variant: str | None
    error: str | None
