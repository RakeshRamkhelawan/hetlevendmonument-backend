"""ScopedToolBroker enforces execution-context scope onto tool payloads.

The wrapper must treat the execution context (JWT-derived tenant_id/user_id) as
authoritative and override any value the (LLM-generated) payload carries -- a spoofed
action_param must never redirect the tenant/user scope. Dag-9 Gate-2 finding.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.services.tool_broker.scoped_broker import ScopedToolBroker


class _RecordingBroker:
    """Inner IToolBroker stub that records the payload it received."""

    def __init__(self) -> None:
        self.seen_payload: dict[str, Any] | None = None

    async def execute_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],
        agent_id: str | None = None,
        timeout_seconds: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.seen_payload = payload
        return {"ok": True}


@pytest.mark.unit
@pytest.mark.security
async def test_context_tenant_overrides_spoofed_payload_tenant() -> None:
    """A payload-supplied tenant_id is overridden by the execution-context tenant_id."""
    inner = _RecordingBroker()
    scoped = ScopedToolBroker(inner)

    await scoped.execute_tool(
        tool_name="create_task",
        payload={"title": "x", "tenant_id": 999, "user_id": 999},
        context={"tenant_id": 1, "user_id": 2},
    )

    assert inner.seen_payload is not None
    assert inner.seen_payload["tenant_id"] == 1, "context tenant must override spoofed payload"
    assert inner.seen_payload["user_id"] == 2, "context user must override spoofed payload"


@pytest.mark.unit
async def test_context_fills_absent_scope() -> None:
    """When the payload has no tenant_id/user_id, the context values are injected."""
    inner = _RecordingBroker()
    scoped = ScopedToolBroker(inner)

    await scoped.execute_tool(
        tool_name="create_task",
        payload={"title": "x"},
        context={"tenant_id": 7, "user_id": 8},
    )

    assert inner.seen_payload is not None
    assert inner.seen_payload["tenant_id"] == 7
    assert inner.seen_payload["user_id"] == 8
