"""External Agent Bridge - Transparent wrapper for external agents.

This module implements the ExternalAgentBridge which:
- Wraps external agents as internal agents
- Is transparent to DomainPackOrchestrator
- Handles dispatch with retry logic
- Enforces SLA timeouts
- Validates output

Architecture:
- Extends EnhancedBaseAgent for compatibility
- Uses ExternalAgentService for API calls
- Implements retry with exponential backoff
- Validates outputs with PolicyEngine
"""

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import cast

from src.core.agents.base_agent import AgentType, EnhancedBaseAgent, ExecutionResult, TaskData
from src.core.company.context import AgentExecutionContext
from src.core.company.external_agent_service import ExternalAgentService
from src.core.company.models import ExternalAgent
from src.core.exceptions.exceptions import ValidationError


class ExternalAgentDispatchError(Exception):
    """Failed to dispatch task to external agent after retries."""

    pass


class TaskTimeoutError(Exception):
    """Task exceeded SLA timeout."""

    pass


class TaskAssignment:
    """Task assignment to external agent."""

    def __init__(self, task_id: uuid.UUID, agent_id: str) -> None:
        self.task_id = task_id
        self.agent_id = agent_id


class TaskCompletion:
    """Task completion from external agent."""

    def __init__(
        self,
        task_id: uuid.UUID,
        status: str,
        output: dict[str, object],
        reasoning_trace: str | None = None,
    ) -> None:
        self.task_id = task_id
        self.status = status
        self.output = output
        self.reasoning_trace = reasoning_trace


class ExternalAgentBridge(EnhancedBaseAgent):
    """Bridge that wraps external agent as internal agent.

    DomainPackOrchestrator sees no difference between this and
    internal agents - the bridge handles all external communication.

    Retry strategy: [1, 5, 30] seconds
    Default SLA: 300 seconds (5 minutes)
    Max output size: 10MB
    """

    DEFAULT_SLA_SECONDS = 300
    MAX_OUTPUT_SIZE = 10 * 1024 * 1024  # 10MB
    RETRY_BACKOFF = [1, 5, 30]  # seconds

    def __init__(
        self,
        external_agent: ExternalAgent,
        service: ExternalAgentService,
    ) -> None:
        """Initialize bridge.

        Args:
            external_agent: External agent configuration
            service: ExternalAgentService for API calls
        """
        agent_id = f"ext-{external_agent.id}"
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.SPECIALIST,
            tenant_id=external_agent.tenant_id,
        )
        self.external_agent = external_agent
        self.service = service

    def _resolve_context(self, task: "TaskData") -> AgentExecutionContext | None:
        """Resolve AgentExecutionContext from task, preferring typed company_context field."""
        # Prefer the new typed field (Task 1 of this plan)
        if hasattr(task, "company_context") and isinstance(
            task.company_context, AgentExecutionContext
        ):
            return task.company_context
        # Fall back to legacy metadata alias for backward compat
        ctx_data = getattr(task, "context", None)
        if isinstance(ctx_data, AgentExecutionContext):
            return ctx_data
        return None

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Process task with context validation (public API).

        Args:
            task: Task data from orchestrator

        Returns:
            ExecutionResult from external agent

        Raises:
            ValueError: If no context (Golden Rule R1)
        """
        # Golden Rule R1: Validate context
        context = self._resolve_context(task)
        if context is None:
            raise ValueError("Task must have AgentExecutionContext (Golden Rule R1)")

        return await self._process_task_external(task)

    async def _process_task_external(self, task: TaskData) -> ExecutionResult:
        """Internal implementation of task processing.

        Args:
            task: Task data from orchestrator

        Returns:
            ExecutionResult from external agent

        Raises:
            ValueError: If no context (Golden Rule R1)
            ExternalAgentDispatchError: If dispatch fails after retries
            TaskTimeoutError: If SLA exceeded
        """
        # Golden Rule R1: Validate context
        context = self._resolve_context(task)
        if context is None:
            raise ValueError("Task must have AgentExecutionContext (Golden Rule R1)")

        # Validate context completeness
        is_valid, missing = context.validate_completeness()
        if not is_valid:
            context.is_degraded = True
            # Still proceed in degraded mode, but log warning
            print(f"[WARNING] Context incomplete: {missing}")

        # Dispatch to external agent with retry
        try:
            assignment = await self._dispatch_with_retry(task)
        except ExternalAgentDispatchError:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data={},
                error_message="Failed to dispatch to external agent after retries",
            )

        # Wait for completion with SLA timeout
        sla_seconds: int = getattr(task, "sla_seconds", None) or self.DEFAULT_SLA_SECONDS
        try:
            completion = await self._wait_for_completion(
                assignment.task_id,
                sla_seconds,
            )
        except TaskTimeoutError:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data={},
                error_message=f"Task exceeded SLA of {sla_seconds} seconds",
            )

        # Validate output
        try:
            validated_output = self._validate_output(completion.output, context)
        except ValidationError as e:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data=completion.output,
                error_message=f"Output validation failed: {e}",
            )

        return ExecutionResult(
            task_id=task.id,
            success=completion.status == "completed",
            result_data=validated_output,
        )

    async def _dispatch_with_retry(self, task: TaskData) -> TaskAssignment:
        """Dispatch task with exponential backoff retry.

        Args:
            task: Task to dispatch

        Returns:
            TaskAssignment

        Raises:
            ExternalAgentDispatchError: After all retries exhausted
        """
        last_error: Exception | None = None

        for attempt, delay in enumerate(self.RETRY_BACKOFF):
            try:
                return await self._dispatch(task)
            except Exception as e:
                last_error = e
                if attempt < len(self.RETRY_BACKOFF) - 1:
                    await asyncio.sleep(delay)

        raise ExternalAgentDispatchError(
            f"Failed to dispatch after {len(self.RETRY_BACKOFF)} attempts: {last_error}"
        )

    async def _dispatch(self, task: TaskData) -> TaskAssignment:
        """Dispatch task to external agent.

        Args:
            task: Task to dispatch

        Returns:
            TaskAssignment
        """
        # Via webhook or queue
        if self.external_agent.webhook_url:
            return await self._dispatch_via_webhook(task)
        else:
            return await self._dispatch_via_queue(task)

    async def _dispatch_via_webhook(self, task: TaskData) -> TaskAssignment:
        """Dispatch via HTTP webhook."""
        import httpx

        # Extract action and input from task metadata
        action = task.metadata.get("action", "") if task.metadata else ""
        input_data = task.metadata.get("input", {}) if task.metadata else {}

        # Extract context and convert to dict if needed
        context_data = task.context
        context_dict: dict[str, object] | None = None
        if isinstance(context_data, AgentExecutionContext):
            context_dict = context_data.model_dump(mode="json")
        elif isinstance(context_data, dict):
            context_dict = context_data

        # Extract sla_seconds from task metadata or use default
        sla_seconds: int | None = task.metadata.get("sla_seconds") if task.metadata else None
        sla: int = sla_seconds or self.DEFAULT_SLA_SECONDS

        payload = {
            "task_id": str(task.task_id),
            "action": action,
            "input": input_data,
            "context": context_dict,
            "sla_seconds": sla,
        }

        # Ensure webhook_url is not None
        webhook_url: str | None = self.external_agent.webhook_url
        if webhook_url is None:
            raise ExternalAgentDispatchError("Webhook URL is not configured")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            data: dict[str, object] = response.json()
            task_id_str: str | object = data.get("task_id", str(task.task_id))
            # Convert string to UUID
            task_id_uuid: uuid.UUID = (
                uuid.UUID(task_id_str)
                if isinstance(task_id_str, str)
                else cast(uuid.UUID, task_id_str)
            )
            return TaskAssignment(
                task_id=task_id_uuid,
                agent_id=self.agent_id,
            )

    async def _dispatch_via_queue(self, task: TaskData) -> TaskAssignment:
        """Dispatch via internal queue."""
        # TODO: Implement queue-based dispatch
        # For now, create assignment and let agent poll
        # Convert task.task_id (str) to UUID
        task_id_uuid: uuid.UUID = (
            uuid.UUID(task.task_id)
            if isinstance(task.task_id, str)
            else cast(uuid.UUID, task.task_id)
        )
        return TaskAssignment(
            task_id=task_id_uuid,
            agent_id=self.agent_id,
        )

    async def _wait_for_completion(
        self,
        task_id: uuid.UUID,
        timeout_seconds: int,
    ) -> TaskCompletion:
        """Poll for task completion.

        Args:
            task_id: Task to wait for
            timeout_seconds: Maximum wait time

        Returns:
            TaskCompletion

        Raises:
            TaskTimeoutError: If timeout exceeded
        """
        start_time = asyncio.get_event_loop().time()
        poll_interval = 5  # seconds

        while True:
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                raise TaskTimeoutError(f"Task {task_id} exceeded {timeout_seconds}s timeout")

            get_task_status = getattr(self.service, "get_task_status", None)
            if callable(get_task_status):
                _typed_fn = cast(Callable[[uuid.UUID], Awaitable[TaskCompletion]], get_task_status)
                status = await _typed_fn(task_id)
            else:
                status = await self._get_task_status_fallback(task_id)

            if status.status in ["completed", "failed"]:
                return status

            # Wait before next poll
            await asyncio.sleep(poll_interval)

    async def _get_task_status_fallback(self, task_id: uuid.UUID) -> TaskCompletion:
        """Fallback method to get task status.

        Args:
            task_id: Task UUID

        Returns:
            TaskCompletion with current status
        """
        # TODO: Implement proper task status retrieval from database
        # For now, return a pending status
        return TaskCompletion(
            task_id=task_id,
            status="pending",
            output={},
        )

    def _validate_output(
        self,
        output: dict[str, object],
        context: AgentExecutionContext,
    ) -> dict[str, object]:
        """Validate task output.

        Args:
            output: Raw output from agent
            context: Execution context for validation

        Returns:
            Validated output

        Raises:
            ValidationError: If output is invalid
        """
        # Check size
        output_size = len(json.dumps(output).encode("utf-8"))
        if output_size > self.MAX_OUTPUT_SIZE:
            raise ValidationError(f"Output size {output_size} exceeds max {self.MAX_OUTPUT_SIZE}")

        # Check required fields
        if "status" not in output:
            raise ValidationError("Output missing required 'status' field")

        # PolicyEngine validation
        # TODO: Integrate with PolicyEngine for risk assessment

        return output
