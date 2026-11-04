"""
SandboxToolBroker -- IToolBroker decorator that routes code execution via sandbox.

Execution path:
  CopilotService -> SandboxToolBroker -> ScopedToolBroker -> ToolBrokerService

Tools with prefix "code__" or payload flag "_execute_code=True" are routed
through TenantSandboxOrchestrator for Docker-isolated execution. All other
tools pass directly to the inner broker.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.copilot.protocols import IToolBroker
from src.core.sandbox.tenant_sandbox_orchestrator import (
    SandboxConfig,
    SandboxType,
    TenantSandboxOrchestrator,
)
from src.core.shared.config import get_settings

logger = logging.getLogger(__name__)

_CODE_TOOL_PREFIXES = frozenset(["code__"])


class SandboxToolBroker:
    """
    IToolBroker decorator that routes code-execution tools through
    TenantSandboxOrchestrator for tenant-isolated Docker execution.

    Non-code tools pass straight through to the inner broker without
    any performance overhead.
    """

    def __init__(
        self,
        orchestrator: TenantSandboxOrchestrator,
        inner: IToolBroker,
    ) -> None:
        self._orchestrator = orchestrator
        self._inner = inner

    def _is_code_tool(self, tool_name: str, payload: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        return any(tool_name.startswith(p) for p in _CODE_TOOL_PREFIXES) or bool(
            payload.get("_execute_code")
        )

    async def execute_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        agent_id: str | None = None,
        timeout_seconds: int | None = None,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        if not self._is_code_tool(tool_name, payload):
            return await self._inner.execute_tool(
                tool_name=tool_name,
                payload=payload,
                agent_id=agent_id,
                timeout_seconds=timeout_seconds,
                context=context,
            )

        # Context is authoritative for tenant_id; payload is fallback only.
        ctx = context or {}
        # ADR-036 OP-27 / NOOIT-lijst: de tenant komt UITSLUITEND uit de executiecontext.
        # `payload` is de json.loads van een TOOL_CALL-directive en dus modeloutput; met de
        # terugval erin koos het model in welke tenant-sandbox code draait. Deze klasse zit
        # als BUITENSTE decorator, dus hij ziet de payload voordat ScopedToolBroker de
        # geverifieerde tenant injecteert -- de terugval was hier dus bereikbaar.
        tenant_id: int | None = ctx.get("tenant_id")
        if not tenant_id:
            raise ValueError("tenant_id required for sandbox code execution")

        # Check Docker availability.
        if not self._orchestrator._docker_client:
            settings = get_settings()
            if settings.environment == "production":
                raise RuntimeError(
                    "SandboxToolBroker: Docker unavailable in production -- refusing execution"
                )
            logger.warning(
                "sandbox_tool_broker.docker_unavailable -- falling back to inner broker",
                extra={"tool_name": tool_name, "tenant_id": tenant_id},
            )
            return await self._inner.execute_tool(
                tool_name=tool_name,
                payload=payload,
                agent_id=agent_id,
                timeout_seconds=timeout_seconds,
                context=context,
            )

        code: str = payload.get("code", "")
        language: str = payload.get("language", "python")
        timeout: int = int(timeout_seconds or payload.get("timeout", 30))

        logger.info(
            "sandbox_tool_broker.executing",
            extra={
                "tool_name": tool_name,
                "tenant_id": tenant_id,
                "language": language,
                "timeout": timeout,
            },
        )

        sandbox_id = await self._orchestrator.create_sandbox(
            tenant_id=tenant_id,
            config=SandboxConfig(
                sandbox_type=SandboxType.WORKFLOW,
                language=language,
                memory_limit_mb=256,
                cpu_limit=0.5,
                timeout_seconds=timeout,
                network_enabled=False,
            ),
        )
        if sandbox_id is None:
            raise RuntimeError(
                f"SandboxToolBroker: create_sandbox returned None for tenant {tenant_id}"
            )

        try:
            result = await self._orchestrator.execute_in_sandbox(
                tenant_id=tenant_id,
                sandbox_id=sandbox_id,
                code=code,
                timeout=timeout,
            )
            return {
                "success": result.get("success", False),
                "output": result.get("output", ""),
                "error": result.get("error", ""),
                "sandbox_id": sandbox_id,
                "sandbox_isolated": True,
                "language": language,
            }
        finally:
            await self._orchestrator.destroy_sandbox(tenant_id, sandbox_id)
