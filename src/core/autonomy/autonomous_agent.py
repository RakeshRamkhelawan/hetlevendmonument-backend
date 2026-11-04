"""
AutonomousAgent Implementation - FASE 5 UPGRADE
Implements autonomous orchestration met proactive monitoring en goal generation
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.autonomy.decision_engine import (
    AgentNotFoundException,
    DecisionEngine,
    create_decision_engine,
)
from src.core.autonomy.enhanced_task_planner import (
    EnhancedTaskPlanner,
    ExecutionPlan,
    ExecutionStep,
    Goal,
    create_enhanced_task_planner,
)
from src.core.collaboration.agent_mesh import AgentRegistry, get_agent_registry
from src.core.collaboration.task_distributor import TaskDistributor, get_task_distributor
from src.core.learning.predictive_analytics_engine import PredictiveAnalyticsEngine

logger = logging.getLogger(__name__)


class AutonomousAgent:
    """
    AutonomousAgent klasse zoals gespecificeerd in FASE 3+ STAP 3+.2

    PLAN SPECIFICATIE:
    "De `_autonomy_control_loop` moet nu een doel kunnen ontvangen. Het roept `self.task_planner.create_plan_for_goal()` aan.
     Vervolgens itereert het over de stappen in het plan en gebruikt `self.task_distributor.dispatch_task()` om de taak
     naar de juiste agent te sturen."
    """

    def __init__(
        self,
        task_planner: EnhancedTaskPlanner | None = None,
        task_distributor: TaskDistributor | None = None,
        agent_registry: AgentRegistry | None = None,
        decision_engine: DecisionEngine | None = None,
        predictive_engine: PredictiveAnalyticsEngine | None = None,
    ) -> None:
        """
        Initialize AutonomousAgent met dependencies

        Args:
            task_planner: TaskPlanner voor goal-naar-plan conversie (optioneel, gebruikt factory)
            task_distributor: TaskDistributor voor task dispatch (optioneel, gebruikt factory)
            agent_registry: AgentRegistry voor agent discovery (optioneel, gebruikt factory)
            decision_engine: DecisionEngine voor dynamic agent selection (optioneel, gebruikt factory)
            predictive_engine: PredictiveAnalyticsEngine voor proactive monitoring (optioneel, creates new)
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Dependency injection met fallback naar factories
        self.task_planner = task_planner or create_enhanced_task_planner()
        self.task_distributor = task_distributor or get_task_distributor()
        self.agent_registry = agent_registry or get_agent_registry()
        self.decision_engine = decision_engine or create_decision_engine(self.agent_registry)

        # FASE 5: PredictiveAnalyticsEngine injection
        self.predictive_engine = predictive_engine or PredictiveAnalyticsEngine()

        # Agent state
        self._running = False
        self._current_goal: Goal | None = None
        self._current_plan: ExecutionPlan | None = None

        # FASE 5: Proactive monitoring state
        self._proactive_goal_queue: asyncio.Queue[Goal] = asyncio.Queue()
        self._monitoring_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type
        self._monitoring_interval_seconds = 300  # 5 minutes

        # Start proactive monitoring loop
        self._monitoring_task = asyncio.create_task(self._proactive_monitoring_loop())

        self.logger.info("AutonomousAgent initialized for FASE 5 proactive operations")

    async def execute_goal(self, goal: Goal) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Execute a goal using autonomous orchestration zoals gespecificeerd

        Implements the main workflow:
        1. Receive goal
        2. Call task_planner.create_plan_for_goal()
        3. Iterate over plan steps
        4. Use task_distributor.dispatch_task() for each step

        Args:
            goal: Goal object te executeren

        Returns:
            Dict[str, Any]: Execution result met plan details en step results  # TODO(TYPE): replace Any with concrete type
        """
        self.logger.info(f"Starting autonomous goal execution: {goal.id}")
        self.logger.debug(f"Goal description: {goal.description}")

        try:
            self._current_goal = goal

            # Start TaskDistributor if not running
            if not self.task_distributor._running:
                await self.task_distributor.start()
                self.logger.info("TaskDistributor started for autonomous operation")

            # Step 1: Create execution plan using EnhancedTaskPlanner zoals gespecificeerd
            self.logger.info("Creating execution plan using EnhancedTaskPlanner...")
            execution_plan = await self.task_planner.create_plan_for_goal(goal)
            self._current_plan = execution_plan

            self.logger.info(f"Execution plan created: {execution_plan.plan_id}")
            self.logger.info(f"Plan contains {len(execution_plan.steps)} steps")

            # Step 2: Execute all steps in the plan zoals gespecificeerd
            step_results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for i, step in enumerate(execution_plan.steps):
                self.logger.info(
                    f"Executing step {i+1}/{len(execution_plan.steps)}: {step.step_id}"
                )

                step_result = await self._execute_plan_step(step)
                step_results.append(step_result)

                if not step_result["success"]:
                    self.logger.error(f"Step {i+1} failed: {step_result['error']}")
                    # Voor nu stoppen bij eerste failure, later dependency resolution
                    break

            # Calculate overall success
            all_success = all(result["success"] for result in step_results)

            result = {
                "success": all_success,
                "goal_id": goal.id,
                "plan_id": execution_plan.plan_id,
                "steps_executed": len(step_results),
                "steps_total": len(execution_plan.steps),
                "step_results": step_results,
                "execution_time": datetime.now(timezone.utc).isoformat(),
            }

            if all_success:
                self.logger.info(f"Goal execution completed successfully: {goal.id}")
            else:
                self.logger.warning(f"Goal execution partially failed: {goal.id}")

            return result

        except Exception as e:
            self.logger.error(f"Error during goal execution: {e}")
            return {
                "success": False,
                "goal_id": goal.id if goal else "unknown",
                "error": str(e),
                "execution_time": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            self._current_goal = None
            self._current_plan = None

    async def _execute_plan_step(self, step: ExecutionStep) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Execute individual plan step using DecisionEngine en TaskDistributor zoals gespecificeerd

        FASE 4 PLAN SPECIFICATIE:
        "De `agent_id` mag niet langer hardgecodeerd uit de `step` komen. In plaats daarvan, roep
         `self.decision_engine.select_agent_for_task(step.task_message.task_type)` aan om de `agent_id`
         dynamisch te bepalen."

        Args:
            step: ExecutionStep te executeren

        Returns:
            Dict[str, Any]: Step execution result  # TODO(TYPE): replace Any with concrete type
        """
        try:
            # FASE 5: Gebruik DecisionEngine voor performance-based agent selectie
            selected_agent = await self.decision_engine.select_agent_for_task(
                step.task_message.task_type
            )
            agent_id = selected_agent.agent_id

            self.logger.info(
                f"DecisionEngine selected agent: {agent_id} for task type: {step.task_message.task_type}"
            )

            # Use TaskDistributor.dispatch_task() zoals gespecificeerd in plan
            dispatch_result = await self.task_distributor.dispatch_task(
                agent_id=agent_id,  # Dynamically selected agent_id
                task_message=step.task_message,
                timeout_seconds=step.estimated_duration_seconds or 30,
            )

            self.logger.info(f"Task dispatch result: success={dispatch_result.success}")

            return {
                "success": dispatch_result.success,
                "step_id": step.step_id,
                "agent_id": agent_id,  # Use dynamically selected agent_id
                "task_id": str(step.task_message.task_id),
                "response_data": dispatch_result.response_data,
                "error": dispatch_result.error_message if not dispatch_result.success else None,
                "status": dispatch_result.status,
            }

        except AgentNotFoundException as e:
            self.logger.error(
                f"No suitable agent found for task type {step.task_message.task_type}: {e}"
            )
            return {
                "success": False,
                "step_id": step.step_id,
                "agent_id": None,  # No agent was selected
                "task_id": str(step.task_message.task_id),
                "error": f"AgentNotFoundException: {str(e)}",
                "agent_selection_error": True,
            }

        except Exception as e:
            self.logger.error(f"Error executing step {step.step_id}: {e}")
            return {
                "success": False,
                "step_id": step.step_id,
                "agent_id": None,  # Unknown agent due to error
                "error": str(e),
            }

    async def _autonomy_control_loop(self, goal: Goal) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Autonomy control loop zoals gespecificeerd in plan

        PLAN SPECIFICATIE:
        "De `_autonomy_control_loop` moet nu een doel kunnen ontvangen. Het roept `self.task_planner.create_plan_for_goal()` aan.
         Vervolgens itereert het over de stappen in het plan en gebruikt `self.task_distributor.dispatch_task()` om de taak
         naar de juiste agent te sturen."

        Args:
            goal: Goal object voor processing

        Returns:
            Dict[str, Any]: Control loop execution result  # TODO(TYPE): replace Any with concrete type
        """
        self.logger.info("Starting autonomy control loop...")

        # Dit is de main entry point voor autonome operaties
        # Execute goal via de execute_goal methode die de complete workflow implementeert
        return await self.execute_goal(goal)

    async def _proactive_monitoring_loop(self) -> None:
        """
        FASE 5: Proactive monitoring loop
        Continuously monitors system health using PredictiveAnalyticsEngine
        Generates goals when warnings are detected
        """
        self.logger.info("Starting proactive monitoring loop")

        while True:
            try:
                # Generate system forecast using PredictiveAnalyticsEngine
                forecast = await self.predictive_engine.generate_system_forecast()

                self.logger.debug(f"Generated forecast with {len(forecast.warnings)} warnings")

                # Check if forecast contains warnings
                if forecast.has_warnings:
                    for warning in forecast.warnings:
                        # Create diagnostic goal for each warning
                        goal_description = f"diagnose: {warning.task_type}"

                        goal = Goal(
                            id=f"proactive_goal_{warning.task_type}_{int(datetime.now(timezone.utc).timestamp())}",
                            description=goal_description,
                            metadata={
                                "priority": "high",
                                "source": "proactive_monitoring",
                                "warning": {
                                    "task_type": warning.task_type,
                                    "failure_rate": warning.failure_rate,
                                    "threshold_exceeded": warning.threshold_exceeded,
                                    "sample_size": warning.sample_size,
                                    "recommendation": warning.recommendation,
                                },
                                "forecast_timestamp": forecast.timestamp.isoformat(),
                            },
                        )

                        # Add goal to proactive queue
                        await self._proactive_goal_queue.put(goal)

                        self.logger.warning(
                            f"Proactive goal generated for {warning.task_type} "
                            f"(failure rate: {warning.failure_rate:.2%}): {goal.id}"
                        )

                # Wait for next monitoring cycle
                await asyncio.sleep(self._monitoring_interval_seconds)

            except asyncio.CancelledError:
                self.logger.info("Proactive monitoring loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in proactive monitoring loop: {e}")
                # Continue monitoring despite errors
                await asyncio.sleep(self._monitoring_interval_seconds)

    async def _process_single_forecast(self) -> int:
        """
        FASE 5: Process single forecast iteration for testing
        Returns number of goals generated
        """
        goals_generated = 0

        try:
            # Generate system forecast using PredictiveAnalyticsEngine
            forecast = await self.predictive_engine.generate_system_forecast()

            self.logger.debug(f"Generated forecast with {len(forecast.warnings)} warnings")

            # Check if forecast contains warnings
            if forecast.has_warnings:
                for warning in forecast.warnings:
                    # Create diagnostic goal for each warning
                    goal_description = f"diagnose: {warning.task_type}"

                    goal = Goal(
                        id=f"proactive_goal_{warning.task_type}_{int(datetime.now(timezone.utc).timestamp())}",
                        description=goal_description,
                        metadata={
                            "priority": "high",
                            "source": "proactive_monitoring",
                            "warning": {
                                "task_type": warning.task_type,
                                "failure_rate": warning.failure_rate,
                                "threshold_exceeded": warning.threshold_exceeded,
                                "sample_size": warning.sample_size,
                                "recommendation": warning.recommendation,
                            },
                            "forecast_timestamp": forecast.timestamp.isoformat(),
                        },
                    )

                    # Add goal to proactive queue
                    await self._proactive_goal_queue.put(goal)
                    goals_generated += 1

                    self.logger.warning(
                        f"Proactive goal generated for {warning.task_type} "
                        f"(failure rate: {warning.failure_rate:.2%}): {goal.id}"
                    )

            return goals_generated

        except Exception as e:
            self.logger.error(f"Error in single forecast processing: {e}")
            return 0

    async def get_proactive_goal(self) -> Goal | None:
        """
        FASE 5: Get next proactive goal from queue

        Returns:
            Optional[Goal]: Next proactive goal or None if queue is empty
        """
        try:
            # Non-blocking get with immediate timeout
            goal = await asyncio.wait_for(self._proactive_goal_queue.get(), timeout=0.1)
            self.logger.info(f"Retrieved proactive goal: {goal.id}")
            return goal
        except TimeoutError:
            return None
        except Exception as e:
            self.logger.error(f"Error getting proactive goal: {e}")
            return None

    async def queue_proactive_goals_count(self) -> int:
        """
        FASE 5: Get count of pending proactive goals

        Returns:
            int: Number of pending proactive goals
        """
        return self._proactive_goal_queue.qsize()

    async def shutdown(self) -> None:
        """
        FASE 5: Shutdown autonomous agent and cleanup resources
        """
        self.logger.info("Shutting down AutonomousAgent")

        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        self._running = False
        self.logger.info("AutonomousAgent shutdown complete")

    def get_current_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get current autonomous agent status

        Returns:
            Dict[str, Any]: Current status information  # TODO(TYPE): replace Any with concrete type
        """
        return {
            "running": self._running,
            "current_goal": (
                {
                    "id": self._current_goal.id,
                    "description": self._current_goal.description,
                }
                if self._current_goal
                else None
            ),
            "current_plan": (
                {
                    "id": self._current_plan.plan_id,
                    "steps_count": len(self._current_plan.steps),
                }
                if self._current_plan
                else None
            ),
            "task_distributor_running": (
                self.task_distributor._running if self.task_distributor else False
            ),
            "proactive_monitoring": {
                "monitoring_active": not (self._monitoring_task and self._monitoring_task.done()),
                "pending_goals": self._proactive_goal_queue.qsize(),
                "monitoring_interval_seconds": self._monitoring_interval_seconds,
            },
        }


def create_autonomous_agent(
    task_planner: EnhancedTaskPlanner | None = None,
    task_distributor: TaskDistributor | None = None,
    agent_registry: AgentRegistry | None = None,
    decision_engine: DecisionEngine | None = None,
    predictive_engine: PredictiveAnalyticsEngine | None = None,
) -> AutonomousAgent:
    """
    Factory function voor AutonomousAgent instantie

    Args:
        task_planner: Optional EnhancedTaskPlanner dependency
        task_distributor: Optional TaskDistributor dependency
        agent_registry: Optional AgentRegistry dependency
        decision_engine: Optional DecisionEngine dependency
        predictive_engine: Optional PredictiveAnalyticsEngine dependency

    Returns:
        AutonomousAgent: Geconfigureerde AutonomousAgent instantie
    """
    return AutonomousAgent(
        task_planner=task_planner,
        task_distributor=task_distributor,
        agent_registry=agent_registry,
        decision_engine=decision_engine,
        predictive_engine=predictive_engine,
    )
