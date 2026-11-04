#!/usr/bin/env python3
"""
Multi-Agent Workflow Engine
Phase 2/3 - Enhanced Workflow Orchestration with Agent Mesh Integration
Building on orchestrator test results (9.1/10 rating) + Phase 3 collaboration
"""

import asyncio
import logging
import time
import uuid

logger = logging.getLogger(__name__)
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.agents.subagent_loader import SubagentLoader, get_subagent_loader

# Phase 3 Integration - Agent Mesh Collaboration (DISABLED - Not yet implemented)
# from core.collaboration.agent_mesh import get_agent_mesh, AgentMessage, MessageType, MessagePriority
# from core.collaboration.task_coordinator import get_task_coordinator, TaskRequirement
# from core.knowledge.adaptive_learning import get_adaptive_learning, LearningExperience, LearningType, LearningOutcome


class WorkflowExecutionMode(Enum):
    """Execution patterns for workflows"""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    MIXED = "mixed"


class TaskStatus(Enum):
    """Task execution status"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class TaskPriority(Enum):
    """Task priority levels"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class WorkflowTask:
    """Individual task within a workflow"""

    task_id: str
    name: str
    description: str
    agent_type: str
    parameters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    dependencies: list[str] | None = field(default=None)
    priority: TaskPriority = field(default=TaskPriority.MEDIUM)
    status: TaskStatus = TaskStatus.PENDING
    result: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    error: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration: float | None = None

    def __post_init__(self) -> None:
        if self.dependencies is None:
            self.dependencies = []


@dataclass
class WorkflowDefinition:
    """Complete workflow structure"""

    workflow_id: str
    name: str
    description: str
    execution_mode: WorkflowExecutionMode
    tasks: list[WorkflowTask]
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    timeout: int = 300  # 5 minutes default

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


@dataclass
class WorkflowExecution:
    """Workflow execution tracking"""

    execution_id: str
    workflow_id: str
    status: TaskStatus
    start_time: datetime
    end_time: datetime | None = None
    duration: float | None = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_total: int = 0
    results: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    def __post_init__(self) -> None:
        if self.results is None:
            self.results = {}


class WorkflowEngine:
    """Multi-Agent Workflow Engine with Sequential & Parallel Execution + Phase 3 Collaboration"""

    def __init__(self) -> None:
        self.workflows: dict[str, WorkflowDefinition] = {}
        self.executions: dict[str, WorkflowExecution] = {}
        self.executor = ThreadPoolExecutor(max_workers=10)

        # Phase 3 Integration - Collaboration Systems
        self.agent_mesh: Any = None
        self.task_coordinator: Any = None
        self.adaptive_learning: Any = None
        self.collaboration_enabled = False

    @property
    def subagent_loader(self) -> "SubagentLoader":
        """Lazy accessor -- always returns the current singleton."""
        return get_subagent_loader()

    async def enable_collaboration(self) -> None:
        """Enable Phase 3 collaboration features - DISABLED (not yet implemented)"""
        # Phase 3 collaboration disabled until modules are implemented
        self.agent_mesh = None
        self.task_coordinator = None
        self.adaptive_learning = None
        self.collaboration_enabled = False
        print("[INFO] Phase 3 collaboration features disabled (not yet implemented)")

    def register_workflow(self, workflow: WorkflowDefinition) -> str:
        """Register a new workflow definition"""
        self.workflows[workflow.workflow_id] = workflow
        return workflow.workflow_id

    def create_workflow(
        self,
        name: str,
        description: str,
        execution_mode: WorkflowExecutionMode = WorkflowExecutionMode.SEQUENTIAL,
    ) -> str:
        """Create a new workflow"""
        workflow_id = f"workflow_{uuid.uuid4().hex[:8]}"
        workflow = WorkflowDefinition(
            workflow_id=workflow_id,
            name=name,
            description=description,
            execution_mode=execution_mode,
            tasks=[],
        )
        return self.register_workflow(workflow)

    def add_task(
        self,
        workflow_id: str,
        name: str,
        description: str,
        agent_type: str,
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        dependencies: list[str] | None = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
    ) -> str:
        """Add a task to a workflow"""
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow {workflow_id} not found")

        task_id = f"task_{uuid.uuid4().hex[:8]}"
        task = WorkflowTask(
            task_id=task_id,
            name=name,
            description=description,
            agent_type=agent_type,
            parameters=parameters,
            dependencies=dependencies or [],
            priority=priority,
        )

        self.workflows[workflow_id].tasks.append(task)
        return task_id

    def _validate_dependencies(self, workflow: WorkflowDefinition) -> list[str]:
        """Validate workflow task dependencies"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        task_ids = {task.task_id for task in workflow.tasks}

        for task in workflow.tasks:
            deps = task.dependencies or []
            for dep in deps:
                if dep not in task_ids:
                    errors.append(f"Task {task.task_id} has invalid dependency: {dep}")

        return errors

    def _build_execution_plan(self, workflow: WorkflowDefinition) -> list[list[str]]:
        """Build task execution plan based on dependencies"""
        completed: set[str] = set()
        execution_plan: list[list[str]] = []

        max_iterations = len(workflow.tasks) + 1
        iteration = 0

        while len(completed) < len(workflow.tasks) and iteration < max_iterations:
            batch: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for task in workflow.tasks:
                task_deps = task.dependencies or []
                if task.task_id not in completed and all(dep in completed for dep in task_deps):
                    batch.append(task.task_id)

            if not batch:
                # Find circular dependencies or unresolvable tasks
                remaining = [t.task_id for t in workflow.tasks if t.task_id not in completed]
                execution_plan.append(
                    [f"ERROR: Circular or unresolvable dependencies: {remaining}"]
                )
                break

            execution_plan.append(batch)
            completed.update(batch)
            iteration += 1

        return execution_plan

    async def execute_task(
        self,
        task: WorkflowTask,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute a single task using REAL subagent with LLM integration - NO MOCK/SIMULATION"""
        task.status = TaskStatus.RUNNING
        task.start_time = datetime.now(timezone.utc)
        start_timestamp = time.time()

        def log_to_file(message: str) -> None:
            with open("log.md", "a", encoding="utf-8") as f:
                f.write(f"\n{message}")

        try:
            # Phase 3 Enhancement: Try collaborative task execution first
            if self.collaboration_enabled and self.task_coordinator:
                collaborative_result = await self._try_collaborative_execution(task, context)
                if collaborative_result:
                    return collaborative_result

            # Get available subagents for REAL execution
            from typing import cast

            subagents = cast(
                list[Any],  # TODO(TYPE): replace Any with concrete type
                self.subagent_loader.get_subagents_by_category(task.agent_type) or [],
            )

            if not subagents:
                # Fallback to any matching subagent
                all_subagents = cast(
                    # TODO(TYPE): replace Any with concrete type
                    list[Any],
                    self.subagent_loader.get_all_subagents()
                    or [],  # TODO(TYPE): replace Any with concrete type
                )  # TODO(TYPE): replace Any with concrete type
                matching = [
                    s
                    for s in all_subagents
                    if hasattr(s, "name")
                    and task.agent_type.lower() in getattr(s, "name", "").lower()
                ]
                subagents = matching[:1]  # Take first match

            if not subagents:
                raise ValueError(f"No suitable subagent found for type: {task.agent_type}")

            # Select best subagent (for now, use first available)
            selected_agent = subagents[0]

            # Get agent name safely
            agent_name = (
                getattr(selected_agent, "name", "UNKNOWN").upper().replace(" ", "_")
                if hasattr(selected_agent, "name")
                else "UNKNOWN_AGENT"
            )
            agent_desc = (
                getattr(selected_agent, "description", "No description")
                if hasattr(selected_agent, "description")
                else "No description"
            )
            log_to_file(f"**{agent_name}:** [REAL_WORKFLOW_EXECUTION] Task: {task.name}")
            log_to_file(f"**{agent_name}:** [SUBAGENT_DETAILS] {agent_desc}")

            # Create TaskData for real LLM execution via subagent API
            from src.core.shared.interfaces import TaskData

            # Convert local TaskPriority enum to expected type
            from src.core.types import TaskPriority as CoreTaskPriority

            _raw_int: int = task.priority.value if isinstance(task.priority.value, int) else 3
            try:
                priority_value = CoreTaskPriority(_raw_int)
            except ValueError:
                priority_value = CoreTaskPriority.MEDIUM

            # Build metadata safely
            metadata: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "workflow_context": context or {},
                "task_parameters": task.parameters,
                "agent_type": task.agent_type,
            }
            if hasattr(selected_agent, "name"):
                metadata["subagent_name"] = getattr(selected_agent, "name", "unknown")
            # Note: AgentDefinition may not have model/system_prompt attributes
            # Use getattr with defaults for optional attributes
            model_attr = getattr(selected_agent, "model", None)
            if model_attr is not None:
                metadata["subagent_model"] = (
                    getattr(model_attr, "value", str(model_attr))
                    if hasattr(model_attr, "value")
                    else str(model_attr)
                )
            if hasattr(selected_agent, "capabilities"):
                metadata["subagent_capabilities"] = getattr(selected_agent, "capabilities", [])
            system_prompt = getattr(selected_agent, "system_prompt", None)
            if system_prompt is not None:
                metadata["subagent_system_prompt"] = system_prompt

            specialized_task_data = TaskData(
                id=task.task_id,
                title=task.name,
                description=task.description,
                priority=priority_value,
                assigned_to="workflow_engine",
                metadata=metadata,
            )

            # Execute with REAL BaseAgent using subagent specialization
            from src.core.agents.base_agent import EnhancedBaseAgent
            from src.core.types import AgentType

            # Get agent name for ID safely
            agent_name_for_id = getattr(selected_agent, "name", "unknown").lower().replace(" ", "_")
            base_agent = EnhancedBaseAgent(
                agent_id=f"workflow_subagent_{agent_name_for_id}",
                agent_type=AgentType.SPECIALIST,
                tenant_id=int((context or {}).get("tenant_id", 1)),
            )

            # Get model value safely
            model_attr = getattr(selected_agent, "model", None)
            model_value = (
                getattr(model_attr, "value", str(model_attr))
                if model_attr is not None
                else "unknown"
            )
            log_to_file(f"**{agent_name}:** [REAL_LLM_CALL] Executing with {model_value}")

            # REAL EXECUTION - NO MOCK/SIMULATION
            execution_result = await base_agent.process_task(specialized_task_data)

            execution_time = time.time() - start_timestamp

            if execution_result and execution_result.success:
                # Real successful execution
                task.status = TaskStatus.COMPLETED
                task.end_time = datetime.now(timezone.utc)
                task.duration = execution_time
                task.result = {
                    "agent": selected_agent.name,
                    "status": "success",
                    "execution_time": execution_time,
                    "real_output": execution_result.result_data,
                    "parameters_processed": task.parameters,
                    "context": context or {},
                    "collaboration_used": False,
                    "execution_type": "REAL_LLM_EXECUTION",
                    "is_mock": False,
                    "provider_used": (
                        str(execution_result.result_data.get("provider_used", "unknown"))
                        if execution_result.result_data
                        else "unknown"
                    ),
                }

                log_to_file(f"**{agent_name}:** [REAL_SUCCESS] Completed in {execution_time:.2f}s")
                log_to_file(
                    f"**{agent_name}:** [OUTPUT_READY] Real LLM output: {len(str(execution_result.result_data))} chars"  # noqa: E501
                )

                # Phase 3 Enhancement: Record learning experience
                if self.collaboration_enabled and self.adaptive_learning:
                    await self._record_task_learning_experience(task, task.result, True)

                return task.result

            # Real execution failed
            task.status = TaskStatus.FAILED
            task.end_time = datetime.now(timezone.utc)
            task.duration = execution_time
            error_msg = "Real execution failed"
            if execution_result is not None:
                error_msg = (
                    getattr(execution_result, "error_message", None) or "Real execution failed"
                )
            task.error = error_msg

            log_to_file(
                f"**{agent_name}:** [REAL_FAILURE] Failed in {execution_time:.2f}s: {task.error}"
            )

            result = {
                "agent": selected_agent.name,
                "status": "failed",
                "execution_time": execution_time,
                "error": error_msg,
                "execution_type": "REAL_LLM_EXECUTION_FAILED",
                "is_mock": False,
            }

            # Phase 3 Enhancement: Record failed learning experience
            if self.collaboration_enabled and self.adaptive_learning:
                await self._record_task_learning_experience(task, result, False)

            return result

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.end_time = datetime.now(timezone.utc)
            if task.start_time:
                task.duration = (task.end_time - task.start_time).total_seconds()
            else:
                task.duration = 0.0

            # Phase 3 Enhancement: Record failed learning experience
            if self.collaboration_enabled and self.adaptive_learning:
                result = {
                    "agent": task.agent_type,
                    "status": "failed",
                    "error": str(e),
                    "execution_time": task.duration,
                    "collaboration_used": False,
                }
                await self._record_task_learning_experience(task, result, False)

            return {
                "agent": task.agent_type,
                "status": "failed",
                "error": str(e),
                "execution_time": task.duration,
            }

    async def execute_workflow(
        self,
        workflow_id: str,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Execute a complete workflow"""
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow {workflow_id} not found")

        workflow = self.workflows[workflow_id]

        # Validate workflow
        errors = self._validate_dependencies(workflow)
        if errors:
            raise ValueError(f"Workflow validation failed: {'; '.join(errors)}")

        # Create execution tracking
        execution_id = f"exec_{uuid.uuid4().hex[:8]}"
        execution = WorkflowExecution(
            execution_id=execution_id,
            workflow_id=workflow_id,
            status=TaskStatus.RUNNING,
            start_time=datetime.now(timezone.utc),
            tasks_total=len(workflow.tasks),
        )
        self.executions[execution_id] = execution

        try:
            # Build execution plan
            execution_plan = self._build_execution_plan(workflow)

            # Execute based on workflow mode
            if workflow.execution_mode == WorkflowExecutionMode.SEQUENTIAL:
                await self._execute_sequential(workflow, execution_plan, context)
            elif workflow.execution_mode == WorkflowExecutionMode.PARALLEL:
                await self._execute_parallel(workflow, execution_plan, context)
            else:  # MIXED mode
                await self._execute_mixed(workflow, execution_plan, context)

            # Update execution status
            execution.status = TaskStatus.COMPLETED
            execution.end_time = datetime.now(timezone.utc)
            execution.duration = (execution.end_time - execution.start_time).total_seconds()

            # Collect results
            execution.results = {
                "tasks": [asdict(task) for task in workflow.tasks],
                "execution_plan": execution_plan,
                "summary": {
                    "total_tasks": len(workflow.tasks),
                    "completed": sum(1 for t in workflow.tasks if t.status == TaskStatus.COMPLETED),
                    "failed": sum(1 for t in workflow.tasks if t.status == TaskStatus.FAILED),
                    "duration": execution.duration,
                },
            }

            execution.tasks_completed = execution.results["summary"]["completed"]
            execution.tasks_failed = execution.results["summary"]["failed"]

        except Exception as e:
            execution.status = TaskStatus.FAILED
            execution.end_time = datetime.now(timezone.utc)
            execution.duration = (execution.end_time - execution.start_time).total_seconds()
            execution.results = {"error": str(e)}

        return execution_id

    async def _execute_sequential(
        self,
        workflow: WorkflowDefinition,
        execution_plan: list[list[str]],
        context: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Execute workflow sequentially"""
        task_map = {task.task_id: task for task in workflow.tasks}

        for batch in execution_plan:
            for task_id in batch:
                if task_id.startswith("ERROR:"):
                    raise ValueError(task_id)

                task = task_map[task_id]
                await self.execute_task(task, context)

    async def _execute_parallel(
        self,
        workflow: WorkflowDefinition,
        execution_plan: list[list[str]],
        context: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Execute workflow in parallel where possible"""
        task_map = {task.task_id: task for task in workflow.tasks}

        for batch in execution_plan:
            if any(task_id.startswith("ERROR:") for task_id in batch):
                raise ValueError(batch[0])

            # Execute all tasks in this batch concurrently
            tasks_to_execute = [task_map[task_id] for task_id in batch]
            await asyncio.gather(*[self.execute_task(task, context) for task in tasks_to_execute])

    async def _execute_mixed(
        self,
        workflow: WorkflowDefinition,
        execution_plan: list[list[str]],
        context: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Execute workflow with mixed sequential/parallel patterns"""
        task_map = {task.task_id: task for task in workflow.tasks}

        for batch in execution_plan:
            if any(task_id.startswith("ERROR:") for task_id in batch):
                raise ValueError(batch[0])

            # For mixed mode, execute high priority tasks sequentially, others in parallel
            high_priority_tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            other_tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for task_id in batch:
                task = task_map[task_id]
                if task.priority in [TaskPriority.HIGH, TaskPriority.CRITICAL]:
                    high_priority_tasks.append(task)
                else:
                    other_tasks.append(task)

            # Execute high priority first (sequential)
            for task in high_priority_tasks:
                await self.execute_task(task, context)

            # Execute others in parallel
            if other_tasks:
                await asyncio.gather(*[self.execute_task(task, context) for task in other_tasks])

    def get_workflow(self, workflow_id: str) -> WorkflowDefinition | None:
        """Get workflow definition"""
        return self.workflows.get(workflow_id)

    def get_execution(self, execution_id: str) -> WorkflowExecution | None:
        """Get workflow execution status"""
        return self.executions.get(execution_id)

    def list_workflows(self) -> list[WorkflowDefinition]:
        """List all registered workflows"""
        return list(self.workflows.values())

    def list_executions(self) -> list[WorkflowExecution]:
        """List all workflow executions"""
        return list(self.executions.values())

    def get_workflow_status(
        self, workflow_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current status of a workflow execution"""
        execution = None
        for exec_id, exec_obj in self.executions.items():
            if exec_obj.workflow_id == workflow_id:
                execution = exec_obj
                break

        if not execution:
            return {
                "workflow_id": workflow_id,
                "status": "not_found",
                "message": f"No execution found for workflow {workflow_id}",
            }

        workflow = self.workflows.get(workflow_id)

        return {
            "workflow_id": workflow_id,
            "execution_id": execution.execution_id,
            "status": execution.status.value,
            "start_time": execution.start_time.isoformat() if execution.start_time else None,
            "end_time": execution.end_time.isoformat() if execution.end_time else None,
            "duration": execution.duration,
            "tasks_total": execution.tasks_total,
            "tasks_completed": execution.tasks_completed,
            "tasks_failed": execution.tasks_failed,
            "progress_percentage": (
                (execution.tasks_completed / execution.tasks_total * 100)
                if execution.tasks_total > 0
                else 0
            ),
            "workflow_name": workflow.name if workflow else "Unknown",
            "execution_mode": workflow.execution_mode.value if workflow else "Unknown",
        }

    def get_workflow_results(
        self, workflow_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get results from completed workflow execution"""
        execution = None
        for exec_id, exec_obj in self.executions.items():
            if exec_obj.workflow_id == workflow_id:
                execution = exec_obj
                break

        if not execution:
            return {
                "workflow_id": workflow_id,
                "found": False,
                "message": f"No execution found for workflow {workflow_id}",
            }

        return {
            "workflow_id": workflow_id,
            "execution_id": execution.execution_id,
            "found": True,
            "status": execution.status.value,
            "results": execution.results,
            "duration": execution.duration,
            "completed": execution.status == TaskStatus.COMPLETED,
        }

    def get_workflow_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get workflow engine statistics"""
        # Get subagents count safely
        try:
            if hasattr(self.subagent_loader, "get_all_subagents"):
                all_subagents = self.subagent_loader.get_all_subagents()
                subagents_count = len(all_subagents) if all_subagents is not None else 0
            else:
                subagents_count = 0
        except Exception:
            subagents_count = 0

        return {
            "total_workflows": len(self.workflows),
            "total_executions": len(self.executions),
            "active_executions": sum(
                1 for e in self.executions.values() if e.status == TaskStatus.RUNNING
            ),
            "successful_executions": sum(
                1 for e in self.executions.values() if e.status == TaskStatus.COMPLETED
            ),
            "failed_executions": sum(
                1 for e in self.executions.values() if e.status == TaskStatus.FAILED
            ),
            "subagents_available": subagents_count,
        }

    # Phase 3 Collaboration Helper Methods (DISABLED)
    async def _try_collaborative_execution(
        self,
        task: WorkflowTask,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Try to execute task using collaborative agents - DISABLED (Phase 3 not implemented)"""
        logger.debug("Collaborative execution skipped for task %s (Phase 3 disabled)", task.task_id)
        return None

    async def _record_task_learning_experience(
        self,
        task: WorkflowTask,
        result: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        success: bool,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Record task execution as learning experience - DISABLED (Phase 3 not implemented)"""
        logger.debug("Task learning experience skipped for task %s (Phase 3 disabled)", task.task_id)
        return

    async def get_collaboration_insights(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get insights from Phase 3 collaboration systems"""
        if not self.collaboration_enabled:
            return {"collaboration_enabled": False}

        try:
            insights = {"collaboration_enabled": True}

            # Agent mesh insights - Phase 3 disabled
            if self.agent_mesh is not None:
                mesh_metrics = await self.agent_mesh.get_network_metrics()
                insights["agent_mesh"] = mesh_metrics

            # Task coordination insights - Phase 3 disabled
            if self.task_coordinator is not None:
                coord_metrics = await self.task_coordinator.get_coordination_metrics()
                insights["task_coordinations"] = coord_metrics

            # Learning insights - Phase 3 disabled
            if self.adaptive_learning is not None:
                learning_metrics = await self.adaptive_learning.get_learning_metrics()
                insights["adaptive_learning"] = learning_metrics

            return insights

        except Exception as e:
            return {"collaboration_enabled": True, "error": str(e)}


# Global workflow engine instance
_workflow_engine: WorkflowEngine | None = None


def get_workflow_engine() -> WorkflowEngine:
    """Get global workflow engine instance"""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine
