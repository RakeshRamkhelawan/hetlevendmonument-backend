"""Deterministic local test tools for ToolBroker validation."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from src.core.tool_broker.exceptions import ToolExecutionException

__test__ = False


async def test_echo(payload: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Return the payload unchanged for deterministic assertions."""
    return {"echo": payload, "tool": "test__echo", "timestamp": time.time()}


async def test_fail(payload: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Raise a broker-compatible exception for unhappy-path testing."""
    raise ToolExecutionException(
        tool_name="test__fail",
        error_detail=str(payload.get("message", "Test failure")),
    )


async def test_slow(payload: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Sleep for a deterministic interval and return it."""
    delay = float(payload.get("delay_seconds", 1.0))
    await asyncio.sleep(delay)
    return {"delayed": delay, "tool": "test__slow"}
