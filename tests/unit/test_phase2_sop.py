import asyncio

import pytest

from src.core.knowledge.sops.sop_executor import SOPExecutor

# MOCK YAML CONTENT
MOCK_SOP_YAML = """
id: SOP-TEST-001
description: Test procedure
steps:
  - tool: say_hello
    params:
      message: "Hello {username}!"
  - tool: report_status
    params:
      status: "done"
      user: "{username}"
"""


@pytest.mark.asyncio
async def test_sop_loading_and_execution(tmp_path):
    # 1. Setup Mock Broker
    class MockBroker:
        def __init__(self):
            self.calls = []

        async def execute_tool(self, tool, params):
            self.calls.append((tool, params))
            return "ok"

    broker = MockBroker()
    executor = SOPExecutor(tool_broker=broker)

    # 2. Load SOP
    sop = executor.load_sop(MOCK_SOP_YAML)
    assert sop.id == "SOP-TEST-001"

    # 3. Execute with Context
    context = {"username": "Bond"}
    result = await executor.execute_sop("SOP-TEST-001", context)

    # 4. Verify Execution
    assert result.status == "SUCCESS"
    assert len(broker.calls) == 2

    # Check variable substitution
    assert broker.calls[0][0] == "say_hello"
    assert broker.calls[0][1]["message"] == "Hello Bond!"

    assert broker.calls[1][0] == "report_status"
    assert broker.calls[1][1]["user"] == "Bond"


@pytest.mark.asyncio
async def test_sop_failure_handling():
    # Test that execution stops if a step fails
    FAIL_YAML = """
    id: SOP-FAIL-001
    description: Fail test
    steps:
      - tool: crash_now
        params: {}
      - tool: never_run
        params: {}
    """

    class CrashingBroker:
        async def execute_tool(self, tool, params):
            if tool == "crash_now":
                raise ValueError("Boom!")
            return "ok"

    executor = SOPExecutor(tool_broker=CrashingBroker())
    executor.load_sop(FAIL_YAML)

    result = await executor.execute_sop("SOP-FAIL-001", {})

    assert result.status == "FAILED"
    assert "Boom!" in result.error
    assert len(result.step_results) == 1  # Only first step ran
    assert result.step_results[0]["status"] == "failed"
