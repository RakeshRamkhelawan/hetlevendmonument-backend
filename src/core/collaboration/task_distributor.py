"""
Task Distributor - FASE 9 Unified Implementation
Converted from HTTP-based inter-container communication to internal function calls
Compliant with Single Server Policy - No more HTTP agent calls
"""

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.agents.diagnostics_agent import TaskExecutionRequest as DiagnosticsRequest
from src.core.agents.diagnostics_agent import execute_diagnostics_task

# Import agent routers for direct function calls - NO MORE HTTP
from src.core.agents.knowledge_agent import TaskExecutionRequest as KnowledgeRequest
from src.core.agents.knowledge_agent import execute_knowledge_task
from src.core.agents.sentiment_agent import TaskExecutionRequest as SentimentRequest
from src.core.agents.sentiment_agent import execute_sentiment_task
from src.core.agents.translation_agent import TaskExecutionRequest as TranslationRequest
from src.core.agents.translation_agent import execute_translation_task

from .agent_mesh import AgentRegistry, get_agent_registry
from .message_protocol import TaskAssignmentMessage, serialize_message

# Import AdaptiveLearningEngine for automatic data collection
try:
    from src.core.ai.adaptive_learning_engine import (
        AdaptiveLearningEngine,
        get_adaptive_learning_engine,
    )
except ImportError:
    AdaptiveLearningEngine = None  # type: ignore[misc, assignment]  # class used as sentinel
    get_adaptive_learning_engine = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# TypeVar for optional AdaptiveLearningEngine to handle import failure gracefully
_AdaptiveLearningEngineType = TypeVar("_AdaptiveLearningEngineType")


class TaskDistributionStatus(str, Enum):
    """Task distribution status states"""

    PENDING = "pending"
    DISPATCHED = "dispatched"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TaskDeliveryResult(BaseModel):
    """Result of task delivery attempt"""

    model_config = ConfigDict(use_enum_values=True)

    success: bool = Field(description="Whether delivery was successful")
    status: TaskDistributionStatus = Field(description="Delivery status")
    response_data: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        default=None, description="Response from agent"
    )  # TODO(TYPE): replace Any with concrete type
    error_message: str | None = Field(default=None, description="Error details if failed")
    delivery_time: datetime | None = Field(default=None, description="When task was delivered")
    response_time: datetime | None = Field(default=None, description="When response was received")
    duration_ms: float | None = Field(
        default=None, description="Total delivery duration in milliseconds"
    )


class PendingTask(BaseModel):
    """Tracking for pending tasks"""

    model_config = ConfigDict(use_enum_values=True)

    task_id: UUID = Field(description="Task identifier")
    agent_id: str = Field(description="Target agent ID")
    task_message: TaskAssignmentMessage = Field(description="Original task message")
    status: TaskDistributionStatus = Field(default=TaskDistributionStatus.PENDING)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Task creation time"
    )
    dispatched_at: datetime | None = Field(default=None, description="Task dispatch time")
    completed_at: datetime | None = Field(default=None, description="Task completion time")
    retry_count: int = Field(default=0, description="Number of retry attempts")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    timeout_seconds: int = Field(default=30, description="Task timeout in seconds")
    result: TaskDeliveryResult | None = Field(default=None, description="Delivery result")


class TaskDistributor:
    """
    Task Distributor - FASE 9 Unified Implementation
    Converted from HTTP calls to direct internal function calls
    NO MORE HTTP CLIENT - Pure internal routing
    """

    def __init__(
        self,
        agent_registry: AgentRegistry | None = None,
        learning_engine: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.agent_registry = agent_registry or get_agent_registry()
        self.learning_engine = learning_engine  # Will be initialized in start()
        self.pending_tasks: dict[UUID, PendingTask] = {}
        self.default_timeout = 30.0  # seconds
        self.retry_delays = [1, 2, 5]  # seconds between retries
        self._running = False

        logger.info("TaskDistributor initialized with INTERNAL ROUTING (no HTTP)")

    async def start(self) -> None:
        """Start the task distributor service"""
        if self._running:
            logger.warning("TaskDistributor already running")
            return

        self._running = True

        # Initialize learning engine if not provided and available
        logger.debug(
            f"Learning engine initialization check: learning_engine={self.learning_engine}, get_adaptive_learning_engine={get_adaptive_learning_engine}"
        )
        if self.learning_engine is None and get_adaptive_learning_engine is not None:
            try:
                logger.info("Attempting to initialize AdaptiveLearningEngine...")
                self.learning_engine = await get_adaptive_learning_engine()
                logger.info(
                    f"AdaptiveLearningEngine initialized successfully: {type(self.learning_engine)}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to initialize AdaptiveLearningEngine: {type(e).__name__}: {e}"
                )
                import traceback

                logger.error(f"AdaptiveLearningEngine init traceback: {traceback.format_exc()}")
        else:
            if self.learning_engine is not None:
                logger.info(f"Learning engine already initialized: {type(self.learning_engine)}")
            if get_adaptive_learning_engine is None:
                logger.warning("get_adaptive_learning_engine is None - import failed")

        # NO HTTP CLIENT INITIALIZATION - Pure internal routing
        logger.info("TaskDistributor service started - INTERNAL ROUTING MODE")

    async def stop(self) -> None:
        """Stop the task distributor service"""
        self._running = False

        # NO HTTP CLIENT TO CLOSE - Internal routing only

        # Cancel any pending tasks
        for task in self.pending_tasks.values():
            if task.status in [
                TaskDistributionStatus.PENDING,
                TaskDistributionStatus.DISPATCHED,
            ]:
                task.status = TaskDistributionStatus.FAILED
                task.completed_at = datetime.now(timezone.utc)

        logger.info("TaskDistributor service stopped")

    async def dispatch_task(
        self,
        agent_id: str,
        task_message: TaskAssignmentMessage,
        timeout_seconds: int | None = None,
    ) -> TaskDeliveryResult:
        """
        Dispatch task to agent via INTERNAL FUNCTION CALLS
        NO MORE HTTP - Direct agent function invocation
        """
        start_time = datetime.now(timezone.utc)

        try:
            # Validate agent exists and is available
            agent = self.agent_registry.get_agent(agent_id)
            if not agent:
                return TaskDeliveryResult(
                    success=False,
                    status=TaskDistributionStatus.FAILED,
                    error_message=f"Agent {agent_id} not found in registry",
                    delivery_time=start_time,
                )

            if not agent.is_available():
                return TaskDeliveryResult(
                    success=False,
                    status=TaskDistributionStatus.FAILED,
                    error_message=f"Agent {agent_id} is not available (status: {agent.status}, load: {agent.current_load}%)",
                    delivery_time=start_time,
                )

            # Create pending task tracking
            pending_task = PendingTask(
                task_id=task_message.task_id,
                agent_id=agent_id,
                task_message=task_message,
                timeout_seconds=int(timeout_seconds or self.default_timeout),
            )

            self.pending_tasks[task_message.task_id] = pending_task

            # Attempt delivery via INTERNAL FUNCTION CALL
            result = await self._deliver_task_internal(pending_task)

            # Update pending task
            pending_task.result = result
            pending_task.status = result.status
            pending_task.completed_at = datetime.now(timezone.utc)

            # FASE 6: Record learning experience for automatic feedback loop
            await self._record_learning_experience(pending_task, result)

            return result

        except Exception as e:
            logger.error(f"Failed to dispatch task to agent {agent_id}: {e}")
            return TaskDeliveryResult(
                success=False,
                status=TaskDistributionStatus.FAILED,
                error_message=f"Dispatch error: {str(e)}",
                delivery_time=start_time,
            )

    async def _deliver_task_internal(self, pending_task: PendingTask) -> TaskDeliveryResult:
        """
        FASE 9: Deliver task via INTERNAL FUNCTION CALLS
        NO MORE HTTP - Direct router function invocation
        """
        delivery_time = datetime.now(timezone.utc)
        pending_task.dispatched_at = delivery_time
        pending_task.status = TaskDistributionStatus.DISPATCHED

        try:
            # Get task parameters from message
            task_params = pending_task.task_message.task_parameters or {}

            response: Any = None
            # Create task execution request based on agent type
            if pending_task.agent_id == "knowledge_agent":
                knowledge_request = KnowledgeRequest(
                    task_message=serialize_message(pending_task.task_message)
                )
                # DIRECT FUNCTION CALL - NO HTTP
                response = await execute_knowledge_task(knowledge_request)

            elif pending_task.agent_id == "sentiment_agent":
                sentiment_request = SentimentRequest(
                    task_id=str(pending_task.task_id),
                    description=pending_task.task_message.task_name,
                    parameters=task_params,
                )
                # DIRECT FUNCTION CALL - NO HTTP
                response = await execute_sentiment_task(sentiment_request)

            elif pending_task.agent_id == "diagnostics_agent":
                diagnostics_request = DiagnosticsRequest(
                    task_id=str(pending_task.task_id),
                    description=pending_task.task_message.task_name,
                    parameters=task_params,
                )
                # DIRECT FUNCTION CALL - NO HTTP
                response = await execute_diagnostics_task(diagnostics_request)

            elif pending_task.agent_id == "translation_agent":
                translation_request = TranslationRequest(
                    task_id=str(pending_task.task_id),
                    description=pending_task.task_message.task_name,
                    parameters=task_params,
                )
                # DIRECT FUNCTION CALL - NO HTTP
                response = await execute_translation_task(translation_request)

            else:
                raise ValueError(f"Unknown agent type: {pending_task.agent_id}")

            response_time = datetime.now(timezone.utc)
            duration_ms = (response_time - delivery_time).total_seconds() * 1000

            # Convert response to dict for compatibility
            if hasattr(response, "dict"):
                response_data = dict(response.dict())
            elif hasattr(response, "__dict__"):
                response_data = dict(response.__dict__)
            else:
                response_data = {"response": str(response)}

            logger.info(
                f"Task {pending_task.task_id} successfully delivered to {pending_task.agent_id} via INTERNAL CALL"
            )

            return TaskDeliveryResult(
                success=True,
                status=TaskDistributionStatus.COMPLETED,
                response_data=response_data,
                delivery_time=delivery_time,
                response_time=response_time,
                duration_ms=duration_ms,
            )

        except Exception as e:
            error_msg = f"Internal delivery error: {str(e)}"
            logger.error(f"Task delivery failed: {error_msg}")

            return TaskDeliveryResult(
                success=False,
                status=TaskDistributionStatus.FAILED,
                error_message=error_msg,
                delivery_time=delivery_time,
            )

    async def get_task_status(self, task_id: UUID) -> PendingTask | None:
        """Get status of a pending task"""
        return self.pending_tasks.get(task_id)

    async def cancel_task(self, task_id: UUID) -> bool:
        """Cancel a pending task"""
        if task_id in self.pending_tasks:
            task = self.pending_tasks[task_id]
            if task.status in [
                TaskDistributionStatus.PENDING,
                TaskDistributionStatus.DISPATCHED,
            ]:
                task.status = TaskDistributionStatus.FAILED
                task.completed_at = datetime.now(timezone.utc)
                logger.info(f"Task {task_id} cancelled")
                return True
        return False

    async def _record_learning_experience(
        self, pending_task: PendingTask, result: TaskDeliveryResult
    ) -> None:
        """
        FASE 6: Record learning experience for automatic feedback loop
        Called after every task dispatch to collect learning data
        FASE 10: Enhanced logging for debugging and reliability
        """
        # Initialize variables to avoid possibly unbound errors
        task_type: str = "unknown"
        success: bool = False
        duration: float = 0.0

        # FASE 10: Enhanced logging - Method entry
        logger.info(f"LEARNING_EXPERIENCE: Starting recording for task {pending_task.task_id}")
        logger.debug(
            f"LEARNING_EXPERIENCE: Task details - agent_id={pending_task.agent_id}, "
            f"task_type={getattr(pending_task.task_message, 'task_type', 'unknown')}, "
            f"success={result.success}, status={result.status}"
        )

        # FASE 10: Enhanced logging - Learning engine state check
        if self.learning_engine is None:
            logger.warning(
                f"LEARNING_EXPERIENCE: Learning engine is None for task {pending_task.task_id} - "
                "no learning experience will be recorded. Check TaskDistributor.start() initialization."
            )
            return

        # FASE 10: Enhanced logging - Learning engine availability
        learning_engine_initialized = getattr(self.learning_engine, "_initialized", False)
        logger.info(
            f"LEARNING_EXPERIENCE: Learning engine available, type={type(self.learning_engine)}, "
            f"initialized={learning_engine_initialized}"
        )

        # FASE 10: Initialization validation - Check if learning engine is properly initialized
        if not learning_engine_initialized:
            logger.warning(
                f"LEARNING_EXPERIENCE: Learning engine not initialized for task {pending_task.task_id} - "
                "no learning experience will be recorded. Check AdaptiveLearningEngine.initialize() call."
            )
            return

        logger.info(
            "LEARNING_EXPERIENCE: Learning engine initialization validated - proceeding with recording"
        )

        try:
            # Determine task success based on result
            success = result.success and result.status == TaskDistributionStatus.COMPLETED

            # Calculate duration in seconds
            if result.duration_ms:
                duration = result.duration_ms / 1000.0

            # Extract task type from task message
            if hasattr(pending_task.task_message, "task_type"):
                task_type = pending_task.task_message.task_type
            elif hasattr(pending_task.task_message, "task_name"):
                # Try to infer task type from task_name
                description = pending_task.task_message.task_name.lower()
                if "archive" in description or "knowledge" in description:
                    task_type = "knowledge_archive"
                elif "sentiment" in description or "emotion" in description:
                    task_type = "sentiment_analysis"
                elif "diagnos" in description or "health" in description:
                    task_type = "diagnostic"
                else:
                    task_type = "general"

            # Prepare context information
            context = {
                "task_id": str(pending_task.task_id),
                "retry_count": pending_task.retry_count,
                "timeout_seconds": pending_task.timeout_seconds,
                "delivery_status": (
                    result.status.value
                    if hasattr(result.status, "value")
                    else str(result.status)
                    if result.status
                    else "unknown"
                ),
                "delivery_method": "internal_function_call",  # NEW: Track internal vs HTTP
            }

            # Prepare metrics
            metrics = {
                "response_time": duration,
                "internal_call": True,  # NEW: Mark as internal call
                "retry_count": pending_task.retry_count,
            }

            if result.duration_ms:
                metrics["duration_ms"] = result.duration_ms

            # FASE 10: Enhanced logging - About to record experience
            logger.info(
                f"LEARNING_EXPERIENCE: Recording experience - agent_id={pending_task.agent_id}, "
                f"task_type={task_type}, success={success}, duration={duration:.2f}s"
            )
            logger.debug(f"LEARNING_EXPERIENCE: Context data - {context}")
            logger.debug(f"LEARNING_EXPERIENCE: Metrics data - {metrics}")

            # Record the experience
            await self.learning_engine.record_experience(
                agent_id=pending_task.agent_id,
                task_type=task_type,
                success=success,
                duration=duration,
                context=context,
                metrics=metrics,
            )

            # FASE 10: Enhanced logging - Successful recording
            logger.info(
                f"LEARNING_EXPERIENCE: Successfully recorded learning experience for task {pending_task.task_id}"
            )

        except Exception as e:
            # FASE 10: Robust error handling - Comprehensive exception management
            import traceback

            # FASE 10: Enhanced logging - Detailed exception information
            logger.error(
                f"LEARNING_EXPERIENCE: Failed to record learning experience for task {pending_task.task_id}"
            )
            logger.error(f"LEARNING_EXPERIENCE: Exception type: {type(e).__name__}")
            logger.error(f"LEARNING_EXPERIENCE: Exception message: {str(e)}")
            logger.error(f"LEARNING_EXPERIENCE: Full traceback:\n{traceback.format_exc()}")

            # FASE 10: Error context logging
            logger.error("LEARNING_EXPERIENCE: Error context:")
            logger.error(f"  - Learning engine type: {type(self.learning_engine)}")
            logger.error(
                f"  - Learning engine initialized: {getattr(self.learning_engine, '_initialized', 'unknown')}"
            )
            logger.error(f"  - Task agent_id: {pending_task.agent_id}")
            logger.error(f"  - Task type: {task_type}")
            logger.error(f"  - Task success: {success}")
            logger.error(f"  - Task duration: {duration:.2f}s")
            logger.error(f"  - Result status: {result.status}")

            # FASE 10: Specific error handling for common failure types
            if "database" in str(e).lower() or "connection" in str(e).lower():
                logger.error("LEARNING_EXPERIENCE: Database connectivity issue detected")
                logger.error(
                    "LEARNING_EXPERIENCE: Recommend checking database connection and session state"
                )
            elif "attributeerror" in type(e).__name__.lower():
                logger.error(
                    "LEARNING_EXPERIENCE: Attribute error suggests missing method or property"
                )
                logger.error(
                    "LEARNING_EXPERIENCE: Check AdaptiveLearningEngine.record_experience method availability"
                )
            elif "typeerror" in type(e).__name__.lower():
                logger.error("LEARNING_EXPERIENCE: Type error suggests parameter mismatch")
                logger.error(
                    "LEARNING_EXPERIENCE: Check record_experience method signature compatibility"
                )

            # FASE 10: Error escalation
            logger.error(
                "LEARNING_EXPERIENCE: Learning experience recording FAILED - task execution continues"
            )
            logger.error(
                "LEARNING_EXPERIENCE: This affects learning feedback loop but not core functionality"
            )

    async def cleanup_completed_tasks(self, max_age_hours: int = 24) -> None:
        """Clean up old completed tasks"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        completed_tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for task_id, task in self.pending_tasks.items():
            if (
                task.completed_at
                and task.completed_at < cutoff_time
                and task.status in [TaskDistributionStatus.COMPLETED, TaskDistributionStatus.FAILED]
            ):
                completed_tasks.append(task_id)

        for task_id in completed_tasks:
            del self.pending_tasks[task_id]

        if completed_tasks:
            logger.info(f"Cleaned up {len(completed_tasks)} old completed tasks")

    def get_distributor_statistics(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get distributor statistics"""
        total_tasks = len(self.pending_tasks)

        status_counts: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for status in TaskDistributionStatus:
            status_counts[status.value] = len(
                [task for task in self.pending_tasks.values() if task.status == status]
            )

        # Calculate average delivery time
        completed_tasks = [
            task
            for task in self.pending_tasks.values()
            if (
                task.status == TaskDistributionStatus.COMPLETED
                and task.result
                and task.result.duration_ms
            )
        ]

        avg_delivery_time_ms = (
            sum(
                (task.result.duration_ms or 0.0)
                for task in completed_tasks
                if task.result is not None
            )
            / len(completed_tasks)
            if completed_tasks
            else 0.0
        )

        return {
            "total_tasks": total_tasks,
            "task_status_counts": status_counts,
            "average_delivery_time_ms": round(avg_delivery_time_ms, 2),
            "distributor_running": self._running,
            "communication_method": "internal_function_calls",  # NEW: Track method
            "http_client_active": False,  # NO MORE HTTP CLIENT
        }

    def __len__(self) -> int:
        """Get number of pending tasks"""
        return len(self.pending_tasks)


# Global distributor instance
_task_distributor: TaskDistributor | None = None


def get_task_distributor() -> TaskDistributor:
    """Get or create global task distributor instance"""
    global _task_distributor
    if _task_distributor is None:
        _task_distributor = TaskDistributor()
    return _task_distributor


def create_task_distributor(
    agent_registry: AgentRegistry | None = None,
    learning_engine: Any | None = None,  # TODO(TYPE): replace Any with concrete type
) -> TaskDistributor:
    """Create new task distributor instance"""
    return TaskDistributor(agent_registry=agent_registry, learning_engine=learning_engine)


__all__ = [
    "TaskDistributor",
    "TaskDeliveryResult",
    "PendingTask",
    "TaskDistributionStatus",
    "get_task_distributor",
    "create_task_distributor",
]
