"""Async polling helpers for integration tests."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable


async def wait_for_condition(
    check_fn: Callable[[], Any] | Callable[[], Awaitable[Any]],
    condition: Callable[[Any], bool],
    timeout_seconds: float = 10.0,
    poll_interval: float = 0.1,
    description: str = "",
) -> None:
    """Poll until a condition is met or timeout is reached."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = check_fn()
        if asyncio.iscoroutine(result):
            result = await result
        if condition(result):
            return
        await asyncio.sleep(poll_interval)

    raise TimeoutError(f"Condition not met within {timeout_seconds}s: {description}")
