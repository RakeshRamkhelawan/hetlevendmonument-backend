from typing import Any

from langgraph.graph import END, StateGraph

from src.domains.agentic.graph.experiment_state import ExperimentState
from src.domains.agentic.nodes.evaluator_node import EvaluatorNode
from src.domains.agentic.nodes.generator_node import GeneratorNode
from src.domains.agentic.nodes.simulator_node import SimulatorNode


class ExperimentGraphBuilder:
    """
    Builder for the Prompt Experiment Optimization Graph.
    Flow: Generator -> Simulator -> Evaluator -> END
    """

    def __init__(self) -> None:
        self.graph = StateGraph(ExperimentState)
        self.generator = GeneratorNode()
        self.simulator = SimulatorNode()
        self.evaluator = EvaluatorNode()

    def build(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Constructs and compiles the experiment graph."""

        # Add Nodes
        self.graph.add_node("generator", self.generator.invoke)
        self.graph.add_node("simulator", self.simulator.invoke)
        self.graph.add_node("evaluator", self.evaluator.invoke)

        # Add Edges
        self.graph.set_entry_point("generator")
        self.graph.add_edge("generator", "simulator")
        self.graph.add_edge("simulator", "evaluator")
        self.graph.add_edge("evaluator", END)

        return self.graph.compile()
