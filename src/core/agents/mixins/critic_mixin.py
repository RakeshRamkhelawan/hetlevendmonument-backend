"""CriticMixin for optional critique integration into existing agents.

This mixin follows the same pattern as LearningMixin, allowing agents to opt-in
to critique functionality with minimal code changes.

Usage:
    class MyAgent(CriticMixin, EnhancedBaseAgent):
        def __init__(self, ...) -> None:
            super().__init__(...)
            self.__init_critic__(mode=CriticMode.ADVISORY)
"""

import logging
from enum import Enum
from typing import Any
from collections.abc import Callable

from src.core.agents.critique_store import Critique, CritiqueStore, get_critique_store
from src.core.shared.interfaces import ExecutionResult

logger = logging.getLogger(__name__)

__all__ = ["CriticMixin", "CriticMode", "with_critic"]


class CriticMode(Enum):
    """Behavior modes for the CriticAgent integration."""

    ADVISORY = "advisory"
    """Output goes directly to caller, critique stored asynchronously.

    Use this for agents where speed is critical and critique is for
    offline analysis and learning.
    """

    BLOCKING = "blocking"
    """CriticAgent sits between agent and caller.

    If score < threshold, task goes back to agent for retry.
    Use this for safety-critical or financial agents.
    """

    SILENT = "silent"
    """Only logging for telemetry and learning.

    Use this for baseline measurement before enabling critique.
    """


class CriticMixin:
    """
    Mixin to add critique functionality to any agent.

    This mixin adds a post_process_task() hook that automatically
    sends ExecutionResults to the CriticAgent for evaluation.

    Example:
        class FinancialAgent(CriticMixin, EnhancedBaseAgent):
            def __init__(self, agent_id, agent_type, tenant_id) -> None:
                super().__init__(agent_id, agent_type, tenant_id)
                self.__init_critic__(mode=CriticMode.BLOCKING)
    """

    def __init_critic__(
        self,
        mode: CriticMode = CriticMode.ADVISORY,
        score_threshold: float = 0.5,
        max_retries: int = 2,
        critique_store: CritiqueStore | None = None,
    ) -> None:
        """
        Initialize critique functionality.

        Args:
            mode: Critic behavior mode (ADVISORY, BLOCKING, SILENT)
            score_threshold: Minimum score for BLOCKING mode (0.0-1.0)
            max_retries: Maximum retries in BLOCKING mode
            critique_store: Optional custom critique store instance
        """
        self._critic_mode = mode
        self._critic_score_threshold = score_threshold
        self._critic_max_retries = max_retries
        self._critic_store = critique_store or get_critique_store()
        self._critic_retry_count: dict[str, int] = {}

        logger.info(
            "Initialized CriticMixin for %s",
            self.__class__.__name__,
            extra={
                "agent_name": self.__class__.__name__,
                "critic_mode": mode.value,
                "score_threshold": score_threshold,
            },
        )

    async def post_process_task(
        self,
        result: ExecutionResult,
        task_id: str,
    ) -> ExecutionResult:
        """
        Post-process task execution result through CriticAgent.

        This method should be called after task execution is complete.
        It will:
        1. Send result to CriticAgent for evaluation
        2. Store critique (in ADVISORY/SILENT mode)
        3. Potentially retry (in BLOCKING mode if score < threshold)

        Args:
            result: The execution result from the agent
            task_id: Unique task identifier

        Returns:
            ExecutionResult (potentially modified in BLOCKING mode)
        """
        # Skip if not initialized or SILENT mode
        if not hasattr(self, "_critic_mode"):
            return result

        if self._critic_mode == CriticMode.SILENT:
            # Just log, don't actually critique
            logger.debug(
                "SILENT mode: Would critique task %s",
                task_id,
                extra={"agent_name": self.__class__.__name__, "task_id": task_id},
            )
            return result

        # Get or create CriticAgent
        from src.core.agents.critic_agent import CriticAgent

        try:
            critic = CriticAgent(tenant_id=getattr(self, "tenant_id", 1))

            # Submit for critique
            critique = await critic.critique_task(
                agent_name=self.__class__.__name__,
                task_id=task_id,
                result=result,
                mode=self._critic_mode.value,
            )

            if self._critic_mode == CriticMode.ADVISORY:
                # Store critique asynchronously, don't block
                await self._store_critique_async(critique)
                return result

            elif self._critic_mode == CriticMode.BLOCKING:
                # Check score and potentially retry
                if critique.score < self._critic_score_threshold:
                    retry_count = self._critic_retry_count.get(task_id, 0)

                    result_meta: ExecutionResult = result
                    if retry_count < self._critic_max_retries:
                        self._critic_retry_count[task_id] = retry_count + 1

                        logger.warning(
                            "Task %s failed critique (score: %.2f), retrying (%d/%d)",
                            task_id,
                            critique.score,
                            retry_count + 1,
                            self._critic_max_retries,
                            extra={
                                "agent_name": self.__class__.__name__,
                                "task_id": task_id,
                                "score": critique.score,
                                "retry": retry_count + 1,
                            },
                        )

                        # Mark result for retry
                        result_meta.metadata = result_meta.metadata or {}
                        result_meta.metadata["critique_score"] = critique.score
                        result_meta.metadata["critique_issues"] = critique.issues
                        result_meta.metadata["needs_retry"] = True
                    else:
                        # Max retries exceeded, return with warning
                        result_meta.metadata = result_meta.metadata or {}
                        result_meta.metadata["critique_score"] = critique.score
                        result_meta.metadata["critique_issues"] = critique.issues
                        result_meta.metadata["max_retries_exceeded"] = True

                        logger.error(
                            "Task %s failed critique after %d retries",
                            task_id,
                            self._critic_max_retries,
                            extra={
                                "agent_name": self.__class__.__name__,
                                "task_id": task_id,
                                "final_score": critique.score,
                            },
                        )

                # Store critique
                await self._critic_store.store(critique)
                return result

            # Fallback for any other mode
            return result

        except Exception as e:
            # Don't let critique failures break the agent
            logger.error(
                "Critique failed for task %s: %s",
                task_id,
                e,
                extra={"agent_name": self.__class__.__name__, "task_id": task_id},
            )
            return result

    async def _store_critique_async(self, critique: Critique) -> None:
        """Store critique asynchronously (don't await)."""
        import asyncio

        try:
            # Fire and forget
            asyncio.create_task(self._critic_store.store(critique))
        except Exception as e:
            logger.debug("Failed to schedule critique storage: %s", e)

    def get_critic_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get critique statistics for this agent."""
        if not hasattr(self, "_critic_store"):
            return {"error": "CriticMixin not initialized"}

        import asyncio

        # Run async method synchronously
        try:
            stats = asyncio.run(
                self._critic_store.get_stats(tenant_id=getattr(self, "tenant_id", 1))
            )
            return stats
        except Exception as e:
            return {"error": str(e)}


def with_critic(
    mode: CriticMode = CriticMode.ADVISORY,
    score_threshold: float = 0.5,
    max_retries: int = 2,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:  # TODO(TYPE): replace with concrete type
    """
    Decorator to add critique to any agent method.

    Usage:
        @with_critic(mode=CriticMode.BLOCKING)
        async def process_task(self, task):
            ...
    """

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Any]:  # TODO(TYPE): replace with concrete type
        async def wrapper(
            self: Any, *args: Any, **kwargs: Any
        ) -> (
            # TODO(TYPE): replace Any with concrete type
            Any
        ):  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
            # Execute original function
            result = await func(self, *args, **kwargs)

            # Get task_id from args or kwargs
            task_id = kwargs.get("task_id") or (args[0].id if args else "unknown")

            # Post-process through critic
            if hasattr(self, "post_process_task"):
                result = await self.post_process_task(result, task_id)

            return result

        return wrapper

    return decorator
