"""
Orchestrator Client - API communication with the orchestrator system.

Handles all HTTP calls to the orchestrator API including:
- Task management execution
- Performance metrics retrieval
- System control operations
- Dashboard and agent data fetching

Usage:
    client = OrchestratorClient(api_url)
    result = await client.execute_task_management(command, analysis, context)
"""

from typing import Any, Optional, cast

import httpx
from loguru import logger

from src.core.tool_broker.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    RetryConfig,
    retry_decorator,
)

from . import prompts
from .models import ParsedCommand

# Lazy circuit breaker -- not instantiated at import time
_orchestrator_cb: CircuitBreaker | None = None


def get_orchestrator_cb() -> CircuitBreaker:
    """Lazy factory for the orchestrator circuit breaker."""
    global _orchestrator_cb
    if _orchestrator_cb is None:
        registry = CircuitBreakerRegistry()
        _orchestrator_cb = registry.get_or_create(
            "orchestrator_api",
            CircuitBreakerConfig(
                failure_threshold=5, timeout_seconds=60, success_threshold=2
            ),
        )
    return _orchestrator_cb


class OrchestratorClient:
    """Handles communication with the orchestrator API using non-blocking I/O."""

    def __init__(self, api_url: str) -> None:
        """
        Initialize orchestrator client.

        Args:
            api_url: Base URL for orchestrator API
        """
        self.api_url = api_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "UltimateCVA-CEO/2.0",
        }
        # Connection timeouts (connect, read, write, pool)
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    async def _get_client(self, token: str | None = None) -> httpx.AsyncClient:
        """Create a configured AsyncClient."""
        headers = self.headers.copy()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        return httpx.AsyncClient(base_url=self.api_url, headers=headers, timeout=self.timeout)

    @retry_decorator(config=RetryConfig(max_attempts=3))
    async def get_dashboard_data(self, token: str | None = None) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get system dashboard data."""

        async def _call() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
            async with await self._get_client(token) as client:
                response = await client.get("/api/v1/orchestrator/status")
                if response.status_code == 200:
                    return cast(dict[str, Any], response.json())  # TODO(TYPE): replace Any with concrete type
                raise Exception(f"HTTP {response.status_code}")

        try:
            return await get_orchestrator_cb().call(_call)
        except Exception as e:
            logger.error(f"Dashboard data fetch failed: {e}")
            return {"error": str(e), "status": "connection_failed"}

    async def get_agents_data(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get active agents data."""
        # TODO: Integrate with real agent registry
        return {
            "total_agents": 77,
            "active_agents": 45,
            "agents": [
                {"id": "content-marketer", "status": "active", "load": 0.3},
                {"id": "data-analyst", "status": "active", "load": 0.7},
                {"id": "social-media", "status": "active", "load": 0.5},
            ],
        }

    @retry_decorator(config=RetryConfig(max_attempts=3))
    async def get_performance_metrics(self, token: str | None = None) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get real performance metrics from orchestrator API."""

        async def _call() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
            async with await self._get_client(token) as client:
                response = await client.get("/api/v1/orchestrator/performance/metrics")
                if response.status_code == 200:
                    return cast(dict[str, Any], response.json())  # TODO(TYPE): replace Any with concrete type
                logger.warning(f"Performance metrics failed: HTTP {response.status_code}")
                raise Exception(f"HTTP {response.status_code}")

        try:
            return await get_orchestrator_cb().call(_call)
        except Exception as e:
            logger.error(f"Performance metrics API call failed: {e}")
            return {"error": str(e), "source": "api_failure"}

    async def execute_task_management(
        self,
        parsed_command: ParsedCommand,
        llm_analysis: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        token: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute task management through orchestrator API."""
        try:
            masterprompt = prompts.create_ceo_masterprompt(
                command_type="task_management",
                context={
                    "description": parsed_command.original_text,
                    "priority": context.get("priority", "medium"),
                    "llm_analysis": llm_analysis[:200],
                },
            )
            logger.info(f"Generated CEO masterprompt ({len(masterprompt)} chars)")

            payload = self._build_task_payload(parsed_command, llm_analysis, context, masterprompt)
            return await self._post_multi_agent(payload, token)
        except Exception as e:
            logger.error(f"Task management API call failed: {e}")
            return {"status": "error", "error": str(e)}

    def _build_task_payload(
        self,
        cmd: ParsedCommand,
        analysis: str,
        ctx: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        masterprompt: str,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Build task management API payload."""
        return {
            "description": cmd.original_text,
            "type": "task_management",
            "priority": "medium",
            "masterprompt": masterprompt,
            "context": {
                "llm_analysis": analysis,
                "original_context": ctx,
                "cva_initiated": True,
                "ceo_oversight": True,
            },
        }

    @retry_decorator(config=RetryConfig(max_attempts=2))
    async def _post_multi_agent(
        self, payload: dict[str, Any], token: str | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Post to multi-agent orchestrator endpoint."""

        async def _call() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
            async with await self._get_client(token) as client:
                response = await client.post(
                    "/api/v1/orchestrator/multi-agent",
                    json=payload,
                )
                if response.status_code == 200:
                    logger.info("Task management executed successfully")
                    return {
                        "status": "success",
                        "orchestrator_response": response.json(),
                    }
                logger.error(f"Task management failed: HTTP {response.status_code}")
                raise Exception(f"HTTP {response.status_code}")

        try:
            return await get_orchestrator_cb().call(_call)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute_system_control(
        self,
        parsed_command: ParsedCommand,
        safety_analysis: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        token: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute safe system control through orchestrator API."""
        try:
            payload = {
                "action": parsed_command.original_text,
                "safety_analysis": safety_analysis,
                "context": context,
                "approval_required": True,
                "source": "cva_agent",
            }
            return await self._post_system_control(payload, token)
        except Exception as e:
            logger.error(f"System control API call failed: {e}")
            return {"status": "error", "error": str(e)}

    @retry_decorator(config=RetryConfig(max_attempts=2))
    async def _post_system_control(
        self, payload: dict[str, Any], token: str | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Post to system control endpoint."""

        async def _call() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
            async with await self._get_client(token) as client:
                response = await client.post(
                    "/api/v1/orchestrator/system-control",
                    json=payload,
                )
                if response.status_code == 200:
                    logger.info("System control executed successfully")
                    return {
                        "status": "success",
                        "orchestrator_response": response.json(),
                    }
                raise Exception(f"HTTP {response.status_code}")

        try:
            return await get_orchestrator_cb().call(_call)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @retry_decorator(config=RetryConfig(max_attempts=3))
    async def check_health(self, token: str | None = None) -> bool:
        """Check orchestrator connection health."""

        async def _call() -> bool:
            async with await self._get_client(token) as client:
                response = await client.get("/api/v1/orchestrator/status")
                response.raise_for_status()
                logger.info("Orchestrator connection established")
                return True

        try:
            return await get_orchestrator_cb().call(_call)
        except Exception as e:
            # Log usage of localhost which might fail in docker
            logger.error(f"Orchestrator connection failed to {self.api_url}: {e}")
            return False
