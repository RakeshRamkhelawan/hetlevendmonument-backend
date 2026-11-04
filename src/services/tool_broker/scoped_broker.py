"""
Scoped Tool Broker Wrapper

Wraps an IToolBroker to ensure that tenant_id and user_id are always
propagated from the execution context to the tool payload.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.copilot.protocols import IToolBroker

logger = logging.getLogger(__name__)


class ScopedToolBroker(IToolBroker):
    """Wrapper that enforces context propagation to tool payloads."""

    def __init__(self, inner: IToolBroker) -> None:
        self._inner = inner

    async def execute_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        agent_id: str | None = None,
        timeout_seconds: int | None = None,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute tool, enforcing execution-context scope onto the payload."""
        scoped_payload = payload.copy()

        if context:
            # Context is authoritative: tenant_id/user_id come from the verified execution
            # context (JWT-derived), NEVER from the (LLM-generated) payload. Override any
            # value the payload carries so a spoofed action_param cannot redirect the scope.
            if "tenant_id" in context:
                scoped_payload["tenant_id"] = context["tenant_id"]
            if "user_id" in context:
                scoped_payload["user_id"] = context["user_id"]

            logger.debug(
                "scoped_tool_broker.executing",
                extra={
                    "tool_name": tool_name,
                    "tenant_id": context.get("tenant_id"),
                    "user_id": context.get("user_id"),
                },
            )

        return await self._inner.execute_tool(
            tool_name=tool_name,
            payload=scoped_payload,
            agent_id=agent_id,
            timeout_seconds=timeout_seconds,
            context=context,
        )
