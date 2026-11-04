import time
from unittest.mock import patch

import pytest

# Deze tests voeren echt een tool uit en hebben dus een tenant in de executiecontext
# nodig (ADR-036 OP-27: de pseudonimiseringsscope van de payload hangt eraan).
from tests.fixtures.tool_execution_tenant import tool_execution_tenant  # noqa: F401

from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.service import ToolBrokerService


@pytest.fixture(autouse=True)
def _allow_all_tools():
    """Bypass ToolPermissionManager for service unit tests -- permission logic tested separately."""
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


@pytest.mark.asyncio
async def test_echo_returns_payload() -> None:
    registry = LocalToolRegistry()
    service = ToolBrokerService(
        serena_client=None,
        seq_thinking_client=None,
        local_registry=registry,
        enable_resilience=False,
    )
    result = await service.execute_tool("test__echo", {"message": "hi"})
    assert result["tool"] == "test__echo"
    assert result["echo"]["message"] == "hi"


@pytest.mark.asyncio
async def test_fail_raises_exception() -> None:
    registry = LocalToolRegistry()
    service = ToolBrokerService(
        serena_client=None,
        seq_thinking_client=None,
        local_registry=registry,
        enable_resilience=False,
    )
    with pytest.raises(ToolExecutionException, match="boom"):
        await service.execute_tool("test__fail", {"message": "boom"})


@pytest.mark.asyncio
async def test_slow_delays_execution() -> None:
    registry = LocalToolRegistry()
    service = ToolBrokerService(
        serena_client=None,
        seq_thinking_client=None,
        local_registry=registry,
        enable_resilience=False,
    )
    # asyncio rekent met de klok `monotonic`; op Windows (Python 3.11) is dat GetTickCount64 met stappen van
    # ~15,6 ms en laat asyncio een timer die korter is dan een stap meteen aflopen (gemeten 2026-10-19: een kale
    # `asyncio.sleep(0.01)` kwam 2 van 2000 keer na 0,0003 s terug). Een ondergrens van exact `delay` is daarom
    # onwaar; `delay` minus een klokstap is het wel, en een tool die niet slaapt blijft zo rood.
    delay = 0.1
    klokstap = time.get_clock_info("monotonic").resolution
    start = time.perf_counter()
    result = await service.execute_tool("test__slow", {"delay_seconds": delay})
    elapsed = time.perf_counter() - start
    assert result["tool"] == "test__slow"
    assert elapsed >= delay - klokstap
