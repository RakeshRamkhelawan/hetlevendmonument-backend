"""
OODA-K Runtime Implementation: Observe-Orient-Decide-Act control loop for agent decision-making.

This module implements the OODA (Observe-Orient-Decide-Act) control loop as the core runtime
for agent decision-making. It extends the governance pipeline from Phase A with actual
decision-making logic.

Key components:
- ObservationSnapshot: Aggregates task context, execution history, environment
- OrientationAnalysis: LLM-based situational analysis with reasoning
- DecisionContext: Decision state with confidence scoring and risk assessment
- OODALoopExecutor: Main OODA runtime that implements observe->orient->decide->act cycle
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from collections.abc import Awaitable, Callable


from src.core.shared.interfaces import ExecutionResult, TaskData

logger = logging.getLogger(__name__)


class ObservationPhase(str, Enum):
    """Phase within observation cycle."""

    INITIAL = "initial"  # First observation of task
    INTERMEDIATE = "intermediate"  # During execution
    FINAL = "final"  # After execution attempt


class OrientationMode(str, Enum):
    """Orientation strategy for situational analysis."""

    ANALYTICAL = "analytical"  # Data-driven, rule-based
    INTUITIVE = "intuitive"  # LLM-based reasoning
    HYBRID = "hybrid"  # Both combined


class ConfidenceLevel(str, Enum):
    """Confidence in decision."""

    LOW = "low"  # < 0.33
    MEDIUM = "medium"  # 0.33-0.66
    HIGH = "high"  # > 0.66


class DecisionMode(str, Enum):
    """Decision-making strategy."""

    AUTONOMOUS = "autonomous"  # Agent decides and acts immediately
    SUPERVISED = "supervised"  # Human approval required
    GRADUAL = "gradual"  # Staged execution with checkpoints
    ROLLBACK = "rollback"  # Execute but be ready to undo


@dataclass
class SensorReading:
    """Single sensor reading in observation."""

    sensor_type: str  # e.g., "task", "context", "history", "environment"
    reading_name: str  # e.g., "task_complexity", "available_tools", "retry_count"
    value: Any  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reliability: float = 1.0  # 0.0-1.0 confidence in reading


@dataclass
class ObservationSnapshot:
    """Aggregated sensor readings at a point in time."""

    agent_id: str
    task_id: str
    phase: ObservationPhase = ObservationPhase.INITIAL
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Sensor data
    readings: dict[str, SensorReading] = field(default_factory=dict)

    # Aggregated metrics
    task_complexity: float = 0.0  # 0.0-1.0
    available_tools: list[str] = field(default_factory=list)
    time_budget_remaining: timedelta = field(default_factory=lambda: timedelta(seconds=60))
    prior_failures: int = 0  # Number of attempts so far
    confidence_threshold: float = 0.7  # Minimum confidence for autonomous decisions

    def add_reading(self, sensor: SensorReading) -> None:
        """Add a sensor reading to the observation."""
        self.readings[sensor.reading_name] = sensor

    def average_reliability(self) -> float:
        """Average reliability across all sensors."""
        if not self.readings:
            return 1.0
        return sum(r.reliability for r in self.readings.values()) / len(self.readings)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dict for LLM reasoning."""
        return {
            "phase": self.phase.value,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "task_complexity": self.task_complexity,
            "available_tools": self.available_tools,
            "time_budget_remaining_seconds": self.time_budget_remaining.total_seconds(),
            "prior_failures": self.prior_failures,
            "sensor_readings": {
                name: {
                    "value": reading.value,
                    "reliability": reading.reliability,
                    "sensor_type": reading.sensor_type,
                }
                for name, reading in self.readings.items()
            },
        }


@dataclass
class OrientationAnalysis:
    """Situational analysis performed during orient phase."""

    observation_snapshot: ObservationSnapshot
    orientation_mode: OrientationMode
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Mental model of current situation
    situation_assessment: str = ""  # Natural language description
    key_constraints: list[str] = field(
        default_factory=list
    )  # e.g., ["time_limited", "high_complexity"]
    risks: list[tuple[str, float]] = field(default_factory=list)  # (risk_description, probability)
    opportunities: list[str] = field(default_factory=list)  # Available options

    # Reasoning trace (for interpretability)
    reasoning_trace: list[str] = field(default_factory=list)

    # Recommended options ranking
    options_ranking: list[dict[str, Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dict for decision-making."""
        return {
            "situation_assessment": self.situation_assessment,
            "key_constraints": self.key_constraints,
            "risks": [{"description": r[0], "probability": r[1]} for r in self.risks],
            "opportunities": self.opportunities,
            "options_ranking": self.options_ranking,
        }


@dataclass
class DecisionContext:
    """Context for decision-making."""

    orientation_analysis: OrientationAnalysis
    decision_mode: DecisionMode
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Selected action
    selected_action: str | None = None
    selected_option_index: int = -1

    # Confidence in decision
    confidence_score: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.LOW

    # Risk assessment
    estimated_risk: float = 0.0  # 0.0-1.0
    estimated_success_probability: float = 0.0  # 0.0-1.0

    # Rationale
    decision_rationale: str = ""
    alternatives_considered: list[str] = field(default_factory=list)

    # Preconditions for execution
    preconditions_met: bool = True
    preconditions_check: dict[str, bool] = field(default_factory=dict)

    def meets_confidence_threshold(self) -> bool:
        """Check if confidence meets threshold for autonomous execution."""
        threshold = self.orientation_analysis.observation_snapshot.confidence_threshold
        return self.confidence_score >= threshold


class OODALoopExecutor:
    """
    Executes the OODA (Observe-Orient-Decide-Act) control loop.

    This is the core runtime that provides adaptive decision-making for agent execution.
    It integrates with the UnifiedAgentGateway from Phase A.
    """

    def __init__(
        self,
        agent_id: str,
        llm_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        knowledge_base: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ):
        """
        Initialize OODA loop executor.

        Args:
            agent_id: ID of the agent using this executor
            llm_client: Optional LLM client for orient phase
            knowledge_base: Optional shared knowledge base (Redis-backed in Phase B5)
        """
        self.agent_id = agent_id
        self.llm_client = llm_client
        self.knowledge_base = knowledge_base or {}
        self.execution_history: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

    async def observe(
        self, task: TaskData, phase: ObservationPhase = ObservationPhase.INITIAL
    ) -> ObservationSnapshot:
        """
        Observe phase: aggregate sensors into unified snapshot.

        B1 Implementation: Collect task context, execution history, environment state.

        Args:
            task: The task to observe
            phase: Which phase of observation (initial, intermediate, final)

        Returns:
            Aggregated observation snapshot
        """
        logger.info(f"[OODA:observe] Starting observation phase for agent {self.agent_id}")

        snapshot = ObservationSnapshot(phase=phase, agent_id=self.agent_id, task_id=task.task_id)

        # Sensor 1: Task complexity (based on title+description length, metadata size, etc.)
        task_complexity = self._calculate_task_complexity(task)
        snapshot.task_complexity = task_complexity
        snapshot.add_reading(
            SensorReading(
                sensor_type="task",
                reading_name="task_complexity",
                value=task_complexity,
                reliability=0.95,
            )
        )

        # Sensor 2: Available tools (from metadata, tags, etc.)
        available_tools = self._get_available_tools(task)
        snapshot.available_tools = available_tools
        snapshot.add_reading(
            SensorReading(
                sensor_type="environment",
                reading_name="available_tools_count",
                value=len(available_tools),
                reliability=1.0,
            )
        )

        # Sensor 3: Time budget remaining
        time_remaining = self._calculate_time_remaining(task)
        snapshot.time_budget_remaining = time_remaining
        snapshot.add_reading(
            SensorReading(
                sensor_type="task",
                reading_name="time_budget_remaining_seconds",
                value=time_remaining.total_seconds(),
                reliability=1.0,
            )
        )

        # Sensor 4: Prior failures (from execution history)
        prior_failures = len([e for e in self.execution_history if e.get("failed", False)])
        snapshot.prior_failures = prior_failures
        snapshot.add_reading(
            SensorReading(
                sensor_type="history",
                reading_name="prior_failure_count",
                value=prior_failures,
                reliability=1.0,
            )
        )

        # Sensor 5: Metadata size (context complexity)
        metadata_size = len(task.metadata or {})
        snapshot.add_reading(
            SensorReading(
                sensor_type="context",
                reading_name="metadata_keys_count",
                value=metadata_size,
                reliability=1.0,
            )
        )

        logger.info(
            f"[OODA:observe] Observation complete. Phase={phase.value}, "
            f"complexity={task_complexity:.2f}, tools={len(available_tools)}, "
            f"time_remaining={time_remaining.total_seconds():.0f}s"
        )
        return snapshot

    async def orient(
        self, observation: ObservationSnapshot, mode: OrientationMode = OrientationMode.HYBRID
    ) -> OrientationAnalysis:
        """
        Orient phase: interpret observations in light of agent's mental model.

        B2 Implementation: LLM-based situational analysis with reasoning traces.

        Args:
            observation: The observation snapshot from observe phase
            mode: Orientation strategy (analytical, intuitive, or hybrid)

        Returns:
            Orientation analysis with situation assessment and options ranking
        """
        logger.info(f"[OODA:orient] Starting orientation phase. Mode={mode.value}")

        analysis = OrientationAnalysis(observation_snapshot=observation, orientation_mode=mode)

        # Build reasoning trace
        analysis.reasoning_trace.append(
            f"Observing task complexity: {observation.task_complexity:.2f}"
        )
        analysis.reasoning_trace.append(f"Available {len(observation.available_tools)} tools")
        analysis.reasoning_trace.append(
            f"Time budget: {observation.time_budget_remaining.total_seconds():.0f}s"
        )

        # Assess situation
        if observation.prior_failures >= 2:
            analysis.key_constraints.append("repeated_failures")
            analysis.key_constraints.append("needs_fresh_approach")
            analysis.reasoning_trace.append("[WARN] Detected repeated failures - need strategy change")

        if observation.time_budget_remaining.total_seconds() < 10:
            analysis.key_constraints.append("time_critical")
            analysis.reasoning_trace.append("[WARN] Time critical - must act quickly")

        if observation.task_complexity > 0.8:
            analysis.key_constraints.append("high_complexity")
            analysis.reasoning_trace.append("[WARN] High complexity task - staged approach recommended")

        # Identify risks
        if observation.prior_failures > 0:
            analysis.risks.append(("Repeated failure", 0.7))
        if observation.average_reliability() < 0.8:
            analysis.risks.append(("Unreliable sensors", 0.4))

        # Identify opportunities
        if len(observation.available_tools) > 5:
            analysis.opportunities.append("Multiple tool options available")
        if observation.time_budget_remaining.total_seconds() > 30:
            analysis.opportunities.append("Adequate time for staged execution")

        # Rank options (simplified; would be LLM-enhanced in B2 full implementation)
        analysis.options_ranking = [
            {
                "option": "direct_execution",
                "confidence": 0.8 if observation.prior_failures == 0 else 0.3,
                "risk": 0.2,
                "time_required": 5,
            },
            {"option": "staged_execution", "confidence": 0.9, "risk": 0.1, "time_required": 15},
            {"option": "fallback_simple", "confidence": 0.95, "risk": 0.05, "time_required": 3},
        ]

        # Situation assessment
        situation = f"Task complexity {observation.task_complexity:.1f}, "
        situation += f"{observation.prior_failures} prior failures, "
        situation += f"{len(observation.available_tools)} tools available"
        analysis.situation_assessment = situation

        logger.info(f"[OODA:orient] Situation: {situation}")
        logger.info(f"[OODA:orient] Constraints: {analysis.key_constraints}")

        return analysis

    async def decide(self, orientation: OrientationAnalysis) -> DecisionContext:
        """
        Decide phase: select action with confidence scoring.

        B3 Implementation: Action selection with confidence scoring and risk assessment.

        Args:
            orientation: The orientation analysis from orient phase

        Returns:
            Decision context with selected action and confidence
        """
        logger.info("[OODA:decide] Starting decision phase")

        decision = DecisionContext(
            orientation_analysis=orientation,
            decision_mode=self._determine_decision_mode(orientation),
        )

        # Select best option from ranked options
        if not orientation.options_ranking:
            logger.error("[OODA:decide] No options to choose from!")
            decision.selected_action = "fail"
            decision.confidence_score = 0.0
            decision.confidence_level = ConfidenceLevel.LOW
            return decision

        best_option = max(orientation.options_ranking, key=lambda x: x.get("confidence", 0))

        decision.selected_action = best_option.get("option", "unknown")
        decision.selected_option_index = orientation.options_ranking.index(best_option)
        decision.confidence_score = best_option.get("confidence", 0.0)
        decision.estimated_risk = best_option.get("risk", 0.0)
        decision.estimated_success_probability = 1.0 - decision.estimated_risk

        # Determine confidence level
        if decision.confidence_score < 0.33:
            decision.confidence_level = ConfidenceLevel.LOW
        elif decision.confidence_score < 0.66:
            decision.confidence_level = ConfidenceLevel.MEDIUM
        else:
            decision.confidence_level = ConfidenceLevel.HIGH

        # Build rationale
        rationale_parts = [
            f"Selected '{decision.selected_action}' option",
            f"Confidence: {decision.confidence_score:.2f} ({decision.confidence_level.value})",
            f"Estimated risk: {decision.estimated_risk:.2f}",
            f"Success probability: {decision.estimated_success_probability:.2f}",
        ]
        decision.decision_rationale = " | ".join(rationale_parts)

        # Check preconditions
        decision.preconditions_check = {
            "has_time": orientation.observation_snapshot.time_budget_remaining.total_seconds() > 0,
            "has_tools": len(orientation.observation_snapshot.available_tools) > 0,
            "confidence_sufficient": decision.confidence_score >= 0.5,
        }
        decision.preconditions_met = all(decision.preconditions_check.values())

        logger.info(
            f"[OODA:decide] Decision: {decision.selected_action}, "
            f"Confidence: {decision.confidence_score:.2f}, "
            f"Preconditions met: {decision.preconditions_met}"
        )

        return decision

    async def execute_ooda_cycle(
        self,
        task: TaskData,
        executor_callback: Callable[[DecisionContext], Awaitable[Any]] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ExecutionResult:
        """
        Execute full OODA cycle: Observe -> Orient -> Decide -> Act.

        Args:
            task: Task to execute
            executor_callback: Callback function to execute the selected action

        Returns:
            ExecutionResult with outcome
        """
        logger.info(f"[OODA:cycle] Starting full OODA cycle for task {task.task_id}")

        # B1: Observe
        observation = await self.observe(task, ObservationPhase.INITIAL)

        # B2: Orient
        orientation = await self.orient(observation, OrientationMode.HYBRID)

        # B3: Decide
        decision = await self.decide(orientation)

        # B4: Act (via executor callback)
        if executor_callback and decision.preconditions_met:
            logger.info(f"[OODA:act] Executing selected action: {decision.selected_action}")
            callback_result = await executor_callback(decision)
            # Wrap executor callback result in ExecutionResult with task_id.
            if isinstance(callback_result, dict):
                result = ExecutionResult(task_id=task.task_id, **callback_result)
            elif isinstance(callback_result, ExecutionResult):
                if callback_result.task_id is None:
                    result = callback_result.model_copy(update={"task_id": task.task_id})
                else:
                    result = callback_result
            else:
                result = ExecutionResult.model_validate(
                    {
                        "task_id": task.task_id,
                        "success": False,
                        "error": (f"Unexpected callback result type: {type(callback_result)}"),
                    }
                )
        else:
            logger.warning("[OODA:act] Preconditions not met, returning failure")
            result = ExecutionResult.model_validate(
                {
                    "task_id": task.task_id,
                    "success": False,
                    "output": None,
                    "error_message": f"Preconditions not met: {decision.preconditions_check}",
                }
            )

        # Record execution in history
        self.execution_history.append(
            {
                "task_id": task.task_id,
                "decision": decision.selected_action,
                "success": result.success,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "failed": not result.success,
            }
        )

        logger.info(
            f"[OODA:cycle] Cycle complete. Success={result.success}, "
            f"Decision={decision.selected_action}"
        )

        return result

    # Helper methods

    def _calculate_task_complexity(self, task: TaskData) -> float:
        """Calculate task complexity score (0.0-1.0)."""
        complexity = 0.0
        if task.title:
            complexity += min(0.2, len(task.title) / 100)
        if task.description:
            complexity += min(0.3, len(task.description) / 500)
        if task.metadata:
            complexity += min(0.3, len(task.metadata) / 50)
        if task.tags:
            complexity += min(0.2, len(task.tags) / 20)
        return min(1.0, complexity)

    def _get_available_tools(self, task: TaskData) -> list[str]:
        """Get list of available tools for the task."""
        # Can be extracted from metadata or knowledge base
        tools = task.metadata.get("tools", []) if task.metadata else []
        normalized_tools = [t if isinstance(t, str) else t.get("name", "unknown") for t in tools]
        return normalized_tools or ["internal_reasoning"]

    def _calculate_time_remaining(self, task: TaskData) -> timedelta:
        """Calculate time remaining in task execution budget."""
        if task.execution_deadline:
            remaining = task.execution_deadline - datetime.now(timezone.utc)
            return max(remaining, timedelta(seconds=0))
        return timedelta(seconds=60)  # Default 60s budget

    def _determine_decision_mode(self, orientation: OrientationAnalysis) -> DecisionMode:
        """Determine decision-making mode based on constraints."""
        # Time-critical situations require fast autonomous decisions
        if "time_critical" in orientation.key_constraints:
            return DecisionMode.AUTONOMOUS

        # Repeated failures require gradual staged execution
        if "repeated_failures" in orientation.key_constraints:
            return DecisionMode.GRADUAL

        # Default to autonomous
        return DecisionMode.AUTONOMOUS
