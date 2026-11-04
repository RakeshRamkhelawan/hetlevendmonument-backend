"""Symbiotic Code Agent - Code generation with ALS."""

from typing import Any

from src.core.als.agents.symbiotic_agent import SymbioticAgent
from src.core.als.infrastructure.signal_bus import Signal, SignalBus
from src.core.shared.interfaces import ExecutionResult
from src.core.types import AgentType


class SymbioticCodeAgent(SymbioticAgent):
    """Code generation agent with symbiotic capabilities."""

    def __init__(self, tenant_id: int, signal_bus: SignalBus, **kwargs: Any) -> None:
        super().__init__(
            agent_id="symbiotic_coder",
            agent_type=AgentType.CODE,
            tenant_id=tenant_id,
            signal_bus=signal_bus,
            department="engineering",
            **kwargs,
        )

        self._capabilities: list[Any] = ["code_generation", "code_review", "refactoring"]  # TODO(TYPE): replace Any with concrete type

    async def observe(self, signal: Signal) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Extract coding request."""
        return {
            "language": signal.payload.get("language", "python"),
            "task": signal.payload.get("task"),
            "context": signal.payload.get("context", ""),
        }

    async def orient(self, observation: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze requirements."""
        return {
            "language": observation["language"],
            "complexity": self._assess_complexity(observation["task"]),
            "task": observation["task"],
        }

    async def decide(self, orientation: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Choose generation strategy."""
        if orientation["complexity"] == "high":
            return "generate_with_tests"
        return "generate_simple"

    async def act(self, decision: str) -> ExecutionResult:
        """Generate code."""
        return ExecutionResult(
            task_id="code_gen",
            success=True,
            result_data={
                "code": "# Generated code\nprint('hello')",
                "tests": decision == "generate_with_tests",
                "language": "python",
            },
        )

    def _assess_complexity(self, task: str) -> str:
        """Assess task complexity."""
        if len(task) > 100:
            return "high"
        elif len(task) > 50:
            return "medium"
        return "low"
