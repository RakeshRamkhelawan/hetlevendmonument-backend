"""
Enhanced TaskPlanner Implementation - FASE 11+ DYNAMIC ARCHITECTURE
Implements dynamic goal parsing, agent selection, and action mapping
ASCII-only compliance enforced
"""

import asyncio
import concurrent.futures
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.core.collaboration.message_protocol import TaskAssignmentMessage

from .action_mapper import ActionMapper, create_action_mapper
from .agent_selector import AgentSelector, create_agent_selector
from .goal_parsers import GoalIntent, GoalParserRegistry, get_goal_parser_registry

logger = logging.getLogger(__name__)


class Goal(BaseModel):
    """
    Goal model voor autonome agent doelen
    Enhanced with additional metadata support
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str = Field(description="Goal description text")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] | None = Field(default=None)  # TODO(TYPE): replace Any with concrete type


class ExecutionStep(BaseModel):
    """
    Individual step in an execution plan
    Enhanced with capability tracking
    """

    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = Field(description="Target agent for this step")
    task_message: TaskAssignmentMessage = Field(description="Task assignment message for agent")
    dependencies: list[str] = Field(
        default_factory=list, description="Step IDs this step depends on"
    )
    estimated_duration_seconds: int | None = Field(default=None)
    required_capabilities: list[str] = Field(
        default_factory=list, description="Required agent capabilities"
    )
    priority: int = Field(default=5, description="Step priority (1-10)")


class ExecutionPlan(BaseModel):
    """
    Complete execution plan for a goal
    Enhanced with dynamic routing information
    """

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal_id: str = Field(description="ID of the goal this plan addresses")
    steps: list[ExecutionStep] = Field(description="Ordered list of execution steps")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    estimated_total_duration_seconds: int | None = Field(default=None)
    plan_type: str = Field(default="dynamic", description="Type of plan (legacy/dynamic)")
    goal_type: str | None = Field(default=None, description="Detected goal type")


class EnhancedTaskPlanner:
    """
    Enhanced TaskPlanner with dynamic goal parsing and agent selection
    Supports multiple goal types through plugin-based architecture

    NEW ARCHITECTURE:
    - Dynamic goal parsing via GoalParserRegistry
    - Capability-based agent selection via AgentSelector
    - Intelligent action mapping via ActionMapper
    - Maintains backward compatibility with legacy "archive:" goals
    """

    def __init__(
        self,
        goal_parser_registry: GoalParserRegistry | None = None,
        agent_selector: AgentSelector | None = None,
        action_mapper: ActionMapper | None = None,
    ) -> None:
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Initialize core services
        self.goal_parser_registry = goal_parser_registry or get_goal_parser_registry()
        self.agent_selector = agent_selector or create_agent_selector()
        self.action_mapper = action_mapper or create_action_mapper()

        # Planning statistics
        self._planning_stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "total_plans": 0,
            "successful_plans": 0,
            "failed_plans": 0,
            "goal_type_distribution": {},
            "agent_usage": {},
            "last_plan_time": None,
        }

        self.logger.info("Enhanced TaskPlanner initialized with dynamic architecture")

    async def create_plan_for_goal(self, goal: Goal) -> ExecutionPlan:
        """
        Create execution plan using dynamic goal parsing and agent selection

        ENHANCED WORKFLOW:
        1. Parse goal using dynamic goal parser registry
        2. Select appropriate agent based on capabilities
        3. Map goal intent to specific agent action
        4. Create execution plan with intelligent routing

        Args:
            goal: Goal object with description to parse

        Returns:
            ExecutionPlan: Dynamically generated execution plan

        Raises:
            ValueError: If goal cannot be parsed or no suitable agent found
        """
        try:
            self._planning_stats["total_plans"] += 1
            self._planning_stats["last_plan_time"] = datetime.now(timezone.utc)

            self.logger.info(f"Creating enhanced execution plan for goal: {goal.id}")
            self.logger.debug(f"Goal description: {goal.description}")

            # Step 1: Parse goal using dynamic parser registry
            goal_intent = self._parse_goal_dynamically(goal)
            if not goal_intent:
                # Fallback to legacy parsing for backward compatibility
                return self._create_legacy_plan(goal)

            # Step 2: Select appropriate agent based on capabilities
            selected_agent = await self.agent_selector.find_best_agent(goal_intent)
            if not selected_agent:
                raise ValueError(f"No suitable agent found for goal type: {goal_intent.goal_type}")

            # Step 3: Map goal intent to agent action
            action_mapping = self.action_mapper.map_goal_to_action(goal_intent)
            if not action_mapping:
                raise ValueError(f"Could not map goal to agent action: {goal_intent.goal_type}")

            # Step 4: Create execution plan
            execution_plan = self._create_dynamic_plan(
                goal, goal_intent, selected_agent, action_mapping
            )

            # Update statistics
            self._planning_stats["successful_plans"] += 1
            self._update_goal_type_stats(goal_intent.goal_type)
            self._update_agent_usage_stats(selected_agent.agent_id)

            self.logger.info(f"Enhanced plan created: {execution_plan.plan_id}")
            return execution_plan

        except Exception as e:
            self._planning_stats["failed_plans"] += 1
            self.logger.error(f"Enhanced planning failed: {e}")
            raise

    def _parse_goal_dynamically(self, goal: Goal) -> GoalIntent | None:
        """
        Parse goal using dynamic goal parser registry

        Args:
            goal: Goal to parse

        Returns:
            Parsed GoalIntent or None if parsing fails
        """
        try:
            goal_intent = self.goal_parser_registry.parse_goal(goal.description)
            if goal_intent:
                self.logger.info(f"Goal parsed as type: {goal_intent.goal_type}")
                self.logger.debug(f"Required capabilities: {goal_intent.required_capabilities}")
            return goal_intent

        except Exception as e:
            self.logger.warning(f"Dynamic goal parsing failed: {e}")
            return None

    def _create_dynamic_plan(
        self, goal: Goal, goal_intent: GoalIntent, selected_agent: Any, action_mapping: Any  # TODO(TYPE): replace Any with concrete type
    ) -> ExecutionPlan:
        """
        Create execution plan using dynamic components

        Args:
            goal: Original goal object
            goal_intent: Parsed goal intent
            selected_agent: Selected agent for execution
            action_mapping: Action mapping for agent

        Returns:
            ExecutionPlan with dynamic routing
        """
        # Create task assignment message with dynamic parameters
        task_message = TaskAssignmentMessage.create_task_assignment(
            sender_id="enhanced_task_planner",
            recipient_id=action_mapping.agent_id,
            task_name=f"{goal_intent.goal_type}_{goal.id[:8]}",
            task_type=goal_intent.goal_type,
            task_parameters=action_mapping.parameters,
        )

        # Create execution step with enhanced metadata
        execution_step = ExecutionStep(
            agent_id=action_mapping.agent_id,
            task_message=task_message,
            dependencies=[],
            estimated_duration_seconds=action_mapping.timeout_seconds,
            required_capabilities=goal_intent.required_capabilities,
            priority=action_mapping.priority,
        )

        # Create execution plan with enhanced tracking
        execution_plan = ExecutionPlan(
            goal_id=goal.id,
            steps=[execution_step],
            estimated_total_duration_seconds=action_mapping.timeout_seconds,
            plan_type="dynamic",
            goal_type=goal_intent.goal_type,
        )

        self.logger.info(
            f"Dynamic plan created: agent={action_mapping.agent_id}, action={action_mapping.action}"
        )
        return execution_plan

    def _create_legacy_plan(self, goal: Goal) -> ExecutionPlan:
        """
        Create plan using legacy logic for backward compatibility
        Handles original "archive:" goal format

        Args:
            goal: Goal with legacy format

        Returns:
            ExecutionPlan using legacy logic
        """
        self.logger.info("Using legacy planning for backward compatibility")

        # Check for legacy "archive:" prefix
        if goal.description.strip().lower().startswith("archive:"):
            return self._create_legacy_archive_plan(goal)

        # No legacy support for this goal type
        raise ValueError(f"Unsupported goal type (legacy): {goal.description}")

    def _create_legacy_archive_plan(self, goal: Goal) -> ExecutionPlan:
        """
        Create legacy execution plan for "archive:" goals (backward compatibility)

        LEGACY SPECIFICATION:
        "Als het begint met "archive:", moet het een `ExecutionPlan` retourneren dat een
         `TaskAssignmentMessage` bevat voor de `knowledge_agent` met de actie `create_knowledge`."

        Args:
            goal: Goal with "archive:" prefix

        Returns:
            ExecutionPlan: Legacy plan with knowledge_agent task
        """
        # Extract content from "archive: CONTENT" format
        content = goal.description[8:].strip()  # Remove "archive:" prefix

        if not content:
            raise ValueError("Archive goal must contain content after 'archive:' prefix")

        self.logger.info(f"Creating legacy archive plan for content: {content[:50]}...")

        # Create TaskAssignmentMessage voor knowledge_agent zoals gespecificeerd
        task_message = TaskAssignmentMessage.create_task_assignment(
            sender_id="enhanced_task_planner",
            recipient_id="knowledge_agent",
            task_name=f"legacy_archive_goal_{goal.id[:8]}",
            task_type="knowledge_management",
            task_parameters={
                "action": "create_knowledge",  # Zoals gespecificeerd in plan
                "content": content,
                "type": "archived_goal",
                "metadata": {
                    "source": "legacy_task_planner",
                    "goal_id": goal.id,
                    "archived_at": datetime.now(timezone.utc).isoformat(),
                    "original_description": goal.description,
                },
                "confidence_score": 0.9,  # High confidence for user-provided goals
            },
        )

        # Create execution step
        archive_step = ExecutionStep(
            agent_id="knowledge_agent",
            task_message=task_message,
            dependencies=[],  # No dependencies for simple archive
            estimated_duration_seconds=10,
            required_capabilities=["knowledge_management"],
            priority=5,
        )

        # Create complete execution plan
        execution_plan = ExecutionPlan(
            goal_id=goal.id,
            steps=[archive_step],
            estimated_total_duration_seconds=10,
            plan_type="legacy",
            goal_type="archive_goal",
        )

        self.logger.info(f"Legacy archive plan created: {execution_plan.plan_id}")
        self.logger.debug(f"Plan contains {len(execution_plan.steps)} steps")

        return execution_plan

    def _update_goal_type_stats(self, goal_type: str) -> None:
        """Update goal type distribution statistics"""
        if goal_type not in self._planning_stats["goal_type_distribution"]:
            self._planning_stats["goal_type_distribution"][goal_type] = 0
        self._planning_stats["goal_type_distribution"][goal_type] += 1

    def _update_agent_usage_stats(self, agent_id: str) -> None:
        """Update agent usage statistics"""
        if agent_id not in self._planning_stats["agent_usage"]:
            self._planning_stats["agent_usage"][agent_id] = 0
        self._planning_stats["agent_usage"][agent_id] += 1

    def get_planning_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get task planning statistics

        Returns: Dict[str, Any]ionary with planning statistics  # TODO(TYPE): replace Any with concrete type
        """
        stats = self._planning_stats.copy()

        # Calculate success rate
        total = stats["total_plans"]
        successful = stats["successful_plans"]
        stats["success_rate"] = (successful / total * 100) if total > 0 else 0.0

        return stats

    async def health_check(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Perform health check on enhanced task planner

        Returns:
            Health check results
        """
        try:
            # Check component health
            goal_parser_health = await self.goal_parser_registry.health_check()  # type: ignore[attr-defined]
            agent_selector_health = await self.agent_selector.health_check()
            action_mapper_health = await self.action_mapper.health_check()

            health_info = {
                "service": "enhanced_task_planner",
                "status": "healthy",
                "components": {
                    "goal_parser_registry": goal_parser_health["status"],
                    "agent_selector": agent_selector_health["status"],
                    "action_mapper": action_mapper_health["status"],
                },
                "planning_stats": self.get_planning_stats(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Check if any component is unhealthy
            component_statuses = [
                goal_parser_health["status"],
                agent_selector_health["status"],
                action_mapper_health["status"],
            ]
            if "error" in component_statuses:
                health_info["status"] = "error"
                health_info["error"] = "One or more components are unhealthy"
            elif "warning" in component_statuses:
                health_info["status"] = "warning"
                health_info["warning"] = "One or more components have warnings"

            return health_info

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "service": "task_planner",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }


# Legacy TaskPlanner class for backward compatibility
class TaskPlanner(EnhancedTaskPlanner):
    """
    Legacy TaskPlanner wrapper for backward compatibility
    Delegates to EnhancedTaskPlanner with async-to-sync adaptation
    """

    def __init__(self) -> None:
        super().__init__()
        self.logger.warning(
            "Using legacy TaskPlanner wrapper - consider upgrading to EnhancedTaskPlanner"
        )

    def create_plan_for_goal(self, goal: Goal) -> ExecutionPlan:  # type: ignore[override]
        """
        Legacy synchronous interface - wrapper for async method

        Args:
            goal: Goal object to plan

        Returns:
            ExecutionPlan: Generated execution plan
        """
        # Check if we're already in an async context
        try:
            asyncio.get_running_loop()

            # We're in an async context, but this is a sync method
            # Create a new event loop in a thread
            def run_async() -> "ExecutionPlan":
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        super(TaskPlanner, self).create_plan_for_goal(goal)
                    )
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async)
                return future.result()

        except RuntimeError:
            # No running event loop, safe to use asyncio.run
            return asyncio.run(super().create_plan_for_goal(goal))


def create_task_planner() -> TaskPlanner:
    """
    Factory function for legacy TaskPlanner instance

    Returns:
        TaskPlanner: Legacy compatible TaskPlanner instance
    """
    return TaskPlanner()


def create_enhanced_task_planner(
    goal_parser_registry: GoalParserRegistry | None = None,
    agent_selector: AgentSelector | None = None,
    action_mapper: ActionMapper | None = None,
) -> EnhancedTaskPlanner:
    """
    Factory function for EnhancedTaskPlanner instance

    Args:
        goal_parser_registry: Optional goal parser registry
        agent_selector: Optional agent selector
        action_mapper: Optional action mapper

    Returns:
        EnhancedTaskPlanner: Configured enhanced task planner
    """
    return EnhancedTaskPlanner(goal_parser_registry, agent_selector, action_mapper)


__all__ = [
    "Goal",
    "ExecutionStep",
    "ExecutionPlan",
    "TaskPlanner",
    "EnhancedTaskPlanner",
    "create_task_planner",
    "create_enhanced_task_planner",
]
